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


def _render(debrief, delta=None, gauges=None):
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "app": None})
    return templates.get_template("pages/practice_feedback.html").render(
        request=req, active_tab="prep", interview={"id": 3, "role_title": "S", "company": "C"},
        session={"id": 39, "debrief": debrief, "transcript": [{"role": "you", "text": "x"}]},
        answers=[], comp_names={"c1": "Budget", "c2": "Workforce", "c3": "Stakeholder"},
        readiness={"level": "almost_ready", "pct": 78, "missing": "strengthen", "missing_count": 1},
        delta=delta, gauges=gauges or [], step="feedback")


def test_new_shape():
    tr = "In 2023 I cut overtime by 25 percent in six months. Um budgets are important you just have to manage them."
    raw = {"takeaway": "t", "top_actions": ["a"], "competency_evidence": [
        {"competency_id": "c1", "quote": "I cut overtime by 25 percent in six months", "checks": {k: True for k in SS.CHECKS}},
        {"competency_id": "c2", "quote": "budgets are important you just have to manage them", "checks": {k: True for k in SS.CHECKS}}]}
    d = PR._parse_debrief(raw, valid_comps={"c1", "c2", "c3"}, comp_ids=["c1", "c2", "c3"],
                          transcript=tr, asked_ids={"c1", "c2"}).to_dict()
    d["delivery"] = {"wpm": 140, "filler_count": 1, "seconds": 95, "word_count": 220, "pace": "on_target"}
    html = _render(d, delta=12, gauges=SS.delivery_gauges(words=220, seconds=95, fillers=6, answer_seconds=[50, 45]))
    _assert("Session score" in html and "Getting close" in html, "score hero")
    _assert("+12 vs last session" in html and "Not asked" in html, "delta + not asked")
    _assert("1 weak competency" in html, "singular readiness copy")
    _assert("Easy to follow" in html and "per 100 words" in html and "about 150 words per minute" in html,
            "gauges show verdict + unit + the research baseline")
    print("PASS test_new_shape")


def test_legacy_shape():
    d = {"takeaway": "t", "competency_bands": [{"competency_id": "c1", "band": "solid"}], "top_actions": ["a"],
         "delivery": {"wpm": 305, "filler_count": 4, "pace": "fast", "confidence": "medium"}}
    html = _render(d)
    _assert("Session score" not in html and "Coach" in html, "legacy → takeaway eyebrow, no score")
    print("PASS test_legacy_shape")


def test_voice_length_gauge_both_shapes():
    """ADR-071: voice sessions with answer_seconds get a length gauge; older
    voice sessions (no answer_seconds) keep pace + fillers and don't crash."""
    from ui_web.routes.interviews import _delivery_gauges
    base = {"word_count": 290, "seconds": 120, "filler_count": 4}
    new = {"transcript": [{"role": "you", "text": "x"}],
           "debrief": {"delivery": {**base, "answer_seconds": [70, 50]}}}
    old = {"transcript": [{"role": "you", "text": "x"}], "debrief": {"delivery": base}}
    g_new = {x["key"]: x for x in _delivery_gauges(new, [])}
    g_old = {x["key"]: x for x in _delivery_gauges(old, [])}
    _assert(g_new["length"]["display"] == "1:00", f"avg of 70+50 → 1:00, got {g_new.get('length')}")
    _assert("length" not in g_old and "pace" in g_old, "legacy voice → pace only, no length")
    _render({"takeaway": "t", "top_actions": ["a"]}, gauges=list(g_new.values()))
    print("PASS test_voice_length_gauge_both_shapes")



def _req():
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "app": None})


def test_history_and_empty_state():
    """REQ-050: past sessions listed (this one marked); Feedback before any session explains itself."""
    hist = [{"id": 40, "status": "done", "completed_at": "2026-10-10T21:22:41Z", "debrief": {"score": 72}, "transcript_json": "[]"},
            {"id": 39, "status": "done", "completed_at": "2026-10-08T00:07:00Z", "debrief": None, "transcript_json": None}]
    req = _req()
    html = templates.get_template("pages/practice_feedback.html").render(
        request=req, active_tab="prep", interview={"id": 3, "role_title": "S", "company": "C"},
        session={"id": 39, "debrief": {"takeaway": "t"}, "transcript": None}, answers=[], comp_names={},
        readiness={"level": "almost_ready", "pct": 78, "missing": "strengthen", "missing_count": 1},
        delta=None, gauges=[], step="feedback", history=hist)
    _assert("Past sessions" in html and "/practice/40/feedback" in html and "viewing" in html, "history listed, current marked")
    empty = templates.get_template("pages/feedback_empty.html").render(
        request=req, active_tab="prep", interview={"id": 3, "role_title": "S", "company": "C"}, step="feedback")
    _assert("No practice sessions yet." in empty and "/interviews/3/practice" in empty, "empty state with CTA")
    print("PASS test_history_and_empty_state")


def test_setup_topics_checklist():
    """REQ-050: setup is a checklist (about you + each competency), all checked by default."""
    html = templates.get_template("pages/practice_setup.html").render(
        request=_req(), active_tab="prep", interview={"id": 3, "role_title": "S", "company": "C"}, step="practice",
        missed_count=2, checked=["c1", "c2", PR.ABOUT_YOU], about_you=PR.ABOUT_YOU,
        competencies=[{"id": "c1", "name": "Budget"}, {"id": "c2", "name": "Workforce"}],
        voice_enabled=False, voices={}, default_voice="x", personalities={}, default_personality="y")
    _assert(html.count('name="topics"') == 3 and "About you" in html and "Budget" in html, "checklist items")
    _assert("{n} questions" in html and "Start with the 2 answers I missed" in html, "count + missed option")
    _assert('href="/interviews/3/feedback"' in html, "stepper links Feedback from Practice")
    _assert('name="length"' not in html and 'name="focus"' not in html, "old pickers gone")
    print("PASS test_setup_topics_checklist")


def test_live_talking_points():
    """REQ-050: live aid = one big line per point, no STAR labels, point to land last."""
    frame = [{"section": "situation", "points": ["At the CRA we lacked visibility."]},
             {"section": "result", "points": ["I saved 60+ staff hours a month."]}]
    html = templates.get_template("partials/live_talking_points.html").render(frame=frame, point="I build tools that save hours.")
    _assert(html.count("<li>") == 2 and "saved 60+" in html and "live-points__land" in html, "points + land")
    _assert("Situation" not in html and "script__cue" not in html, "no section labels")
    print("PASS test_live_talking_points")

if __name__ == "__main__":
    test_new_shape()
    test_legacy_shape()
    test_voice_length_gauge_both_shapes()
    test_history_and_empty_state()
    test_setup_topics_checklist()
    test_live_talking_points()
    print("all feedback-render tests passed")
