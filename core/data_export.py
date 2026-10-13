""""Download my data" (ADR-084): one ZIP of everything the user put in or the
app made about them. PIPEDA access + Quebec Law 25 portability.

Pure caches of public data (jobs, search tasks, company research) and
internal counters (gemini_usage, rate_limits) are left out; every table here
is also wiped by "Delete all" (tests/test_data_export.py checks both lists).
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core import db

# table -> file name in the ZIP. Résumé file bytes are written separately.
EXPORT_TABLES: dict[str, str] = {
    "resumes": "resumes.json",
    "applications": "applications.json",
    "saved_searches": "saved_searches.json",
    "job_scores": "fit_scores.json",
    "gap_dismissals": "gap_dismissals.json",
    "tailor_runs": "tailored_resumes.json",
    "tailored_scores": "tailored_scores.json",
    "interviews": "interviews.json",
    "prep_artifacts": "interview_prep.json",
    "practice_sessions": "practice_sessions.json",
    "practice_answers": "practice_answers.json",
    "stories": "stories.json",
    "story_drafts": "story_drafts.json",
    "feedback": "feedback_you_sent.json",
    "events": "activity_log.json",
}

_README = """Your Jobot data, exported {when} (UTC).

Each .json file is one kind of data, as a list of records.
applications.csv is the same as applications.json, for spreadsheets.
resume_files/ holds the original files you uploaded.

Voice recordings are not included because we never store them.
Questions: see the privacy page.
"""


def _rows(conn, table: str) -> list[dict]:
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if not cols:
        return []   # table not in this DB's schema (older deploy)
    keep = [c for c in cols if c != "raw_bytes"]
    return [dict(r) for r in conn.execute(f"SELECT {', '.join(keep)} FROM {table}").fetchall()]


def build_zip(path: Path = db.DB_PATH) -> bytes:
    buf = io.BytesIO()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    with db.connect(path) as conn, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", _README.format(when=now))
        for table, name in EXPORT_TABLES.items():
            rows = _rows(conn, table)
            z.writestr(name, json.dumps(rows, ensure_ascii=False, indent=2, default=str))
            if table == "applications" and rows:
                s = io.StringIO()
                w = csv.DictWriter(s, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
                z.writestr("applications.csv", s.getvalue())
        for r in conn.execute("SELECT id, filename, raw_bytes FROM resumes WHERE raw_bytes IS NOT NULL").fetchall():
            safe = Path(r["filename"] or "resume").name or "resume"
            z.writestr(f"resume_files/{r['id']}-{safe}", bytes(r["raw_bytes"]))
    return buf.getvalue()
