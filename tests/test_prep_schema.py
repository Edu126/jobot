"""Prep / land-it kit schema (REQ-023, v21): the three new tables exist after
init, and the two FK behaviours the ADRs depend on hold:

  1. prep_kits CASCADEs off prep_sessions (ADR-028) — deleting a session drops
     its cached kit blob.
  2. prep_sessions.job_id is ON DELETE SET NULL (ADR-026) — the session is
     SELF-CONTAINED, so wiping the bound job leaves the session alive (with its
     stored jd_text) and just clears the binding. This is what makes a prep
     session robust to the job row / live posting disappearing months later.

No network. Runs without pytest:
    .venv/bin/python tests/test_prep_schema.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _fresh_db() -> Path:
    p = Path(tempfile.mkdtemp()) / "prep.sqlite"
    db.init_db(p)
    return p


def test_tables_exist_and_version() -> None:
    p = _fresh_db()
    con = sqlite3.connect(p)
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("prep_sessions", "company_outlook", "prep_kits"):
            _assert(t in tables, f"{t} missing after init_db")
        ver = con.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        _assert(ver == str(db.SCHEMA_VERSION) == "23", f"schema_version={ver}, want 23")
        # v22/v23: imported/pasted sessions carry a self-contained score + brief.
        ps_cols = {r[1] for r in con.execute("PRAGMA table_info(prep_sessions)")}
        _assert("match_score" in ps_cols, "prep_sessions.match_score missing (v22)")
        _assert("match_brief" in ps_cols, "prep_sessions.match_brief missing (v23)")
    finally:
        con.close()
    print("PASS test_tables_exist_and_version")


def test_kit_cascades_off_session() -> None:
    p = _fresh_db()
    con = sqlite3.connect(p)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        con.execute(
            "INSERT INTO prep_sessions(id, resume_hash, company, source, created_at) "
            "VALUES (1, 'abc', 'CMHC', 'pasted_text', 'now')")
        con.execute(
            "INSERT INTO prep_kits(prep_session_id, lang, prompt_version, kit_json, created_at) "
            "VALUES (1, 'en', 'v1', '{}', 'now')")
        con.commit()
        con.execute("DELETE FROM prep_sessions WHERE id = 1")
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM prep_kits WHERE prep_session_id = 1").fetchone()[0]
        _assert(n == 0, f"prep_kits should CASCADE-delete with its session, found {n}")
    finally:
        con.close()
    print("PASS test_kit_cascades_off_session")


def test_session_survives_job_delete() -> None:
    p = _fresh_db()
    con = sqlite3.connect(p)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        con.execute(
            "INSERT INTO jobs(id, title, company, first_seen, last_seen) "
            "VALUES ('job-1', 'Senior BA', 'CMHC', 'now', 'now')")
        con.execute(
            "INSERT INTO prep_sessions(id, resume_hash, job_id, company, jd_text, source, created_at) "
            "VALUES (2, 'abc', 'job-1', 'CMHC', 'the JD text', 'from_job', 'now')")
        con.commit()
        con.execute("DELETE FROM jobs WHERE id = 'job-1'")
        con.commit()
        row = con.execute(
            "SELECT job_id, jd_text FROM prep_sessions WHERE id = 2").fetchone()
        _assert(row is not None, "session must survive its bound job being deleted")
        _assert(row[0] is None, f"job_id should be SET NULL after job delete, got {row[0]!r}")
        _assert(row[1] == "the JD text", "stored jd_text must be preserved (self-contained)")
    finally:
        con.close()
    print("PASS test_session_survives_job_delete")


if __name__ == "__main__":
    test_tables_exist_and_version()
    test_kit_cascades_off_session()
    test_session_survives_job_delete()
    print("all prep-schema tests passed")
