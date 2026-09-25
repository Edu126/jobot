"""Practice DB helpers (REQ-041 / D6). Locks:
  1. create_practice_session freezes the picked questions + starts in_progress;
  2. add/list answers round-trip delivery JSON in order; save_practice_eval fills
     eval; save_practice_debrief sets debrief + status=done + completed_at;
  3. count_practice_sessions counts only DONE sessions;
  4. deleting the interview cascades sessions + answers away.
    .venv/bin/python tests/test_practice_db.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "prac.sqlite"
    db.init_db(p)
    return p


def test_practice_lifecycle():
    p = _fresh()
    iid = db.create_interview("cand1", "Acme", "DA", "jd", "en", "paste_text", path=p)
    qs = [{"id": "q1", "text": "Q1", "competency_id": "c1"},
          {"id": "q2", "text": "Q2", "competency_id": None}]
    sid = db.create_practice_session(iid, mode="study", length="quick",
                                     focus_competency="c1", questions=qs, path=p)
    s = db.get_practice_session(sid, path=p)
    _assert(s["status"] == "in_progress" and s["mode"] == "study", "starts in_progress/study")
    _assert(len(s["questions"]) == 2 and s["questions"][0]["id"] == "q1", "questions frozen")
    _assert(db.count_practice_sessions(iid, path=p) == 0, "no DONE sessions yet")

    a1 = db.add_practice_answer(sid, position=0, question_id="q1", question_text="Q1",
                                competency_id="c1", transcript="I led it", seconds=70,
                                delivery={"wpm": 120, "filler_count": 1}, path=p)
    db.add_practice_answer(sid, position=1, question_id="q2", question_text="Q2",
                           competency_id=None, transcript="Because", seconds=30,
                           delivery={"wpm": 90, "filler_count": 0}, path=p)
    answers = db.list_practice_answers(sid, path=p)
    _assert([a["position"] for a in answers] == [0, 1], "answers in order")
    _assert(answers[0]["delivery"]["wpm"] == 120, "delivery round-trips")
    _assert(answers[0]["eval"] is None, "eval empty until build")

    db.save_practice_eval(a1, {"overall": "solid", "fix": "add a number"}, path=p)
    _assert(db.list_practice_answers(sid, path=p)[0]["eval"]["overall"] == "solid", "eval saved")

    db.save_practice_debrief(sid, {"takeaway": "good", "competency_bands": []}, path=p)
    s = db.get_practice_session(sid, path=p)
    _assert(s["status"] == "done" and s["completed_at"], "debrief sets done + completed_at")
    _assert(s["debrief"]["takeaway"] == "good", "debrief round-trips")
    _assert(db.count_practice_sessions(iid, path=p) == 1, "one DONE session")
    print("PASS test_practice_lifecycle")


def test_practice_cascade():
    p = _fresh()
    iid = db.create_interview("cand1", "Acme", "DA", "jd", "en", "paste_text", path=p)
    sid = db.create_practice_session(iid, questions=[{"id": "q1", "text": "Q"}], path=p)
    db.add_practice_answer(sid, position=0, question_id="q1", question_text="Q",
                           competency_id=None, transcript="x", seconds=10, path=p)
    db.delete_interview(iid, path=p)
    _assert(db.get_practice_session(sid, path=p) is None, "session cascades on interview delete")
    _assert(db.list_practice_answers(sid, path=p) == [], "answers cascade too")
    print("PASS test_practice_cascade")


if __name__ == "__main__":
    test_practice_lifecycle()
    test_practice_cascade()
    print("all practice-db tests passed")
