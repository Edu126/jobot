"""Typed-practice build route (code-review 2026-10-07). Locks down:
  - a failed debrief (quota / model error) is NEVER saved as an empty "done"
    session: the user gets the Retry partial and the session stays open;
  - Retry only re-scores answers that have no evaluation yet;
  - a session that is already done redirects to Feedback without rebuilding;
  - a second request while a build is in flight waits instead of paying twice.
Dependencies are stubbed; no network.

    .venv/bin/python tests/test_practice_build_route.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core.prep import practice as PR  # noqa: E402
from ui_web.routes import interviews as R  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    state = {"status": "building", "saved": None, "p8_calls": 0, "p9_ok": False}
    answers = [{"id": 1, "position": 0, "question_id": "q1", "question_text": "Q1", "competency_id": None,
                "transcript": "t", "seconds": 30, "delivery": {"wpm": 120}, "eval": {"overall": "solid"}},
               {"id": 2, "position": 1, "question_id": "q2", "question_text": "Q2", "competency_id": None,
                "transcript": "t", "seconds": 30, "delivery": None, "eval": None}]
    R.db.get_interview = lambda i: {"id": i, "lang": "en", "resume_hash": "h"}
    R.db.get_practice_session = lambda s: {"id": s, "interview_id": 3, "status": state["status"],
                                           "questions": [{"id": "q1"}, {"id": "q2"}]}
    R.db.list_practice_answers = lambda s: answers
    R.db.list_stories = lambda *a, **k: []
    R.db.save_practice_eval = lambda aid, ev: None
    R.db.save_practice_debrief = lambda s, d: state.update(saved=d, status="done")
    R.prep_brief.read_cached_brief = lambda i, lang=None: None
    R.prep_toolkit.read_cached_mapping = lambda *a, **k: []
    R.GeminiClient = lambda **k: object()
    R.resolve_api_key = lambda: "k"

    def p8(*a, **k):
        state["p8_calls"] += 1
        return None   # the model fails
    PR_eval, PR_debrief = R.prep_practice.evaluate_answer, R.prep_practice.session_debrief
    R.prep_practice.evaluate_answer = p8
    R.prep_practice.session_debrief = lambda evals, *a, **k: (
        PR.Debrief(takeaway="ok") if state["p9_ok"] else None)
    try:
        app = FastAPI()
        app.include_router(R.router)
        c = TestClient(app)
        url = "/interviews/3/practice/9/build"

        r = c.post(url)
        _assert(state["saved"] is None and state["status"] == "building",
                "failure → nothing saved, session not marked done")
        _assert("practice-build" in r.text and "/build" in r.text, "Retry partial returned")
        _assert(state["p8_calls"] == 1, f"only the un-evaluated answer is scored ({state['p8_calls']})")

        state["p9_ok"] = True
        r = c.post(url)
        _assert(r.headers.get("HX-Redirect", "").endswith("/feedback") and state["saved"] == PR.Debrief(takeaway="ok").to_dict(),
                "retry that works → saved + redirect to Feedback")

        calls = state["p8_calls"]
        r = c.post(url)   # status is now done
        _assert(r.headers.get("HX-Redirect", "").endswith("/feedback") and state["p8_calls"] == calls,
                "done session → straight to Feedback, no rebuild")

        state["status"] = "building"
        R._BUILDS_IN_FLIGHT.add(9)
        r = c.post(url)
        _assert("load delay:3s" in r.text and state["p8_calls"] == calls, "in-flight build → wait, no second build")
        R._BUILDS_IN_FLIGHT.discard(9)
    finally:
        R.prep_practice.evaluate_answer, R.prep_practice.session_debrief = PR_eval, PR_debrief
    print("PASS practice build route")
    return 0


if __name__ == "__main__":
    sys.exit(main())
