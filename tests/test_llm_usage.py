"""Fixture test for the check_and_charge + record_tokens round-trip.

The bug this locks down: before this fix, `check_and_charge` wrote
into `(identity, "any", day)` while `record_tokens` did an UPDATE
against `(identity, <specific_model>, day)`. The specific-model row
didn't exist yet, so the UPDATE was a silent no-op and every
`/admin/pulse` report rendered "Tokens: 0 in · 0 out".

Post-fix: `record_tokens` UPSERTs against the per-model key. The two
functions coexist — calls live on "any", tokens live on the specific
model — so `get_usage_today` sums both without double-counting.

Runs without pytest:
    .venv/bin/python tests/test_llm_usage.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.llm import usage as llm_usage  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "usage.db"
        db.init_db(db_path)

        # `usage.py` calls `db.tx()` / `db.connect()` with no path arg — the
        # defaults are bound to the module-level DB_PATH at import time,
        # so mutating `db.DB_PATH` after the fact wouldn't reroute them.
        # Wrap both to force the tmp path.
        _orig_tx, _orig_connect = db.tx, db.connect
        db.tx = lambda path=db_path: _orig_tx(path)
        db.connect = lambda path=db_path: _orig_connect(path)

        identity = "test:user"
        token = llm_usage.set_identity(identity)
        try:
            # First call: charge, then record tokens for the model that served it.
            llm_usage.check_and_charge(model="any")
            llm_usage.record_tokens("gemini-3.5-flash-lite", 1200, 800)

            # Second call to the SAME model: tokens should accumulate.
            llm_usage.check_and_charge(model="any")
            llm_usage.record_tokens("gemini-3.5-flash-lite", 300, 100)

            # Third call, different model (simulated fallback): its own row.
            llm_usage.check_and_charge(model="any")
            llm_usage.record_tokens("gemini-2.5-flash", 500, 250)

            # Inspect the raw rows.
            day = datetime.utcnow().strftime("%Y-%m-%d")
            with db.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT model, calls, tokens_in, tokens_out FROM gemini_usage "
                    "WHERE identity = ? AND day = ? ORDER BY model",
                    (identity, day),
                ).fetchall()
            by_model = {r["model"]: dict(r) for r in rows}

            _assert("any" in by_model,
                    f'expected "any" row for calls counter, got {list(by_model)}')
            _assert(by_model["any"]["calls"] == 3,
                    f'"any".calls expected 3, got {by_model["any"]["calls"]}')
            _assert(by_model["any"]["tokens_in"] == 0,
                    f'"any".tokens_in should stay 0, got {by_model["any"]["tokens_in"]}')

            _assert("gemini-3.5-flash-lite" in by_model,
                    "per-model row for gemini-3.5-flash-lite should exist")
            lite = by_model["gemini-3.5-flash-lite"]
            _assert(lite["calls"] == 0,
                    f'per-model calls should stay 0 (calls live on "any"), got {lite["calls"]}')
            _assert(lite["tokens_in"] == 1500,
                    f"tokens_in should accumulate to 1500, got {lite['tokens_in']}")
            _assert(lite["tokens_out"] == 900,
                    f"tokens_out should accumulate to 900, got {lite['tokens_out']}")

            fallback = by_model["gemini-2.5-flash"]
            _assert(fallback["tokens_in"] == 500 and fallback["tokens_out"] == 250,
                    f"fallback model tokens wrong: {fallback}")

            # get_usage_today sums across all rows for the identity — must
            # not double-count. Calls only live on "any" (=3). Tokens live
            # on specific models (=2000 in / 1150 out).
            agg = llm_usage.get_usage_today(identity)
            _assert(agg["calls"] == 3, f"agg calls expected 3, got {agg['calls']}")
            _assert(agg["tokens_in"] == 2000,
                    f"agg tokens_in expected 2000, got {agg['tokens_in']}")
            _assert(agg["tokens_out"] == 1150,
                    f"agg tokens_out expected 1150, got {agg['tokens_out']}")

            # Zero-token calls (SDK didn't report usage) are still safe —
            # nothing written, no exception.
            llm_usage.record_tokens("gemini-3.5-flash-lite", 0, 0)
            with db.connect(db_path) as conn:
                lite2 = conn.execute(
                    "SELECT tokens_in FROM gemini_usage "
                    "WHERE identity = ? AND model = ? AND day = ?",
                    (identity, "gemini-3.5-flash-lite", day),
                ).fetchone()
            _assert(lite2["tokens_in"] == 1500, "zero-token call should not mutate")

            # No identity → both functions should be no-ops (CLI/script contexts).
            llm_usage.reset_identity(token)
            llm_usage.check_and_charge(model="any")   # no crash
            llm_usage.record_tokens("gemini-3.5-flash-lite", 999, 999)
            token = llm_usage.set_identity(identity)
            agg2 = llm_usage.get_usage_today(identity)
            _assert(agg2["tokens_in"] == 2000,
                    "no-identity record_tokens must not touch other identities")
        finally:
            llm_usage.reset_identity(token)
            db.tx, db.connect = _orig_tx, _orig_connect

    print("OK — usage accounting round-trip verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
