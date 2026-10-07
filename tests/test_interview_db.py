"""Interview DB helpers (REQ-041 / ADR-047). Locks down:
  1. create_interview round-trips source_url + all structured-interview fields,
     coerces an unknown round_type to the D2 default;
  2. update_interview_fields patches only whitelisted content fields (the build
     step's link-scrape backfill) and ignores id/resume_hash/status;
  3. list_interviews orders soonest-dated first, undated last;
  4. delete cascades prep_artifacts away.
    .venv/bin/python tests/test_interview_db.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "iv.sqlite"
    db.init_db(p)
    return p


def test_create_roundtrips_and_coerces():
    p = _fresh()
    iid = db.create_interview(
        "cand1", "Stripe", "Senior PD", "Design systems.", "en", "paste_link",
        source_url="https://job/x", interviewer_title="Director of Design",
        recruiter_notes="panel of 3", round_type="nonsense", round_length_min=60,
        interview_at="2026-10-24T10:00", path=p)
    row = db.get_interview(iid, path=p)
    _assert(row["source_url"] == "https://job/x", "source_url stored")
    _assert(row["round_type"] == "screening", "unknown round_type → screening default")
    _assert(row["round_length_min"] == 60 and row["interviewer_title"] == "Director of Design", "fields stored")
    _assert(row["status"] == "created", "starts in created")
    print("PASS test_create_roundtrips_and_coerces")


def test_update_fields_whitelist():
    p = _fresh()
    iid = db.create_interview("cand1", "", "", "", "en", "paste_link",
                              source_url="https://job/x", path=p)
    db.update_interview_fields(iid, {
        "jd_text": "scraped JD", "company": "Stripe", "role_title": "PD",
        "id": 999, "resume_hash": "hacked", "status": "toolkit_ready"}, path=p)
    row = db.get_interview(iid, path=p)
    _assert(row["jd_text"] == "scraped JD" and row["company"] == "Stripe", "whitelisted fields patched")
    _assert(row["id"] == iid and row["resume_hash"] == "cand1", "id/resume_hash NOT writable")
    _assert(row["status"] == "created", "status NOT writable via update_interview_fields")
    print("PASS test_update_fields_whitelist")


def test_list_orders_dated_first():
    p = _fresh()
    db.create_interview("cand1", "A", "r", "", "en", "paste_text", path=p)  # undated
    later = db.create_interview("cand1", "B", "r", "", "en", "paste_text",
                                interview_at="2026-12-01T09:00", path=p)
    sooner = db.create_interview("cand1", "C", "r", "", "en", "paste_text",
                                 interview_at="2026-10-01T09:00", path=p)
    from datetime import datetime
    ids = [i["id"] for i in db.list_interviews("cand1", path=p, now=datetime(2026, 9, 20))]
    _assert(ids[0] == sooner and ids[1] == later, f"soonest dated first, got {ids}")
    _assert(ids[2] not in (sooner, later), "undated last")
    # Code-review 2026-10-07: a past interview must not hold the "next" hero.
    ids = [i["id"] for i in db.list_interviews("cand1", path=p, now=datetime(2026, 10, 7))]
    _assert(ids[0] == later, f"upcoming first, the past one last, got {ids}")
    _assert(ids[-1] == sooner, "past interviews go to the end")
    # Same day, local time: still "next" for hours after the UTC clock passes it.
    ids = [i["id"] for i in db.list_interviews("cand1", path=p, now=datetime(2026, 10, 1, 13, 0))]
    _assert(ids[0] == sooner, "an interview isn't past until 14 h after its stored time")
    print("PASS test_list_orders_dated_first")


def test_delete_cascades_artifacts():
    p = _fresh()
    iid = db.create_interview("cand1", "A", "r", "", "en", "paste_text", path=p)
    db.save_prep_artifact(iid, "brief", "en", "v1", {"k": 1}, "m", path=p)
    db.delete_interview(iid, path=p)
    _assert(db.get_prep_artifact(iid, "brief", "en", "v1", path=p) is None, "artifacts cascade on delete")
    print("PASS test_delete_cascades_artifacts")


if __name__ == "__main__":
    test_create_roundtrips_and_coerces()
    test_update_fields_whitelist()
    test_list_orders_dated_first()
    test_delete_cascades_artifacts()
    print("all interview-db tests passed")
