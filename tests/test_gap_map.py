"""Gap map (REQ-019 / ADR-022): cross-job aggregation + ranking + JD-free
parse. Locks down that the map (1) counts a gap across the résumé's scored jobs
case-insensitively, (2) shows only REAL gaps ranked by count (wording stays
per-job), and (3) still ranks gaps it couldn't classify, honestly, rather than
dropping them. No network — build_gap_map runs with client=None (cache only).

Runs without pytest:
    .venv/bin/python tests/test_gap_map.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.matching import gap_map as gm  # noqa: E402
from core.matching import semantic_score as ss  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_parse_jdfree() -> None:
    raw = {"classifications": [
        {"gap": "AutoCAD", "kind": "wording", "suggestion": "You list Autodesk suite."},
        {"gap": "PMP", "kind": "bogus", "suggestion": "x"},
    ]}
    out = gm._parse_response(raw, ["AutoCAD", "PMP", "Dropped"])
    _assert(out["AutoCAD"] == ("wording", "You list Autodesk suite."), "wording parsed")
    _assert(out["PMP"][0] == "real", "bad kind → real")
    _assert("Dropped" not in out, "a gap the model omitted is left out (caller keeps it real)")


def test_build_map_ranks_real_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        _o_tx, _o_connect = db.tx, db.connect
        db.tx = lambda *a, **k: _o_tx(db_path)
        db.connect = lambda *a, **k: _o_connect(db_path)
        try:
            rid = db.save_resume("cv.pdf", {"raw_text": "Autodesk suite; team delivery lead"}, b"x")
            for jid in ("j1", "j2"):
                db.upsert_job({"id": jid, "title": "T", "company": "C", "description": "d"})
            lang = "en"
            db.save_scores(rid, [
                {"job_id": "j1", "score": 50, "verdict": "stretch", "reasoning": "r",
                 "matched": [], "gaps": ["PMP certification", "AutoCAD"], "model": "m"},
                {"job_id": "j2", "score": 50, "verdict": "stretch", "reasoning": "r",
                 "matched": [], "gaps": ["PMP certification", "Six Sigma"], "model": "m"},
            ], lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)

            # Aggregation is pure SQL: PMP twice, the others once.
            counts = db.gap_counts_for_resume(rid, lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)
            _assert(counts.get("PMP certification") == 2, f"PMP count 2, got {counts}")
            _assert(counts.get("AutoCAD") == 1 and counts.get("Six Sigma") == 1, "singles counted once")

            # Seed classifications (no LLM): AutoCAD is a wording gap, the rest real.
            db.save_gap_classifications(rid, lang, gm.PROMPT_VERSION, [
                {"gap": "PMP certification", "kind": "real", "suggestion": "Lead with delivery ownership."},
                {"gap": "AutoCAD", "kind": "wording", "suggestion": "Name it explicitly."},
                {"gap": "Six Sigma", "kind": "real", "suggestion": "Frame your process-improvement work."},
            ])

            entries = gm.build_gap_map(rid, "Autodesk suite; team delivery lead", None, lang=lang)
            gaps = [e.gap for e in entries]
            _assert("AutoCAD" not in gaps, "wording gap must NOT appear in the map (stays per-job)")
            _assert(gaps == ["PMP certification", "Six Sigma"],
                    f"real gaps ranked by count desc then alpha, got {gaps}")
            _assert(entries[0].count == 2 and entries[0].suggestion.startswith("Lead"),
                    "top entry carries its count + defense hook")
        finally:
            db.tx, db.connect = _o_tx, _o_connect


def test_build_map_keeps_unclassified_as_real() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        _o_tx, _o_connect = db.tx, db.connect
        db.tx = lambda *a, **k: _o_tx(db_path)
        db.connect = lambda *a, **k: _o_connect(db_path)
        try:
            rid = db.save_resume("cv.pdf", {"raw_text": "some text"}, b"x")
            db.upsert_job({"id": "j1", "title": "T", "company": "C", "description": "d"})
            db.save_scores(rid, [
                {"job_id": "j1", "score": 40, "verdict": "stretch", "reasoning": "r",
                 "matched": [], "gaps": ["Kubernetes"], "model": "m"},
            ], "en", ss.PROMPT_VERSION, ss.SCORING_VERSION)
            # No classification seeded, client=None → can't classify. Must still
            # surface the gap honestly as real with no suggestion (never dropped).
            entries = gm.build_gap_map(rid, "some text", None, lang="en")
            _assert(len(entries) == 1 and entries[0].gap == "Kubernetes", "unclassified gap still shown")
            _assert(entries[0].kind == "real" and entries[0].suggestion == "",
                    "unclassified → honest real, no invented suggestion")
        finally:
            db.tx, db.connect = _o_tx, _o_connect


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("OK — gap_map aggregation + ranking verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
