"""Round-trip test for the DB-backed Gemini per-model daily state.

The bug this locks down: `_exhausted_models` / `_request_counts` used to be
module-level RAM dicts, wiped on every Fly `auto_stop_machines` wake. That
reset (a) re-probed exhausted models (wasted 429s) and (b) let the fallback
chain land on a DIFFERENT model across restarts → inconsistent scores
(next-work.md, Mehran's unstable re-score). Post-fix the state lives in the
`gemini_model_state` table (schema v18) and survives process death.

Runs without pytest:
    .venv/bin/python tests/test_gemini_model_state.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.llm import gemini  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "state.db"
        db.init_db(db_path)

        # gemini's state helpers call db.tx() / db.connect() with no path arg
        # (bound to the module-level DB_PATH). Reroute both to the temp DB —
        # same technique as tests/test_llm_usage.py.
        _orig_tx, _orig_connect = db.tx, db.connect
        db.tx = lambda path=db_path: _orig_tx(path)
        db.connect = lambda path=db_path: _orig_connect(path)
        try:
            client = gemini.GeminiClient(api_key="x")  # no network — state only

            # Fresh DB: nothing exhausted, all models available, counts zero.
            _assert(client.available_models() == list(gemini.DEFAULT_MODEL_CHAIN),
                    "all models should be available on a fresh DB")
            _assert(not client.all_models_exhausted(), "nothing exhausted yet")
            _assert(all(c == 0 for c in gemini.request_counts_today().values()),
                    "counts should start at zero")

            # Count increments accumulate.
            primary = gemini.DEFAULT_MODEL_CHAIN[0]
            gemini._increment_count(primary)
            gemini._increment_count(primary)
            gemini._increment_count(gemini.DEFAULT_MODEL_CHAIN[1])
            counts = gemini.request_counts_today()
            _assert(counts[primary] == 2, f"{primary} count expected 2, got {counts[primary]}")
            _assert(counts[gemini.DEFAULT_MODEL_CHAIN[1]] == 1, "second model count expected 1")

            # Marking exhausted removes a model from availability and is
            # visible through the module-level view.
            gemini._mark_exhausted(primary)
            _assert(primary in gemini.exhausted_models(), "primary should read as exhausted")
            _assert(primary not in client.available_models(),
                    "exhausted model must drop out of available_models")
            _assert(not client.all_models_exhausted(),
                    "chain not fully down — others remain")

            # Marking exhausted must NOT clobber the accumulated count (the
            # UPSERT touches only its own column).
            _assert(gemini.request_counts_today()[primary] == 2,
                    "exhaustion mark should preserve the request count")

            # Exhaust the rest → all_models_exhausted flips true.
            for m in gemini.DEFAULT_MODEL_CHAIN[1:]:
                gemini._mark_exhausted(m)
            _assert(client.all_models_exhausted(), "whole chain should now read exhausted")
            _assert(client.available_models() == [], "no models available once all down")

            # DURABILITY: a brand-new connection (simulating a process restart)
            # sees the persisted state — the whole point of the fix.
            with _orig_connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT model, exhausted, count FROM gemini_model_state"
                ).fetchall()
            by_model = {r["model"]: dict(r) for r in rows}
            _assert(by_model[primary]["exhausted"] == 1, "exhaustion persisted to disk")
            _assert(by_model[primary]["count"] == 2, "count persisted to disk")
        finally:
            db.tx, db.connect = _orig_tx, _orig_connect

    print("OK — gemini_model_state round-trip + durability verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
