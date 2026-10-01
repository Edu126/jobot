"""Check-in + card-gap routes (ADR-058 rev. 2026-10-01). Locks down:
  - Get Ready hands off to /check-in until THIS question set is answered/skipped
    (and the old ?clarify=1 link lands there too);
  - Skip-all never erases answers already saved;
  - /facts/add appends one gap answer, keeping every existing answer + the
    asked-marker; blank answers are refused.
Routes are exercised with their DB/brief/facts dependencies stubbed.

    .venv/bin/python tests/test_prep_checkin_routes.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core.prep import brief as B  # noqa: E402
from ui_web.routes import interviews as R  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    brief = B._parse_brief({"role_summary": "r", "competencies": [{"name": "x", "what_good_looks_like": "g"}],
                            "clarify_questions": [{"question": "Q1?"}, {"question": "Q2?"}]})
    state = {"submitted": False, "facts": {"Q1?": "existing"}, "saved": None}
    R.db.get_interview = lambda i: {"id": i, "lang": "en", "resume_hash": "h"}
    R.db.touch_interview = lambda i: None
    R.prep_brief.read_cached_brief = lambda i, lang=None: brief
    R.prep_toolkit.facts_submitted = lambda i, qs: state["submitted"]
    R.prep_toolkit.read_facts = lambda i: dict(state["facts"])
    R.prep_toolkit.save_facts = lambda i, a, asked=None, skipped=False: state.update(
        saved={"answers": dict(a), "asked": asked, "skipped": skipped})
    app = FastAPI()
    app.include_router(R.router)
    c = TestClient(app)

    r = c.get("/interviews/3/get-ready", follow_redirects=False)
    _assert(r.status_code == 303 and r.headers["location"] == "/interviews/3/check-in", "unanswered → check-in")
    r = c.get("/interviews/3/get-ready?clarify=1", follow_redirects=False)
    _assert(r.headers.get("location") == "/interviews/3/check-in", "old 'Edit clarifications' link → check-in")

    c.post("/interviews/3/facts", data={"skip": "1", "fact_f1": "typed but skipped"}, follow_redirects=False)
    _assert(state["saved"]["answers"] == {"Q1?": "existing"}, "skip keeps saved answers, ignores the form")
    _assert(state["saved"]["asked"] == ["Q1?", "Q2?"] and state["saved"]["skipped"], "skip marks this set as skipped")

    c.post("/interviews/3/facts", data={"fact_f2": "new answer"}, follow_redirects=False)
    _assert(state["saved"]["answers"] == {"Q2?": "new answer"} and not state["saved"]["skipped"],
            "submit saves what was typed, keyed by question text; not a skip")

    r = c.post("/interviews/3/facts/add", data={"key": "How? — your cadence", "answer": "monthly review"})
    _assert(r.status_code == 204, "gap saved")
    _assert(state["saved"]["answers"] == {"Q1?": "existing", "How? — your cadence": "monthly review"},
            "gap appended, existing answers kept")
    _assert(state["saved"]["asked"] == ["Q1?", "Q2?"], "asked-marker kept")
    _assert(c.post("/interviews/3/facts/add", data={"key": "k", "answer": " "}).status_code == 400, "blank refused")

    print("OK — check-in routes verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
