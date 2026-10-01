"""Practice Feedback page renders for BOTH debrief shapes (ADR-059):
  1. new — score + competency_evidence → score hero, checks, Not asked;
  2. legacy — bands only (pre-ADR-059 sessions) → no score, no crash.
    .venv/bin/python tests/test_practice_feedback_render.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.requests import Request  # noqa: E402

from core.prep import practice as PR, session_score as SS  # noqa: E402
from ui_web.deps import templates  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


def _render(debrief, delta=None):
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "app": None})
    return templates.get_template("pages/practice_feedback.html").render(
        request=req, active_tab="prep", interview={"id": 3, "role_title": "S", "company": "C"},
        session={"id": 39, "debrief": debrief, "transcript": [{"role": "you", "text": "x"}]},
        answers=[], comp_names={"c1": "Budget", "c2": "Workforce", "c3": "Stakeholder"},
        readiness={"level": "almost_ready", "pct": 78, "missing": "strengthen", "missing_count": 1},
        delta=delta, step="feedback")


def test_new_shape():
    tr = "In 2023 I cut overtime by 25 percent in six months. Um budgets are important you just have to manage them."
    raw = {"takeaway": "t", "top_actions": ["a"], "competency_evidence": [
        {"competency_id": "c1", "quote": "I cut overtime by 25 percent in six months", "checks": {k: True for k in SS.CHECKS}},
        {"competency_id": "c2", "quote": "budgets are important you just have to manage them", "checks": {k: True for k in SS.CHECKS}}]}
    d = PR._parse_debrief(raw, valid_comps={"c1", "c2", "c3"}, comp_ids=["c1", "c2", "c3"],
                          transcript=tr, asked_ids={"c1", "c2"}).to_dict()
    d["delivery"] = {"wpm": 140, "filler_count": 1, "seconds": 95, "word_count": 220, "pace": "on_target"}
    html = _render(d, delta=12)
    _assert("Session score" in html and "Getting close" in html, "score hero")
    _assert("+12 vs last session" in html and "Not asked" in html, "delta + not asked")
    _assert("1 weak competency" in html, "singular readiness copy")
    print("PASS test_new_shape")


def test_legacy_shape():
    d = {"takeaway": "t", "competency_bands": [{"competency_id": "c1", "band": "solid"}], "top_actions": ["a"],
         "delivery": {"wpm": 305, "filler_count": 4, "pace": "fast", "confidence": "medium"}}
    html = _render(d)
    _assert("Session score" not in html and "Coach" in html, "legacy → takeaway eyebrow, no score")
    print("PASS test_legacy_shape")


if __name__ == "__main__":
    test_new_shape()
    test_legacy_shape()
    print("all feedback-render tests passed")
