"""In-app nudges (REQ-058): the right one shows, a dismissed one never returns,
the feedback intro shows once, and the banner renders in both languages.

Runs without pytest:
    .venv/bin/python tests/test_nudges.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.requests import Request  # noqa: E402

from core import db, events, nudges  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "n.db"
        db.init_db(p)
        _tx, _c = db.tx, db.connect
        db.tx = lambda path=p: _tx(path)
        db.connect = lambda path=p: _c(path)
        try:
            assert nudges.pick("jobs").id == "add_resume", "no résumé → add_resume"
            assert nudges.pick("profile") is None, "add_resume not on the profile page"
            assert nudges.pick("jobs", "feedback") is None, "no scores → no feedback intro"

            with db.tx(p) as conn:
                conn.execute("INSERT INTO resumes (filename, uploaded_at, parsed_json, is_current) VALUES ('a', 'x', '{}', 1)")
            assert nudges.pick("jobs").id == "first_search", "résumé, no search → first_search"
            assert nudges.pick("journey") is None, "first_search only on jobs"

            events.track("nudge.dismissed", id="first_search")
            assert nudges.pick("jobs") is None, "dismissed never returns"

            # An old user whose search tasks were pruned still has jobs: no "start here".
            with db.tx(p) as conn:
                conn.execute("DELETE FROM events")
                conn.execute("INSERT INTO jobs (id, title, company, first_seen, last_seen) VALUES ('j1', 't', 'c', 'x', 'x')")
            assert nudges.pick("jobs") is None, "past jobs count as having searched"
            with db.tx(p) as conn:
                conn.execute("DELETE FROM jobs")
            events.track("nudge.dismissed", id="first_search")

            os.environ["JOBOT_NUDGES_OFF"] = "add_resume"
            with db.tx(p) as conn:
                conn.execute("UPDATE resumes SET is_current = 0")
            assert nudges.pick("jobs") is None, "switched off by env"
            del os.environ["JOBOT_NUDGES_OFF"]

            stats = {s["id"]: s for s in nudges.stats()}
            assert stats["first_search"]["dismissed"] == 1 and stats["add_resume"]["on"], stats

            # Banner renders (both languages) with its one action + Not now.
            from ui_web import i18n
            from ui_web.deps import templates
            req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "app": None})
            for lang, want in (("en", "Add your résumé"), ("es", "Agrega tu currículum")):
                i18n.set_ui_language(lang)
                html = templates.get_template("partials/nudge_banner.html").render(request=req, active_tab="jobs")
                assert want in html and "nudgeBanner(" in html, (lang, html[:400])
            i18n.set_ui_language("en")
        finally:
            db.tx, db.connect = _tx, _c
    print("OK — nudges: pick, page scope, dismiss, env off, stats, banner render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
