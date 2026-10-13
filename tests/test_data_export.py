"""Download my data (ADR-084): the ZIP holds every user table and the original
résumé file, and every exported table is also wiped by Delete all.

Runs without pytest:
    .venv/bin/python tests/test_data_export.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import data_export, db  # noqa: E402


def main() -> int:
    src = (ROOT / "ui_web/routes/profile.py").read_text()
    block = src[src.index('@router.post("/profile/data/delete-all")'):]
    block = block[:block.index("conn.execute(f\"DELETE FROM {table}\")")]
    wiped = set(re.findall(r'"([a-z_]+)"', block))
    missing = set(data_export.EXPORT_TABLES) - wiped
    assert not missing, f"exported but not wiped by Delete all: {missing}"

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.db"
        db.init_db(p)
        with db.tx(p) as conn:
            conn.execute("INSERT INTO resumes (filename, uploaded_at, parsed_json, raw_bytes, is_current) "
                         "VALUES ('cv.pdf', '2026-10-12', '{\"contact\": {\"name\": \"Sam\"}}', ?, 1)", (b"%PDF-1",))
        z = zipfile.ZipFile(io.BytesIO(data_export.build_zip(p)))
        names = set(z.namelist())
        for f in ["README.txt", "resume_files/1-cv.pdf", *data_export.EXPORT_TABLES.values()]:
            assert f in names, f"{f} missing from the ZIP: {sorted(names)}"
        rows = json.loads(z.read("resumes.json"))
        assert rows[0]["filename"] == "cv.pdf" and "raw_bytes" not in rows[0], rows
        assert z.read("resume_files/1-cv.pdf") == b"%PDF-1"
    print("OK — export ZIP complete, every exported table is also deleted by Delete all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
