"""Gap enhancement (REQ-018 / ADR-021): parse robustness + cache round-trip.

Two things are locked down here:

1. `_parse_response` never fabricates. The whole feature is bound by GOV-005
   (enhance ≠ fabricate), so the parser's safe failure mode — unknown kind,
   dropped gap, re-cased gap — must always land on an honest "real" with no
   invented rewording, and must return exactly one entry per input gap.
2. The `gap_enhancements` cache keys the same way as `job_scores` (résumé
   TEXT hash + lang + prompt_version), so a version/lang mismatch is a miss.

No network: we test the parser directly and the DB helpers directly.

Runs without pytest:
    .venv/bin/python tests/test_gap_enhance.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.matching import gap_enhance as ge  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_parse_happy_path() -> None:
    gaps = ["AutoCAD", "PMP certification"]
    raw = {"enhancements": [
        {"gap": "AutoCAD", "kind": "wording", "suggestion": "You list Autodesk suite — name AutoCAD explicitly."},
        {"gap": "PMP certification", "kind": "real", "suggestion": "Genuine gap; you have project lead experience but no PMP."},
    ]}
    out = ge._parse_response(raw, gaps)
    _assert(len(out) == 2, "one entry per gap")
    _assert(out[0].kind == "wording" and out[1].kind == "real", "kinds preserved")
    _assert(out[0].suggestion.startswith("You list"), "suggestion preserved")


def test_parse_bad_kind_falls_back_to_real() -> None:
    out = ge._parse_response(
        {"enhancements": [{"gap": "Kubernetes", "kind": "invent-it", "suggestion": "x"}]},
        ["Kubernetes"],
    )
    _assert(out[0].kind == "real", "unknown kind must default to real (GOV-005)")


def test_parse_missing_gap_is_honest_real() -> None:
    # Model dropped the gap entirely → we must still return it, as a real gap
    # with no fabricated rewording.
    out = ge._parse_response({"enhancements": []}, ["Six Sigma"])
    _assert(len(out) == 1 and out[0].gap == "Six Sigma", "dropped gap still returned")
    _assert(out[0].kind == "real" and out[0].suggestion == "",
            "dropped gap → real, no invented suggestion")


def test_parse_recased_gap_fuzzy_matches() -> None:
    out = ge._parse_response(
        {"enhancements": [{"gap": "data ANALYSIS", "kind": "wording", "suggestion": "s"}]},
        ["Data Analysis"],
    )
    _assert(out[0].kind == "wording", "case-insensitive gap match should hold")
    _assert(out[0].gap == "Data Analysis", "echoes the ORIGINAL gap text, not the model's")


def test_parse_garbage_returns_one_real_per_gap() -> None:
    for raw in ({}, {"enhancements": "nope"}, {"enhancements": [42, None]}):
        out = ge._parse_response(raw, ["A", "B"])
        _assert(len(out) == 2, f"must return one per gap for {raw!r}")
        _assert(all(e.kind == "real" for e in out), "garbage → all real")


def test_cache_round_trip_and_key_isolation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        rid = db.save_resume(
            "cv.pdf", {"raw_text": "Autodesk suite; selección de personal"}, b"x",
            path=db_path,
        )
        payload = [{"gap": "AutoCAD", "kind": "wording", "suggestion": "Name it explicitly."}]

        _assert(db.get_cached_gap_enhancement("job1", rid, "en", ge.PROMPT_VERSION, path=db_path) is None,
                "cold cache is a miss")
        _assert(db.save_gap_enhancement("job1", rid, "en", ge.PROMPT_VERSION, payload, "m", path=db_path),
                "save returns True on a text-ful resume")

        hit = db.get_cached_gap_enhancement("job1", rid, "en", ge.PROMPT_VERSION, path=db_path)
        _assert(hit == payload, f"round-trip must be identical, got {hit!r}")

        # lang + prompt_version are part of the key → mismatches are misses.
        _assert(db.get_cached_gap_enhancement("job1", rid, "es", ge.PROMPT_VERSION, path=db_path) is None,
                "other language is a miss")
        _assert(db.get_cached_gap_enhancement("job1", rid, "en", "other-version", path=db_path) is None,
                "other prompt version is a miss")


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("OK — gap_enhance parse + cache verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
