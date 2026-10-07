"""'Delete all' must wipe EVERY user-data table (code-review 2026-10-07).

Tables keyed on resume_hash / text_hash have no FK cascade from resumes, so a
new one silently survives the wipe unless it's listed (it happened twice: the
gap caches, then interviews + stories). This test compares the real schema to
the route's wipe list; system tables must be named in KEEP on purpose.

    .venv/bin/python tests/test_delete_all.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import db  # noqa: E402

# Not user data: schema/version + language prefs, and today's model-quota state.
KEEP = {"meta", "gemini_model_state"}


def _wiped_tables() -> set[str]:
    src = (ROOT / "ui_web/routes/profile.py").read_text()
    i = src.index("async def data_delete_all")
    j = src.index("for table in (", i)
    k = src.index('conn.execute(f"DELETE', j)
    return set(re.findall(r'"([a-z_]+)"', src[j:k]))


def test_every_table_is_wiped_or_kept_on_purpose():
    p = Path(tempfile.mkdtemp()) / "t.db"
    db.init_db(p)
    tables = {r[0] for r in sqlite3.connect(p).execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    wiped = _wiped_tables()
    missing = tables - wiped - KEEP
    assert not missing, f"Delete all leaves these tables behind: {sorted(missing)}"
    assert not (wiped - tables), f"wipe list names tables that don't exist: {sorted(wiped - tables)}"
    print("PASS test_every_table_is_wiped_or_kept_on_purpose")


if __name__ == "__main__":
    test_every_table_is_wiped_or_kept_on_purpose()
    print("all delete-all tests passed")
