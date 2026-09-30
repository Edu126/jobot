"""Answer-card self-ratings (ADR-056): append-only, latest wins, bad ratings
refused, and a rating never survives onto a DIFFERENT question text.

Runs without pytest:
    .venv/bin/python tests/test_card_reviews.py
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


def main() -> int:
    p = Path(tempfile.mkdtemp()) / "cards.sqlite"
    db.init_db(p)
    iid = db.create_interview("cand1", "Acme", "Analyst", "jd", "en", "pasted_text", path=p)

    _assert(db.latest_card_reviews(iid, path=p) == {}, "no reviews yet")
    _assert(db.save_card_review(iid, "q1", "Tell me about X", "missed", path=p), "missed saved")
    _assert(db.save_card_review(iid, "q1", "Tell me about X", "got_it", path=p), "got_it saved")
    _assert(db.save_card_review(iid, "q2", "Why us?", "missed", path=p), "q2 saved")
    _assert(not db.save_card_review(iid, "q3", "x", "meh", path=p), "unknown rating refused")
    _assert(not db.save_card_review(iid, "", "x", "missed", path=p), "blank id refused")

    latest = db.latest_card_reviews(iid, path=p)
    _assert(latest["q1"]["rating"] == "got_it", "latest rating wins")
    _assert(latest["q2"] == {"rating": "missed", "question_text": "Why us?"}, "text kept with the rating")
    _assert("q3" not in latest, "refused rating not stored")

    # the route's join: a regenerated P2 re-using q2 for a new question must not inherit the rating
    from ui_web.routes.interviews import _missed_question_ids
    import core.db as live_db
    orig = live_db.latest_card_reviews
    live_db.latest_card_reviews = lambda i, path=None: latest  # route reads the default DB path
    try:
        same = _missed_question_ids(iid, [{"id": "q2", "text": "Why us?"}])
        moved = _missed_question_ids(iid, [{"id": "q2", "text": "A new question"}])
    finally:
        live_db.latest_card_reviews = orig
    _assert(same == {"q2"}, "missed card on the same question counts")
    _assert(moved == set(), "same id, different text → not missed")

    print("OK — card reviews verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
