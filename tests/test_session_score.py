"""Practice session score (ADR-059 / REQ-0xx). Locks:
  1. a quote that isn't in the transcript zeroes the competency (anti-inflation);
  2. answered=false → 0 points whatever else the model ticked;
  3. quantified needs a number IN the quote;
  4. bands are derived from points (5 strong · 3–4 solid · 0–2 needs_work);
  5. not-asked competencies are shown but excluded from the denominator;
  6. junk answers can't reach "solid" even if the model says yes to everything
     it can't quote;
  7. P9 parse builds score + bands from evidence; legacy bands still parse;
  8. delta vs the previous scored session.
    .venv/bin/python tests/test_session_score.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.prep import practice as PR  # noqa: E402
from core.prep import session_score as SS  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


ALL_YES = {k: True for k in SS.CHECKS}
GOOD = ("In 2023 I rebuilt the capacity model for our 40-person IT team and I cut "
        "overtime by 25 percent in six months by moving two projects.")
JUNK = "Um yeah I mean budgets are important you just have to manage them you know."


def test_quote_gate():
    _assert(SS.verify_quote("I rebuilt the capacity model", GOOD), "exact substring verifies")
    _assert(SS.verify_quote("i REBUILT the capacity-model for our team", GOOD), "case/punct drift verifies")
    _assert(not SS.verify_quote("I led a 2M dollar budget turnaround for finance", GOOD), "invented quote fails")
    _assert(not SS.verify_quote("I rebuilt", GOOD), "too short to be evidence")
    g = SS.grade_item({"competency_id": "c1", "quote": "I led a 2M budget turnaround at finance",
                       "checks": ALL_YES}, GOOD)
    _assert(g["points"] == 0 and not g["verified"] and g["quote"] == "", "unverified quote → 0, quote hidden")
    print("PASS test_quote_gate")


def test_answered_and_quantified_gates():
    g = SS.grade_item({"competency_id": "c1", "quote": "I rebuilt the capacity model for our",
                       "checks": {**ALL_YES, "answered": False}}, GOOD)
    _assert(g["points"] == 0, "answered=false → 0")
    g = SS.grade_item({"competency_id": "c1", "quote": "I rebuilt the capacity model for our",
                       "checks": ALL_YES}, GOOD)
    _assert(g["points"] == 4 and not g["checks"]["quantified"], "no number in quote → quantified false")
    g = SS.grade_item({"competency_id": "c1", "quote": "I cut overtime by 25 percent in six months",
                       "checks": ALL_YES}, GOOD)
    _assert(g["points"] == 5, "number in quote → full marks")
    print("PASS test_answered_and_quantified_gates")


def test_own_actions_gate():
    g = SS.grade_item({"competency_id": "c1", "quote": "the team rebuilt the capacity model for everyone",
                       "checks": ALL_YES}, "the team rebuilt the capacity model for everyone")
    _assert(not g["checks"]["own_actions"], "'the team' ≠ own actions")
    print("PASS test_own_actions_gate")


def test_bands_and_verdicts():
    _assert([SS.band_for(p) for p in range(6)] ==
            ["needs_work", "needs_work", "needs_work", "needs_work", "solid", "strong"], "band ladder")
    _assert(SS.verdict_for(74) == "close" and SS.verdict_for(75) == "ready"
            and SS.verdict_for(49) == "not_ready", "verdict thresholds")
    _assert(SS.pace_for(305) == "fast" and SS.pace_for(140) == "on_target" and SS.pace_for(90) == "slow", "pace")
    print("PASS test_bands_and_verdicts")


def test_not_asked_excluded():
    graded = [SS.grade_item({"competency_id": "c1", "quote": "I cut overtime by 25 percent in six months",
                             "checks": ALL_YES}, GOOD)]
    out = SS.aggregate(graded, competency_ids=["c1", "c2", "c3"], asked_ids={"c1", "c2"})
    ev = {e["competency_id"]: e for e in out["competency_evidence"]}
    _assert(ev["c3"]["band"] == "not_asked", "never asked → not_asked")
    _assert(ev["c2"]["band"] == "needs_work" and ev["c2"]["points"] == 0, "asked but no evidence → 0")
    _assert(out["score"] == 50, f"5 / (5×2) = 50, got {out['score']}")
    _assert([b["competency_id"] for b in out["competency_bands"]] == ["c1", "c2"], "bands only for asked")
    _assert(SS.aggregate([], competency_ids=["c1"], asked_ids=set()) is None, "nothing asked → no score")
    print("PASS test_not_asked_excluded")


def test_junk_session_cannot_be_solid():
    # The model is lenient (says yes to everything) but can only quote junk.
    raw = {"takeaway": "x", "top_actions": [],
           "competency_evidence": [
               {"competency_id": "c1", "asked": True, "quote": "budgets are important you just have to manage them",
                "checks": ALL_YES},
               {"competency_id": "c2", "asked": True, "quote": "I built a forecasting dashboard that saved 300 hours",
                "checks": ALL_YES},  # hallucinated — not in transcript
           ]}
    d = PR._parse_debrief(raw, valid_comps={"c1", "c2"}, comp_ids=["c1", "c2"],
                          transcript=JUNK, asked_ids={"c1", "c2"})
    # c1's quote is real but has no number and no "I" → 3/5 max even if the
    # model ticks everything → needs_work. c2's quote is invented → 0.
    bands = {b["competency_id"]: b["band"] for b in d.competency_bands}
    _assert(bands == {"c1": "needs_work", "c2": "needs_work"}, f"junk can't be solid: {bands}")
    _assert(d.score is not None and d.score <= 30, f"junk session scores low, got {d.score}")
    honest = {**raw, "competency_evidence": [
        {"competency_id": "c1", "asked": True, "quote": "budgets are important you just have to manage them",
         "checks": {k: False for k in SS.CHECKS}}]}
    d2 = PR._parse_debrief(honest, valid_comps={"c1", "c2"}, comp_ids=["c1", "c2"],
                           transcript=JUNK, asked_ids={"c1", "c2"})
    _assert(d2.score == 0 and d2.verdict_key == "not_ready", "honest junk → 0")
    _assert(PR._parse_debrief(raw, valid_comps={"c1", "c2"}, comp_ids=["c1", "c2"],
                              transcript=JUNK, asked_ids={"c1", "c2"}).score == d.score, "deterministic")
    print("PASS test_junk_session_cannot_be_solid")


def test_typed_path_best_answer_per_competency():
    ev_weak = PR._parse_eval({"checks": {**ALL_YES, "answered": False}, "evidence_quote": "I rebuilt the capacity model",
                              "overall": "strong"}, question_id="q1", transcript=GOOD, competency_id="c1")
    _assert(ev_weak.overall == "needs_work", "P8 overall derived from checks, not the model's 'strong'")
    ev_good = PR._parse_eval({"checks": ALL_YES, "evidence_quote": "I cut overtime by 25 percent in six months",
                              "overall": "solid"}, question_id="q2", transcript=GOOD, competency_id="c1")
    _assert(ev_good.overall == "strong", "full checks → strong")
    d = PR._parse_debrief({"takeaway": "t"}, valid_comps={"c1"}, comp_ids=["c1"],
                          graded=[ev_weak.evidence, ev_good.evidence], asked_ids={"c1"})
    _assert(d.score == 100, "best answer per competency counts")
    print("PASS test_typed_path_best_answer_per_competency")


def test_legacy_bands_still_parse():
    d = PR._parse_debrief({"competency_bands": [{"competency_id": "c1", "band": "solid"}]}, valid_comps={"c1"})
    _assert(d.score is None and d.competency_bands[0]["band"] == "solid", "legacy → no score, bands kept")
    print("PASS test_legacy_bands_still_parse")


def test_delta():
    sessions = [  # newest first
        {"id": 3, "status": "done", "debrief": {"score": 62}},
        {"id": 2, "status": "abandoned", "debrief": None},
        {"id": 1, "status": "done", "debrief": {"score": 50}},
    ]
    _assert(SS.delta_vs_previous(sessions, 3) == 12, "delta vs last scored session")
    _assert(SS.delta_vs_previous(sessions, 1) is None, "first session → no delta")
    _assert(SS.delta_vs_previous([{"id": 3, "status": "done", "debrief": {}}], 3) is None, "legacy → none")
    print("PASS test_delta")


def test_ready_needs_no_weak_competency():
    strong = SS.grade_item({"competency_id": "c1", "quote": "I cut overtime by 25 percent in six months",
                            "checks": ALL_YES}, GOOD)
    weak = SS.grade_item({"competency_id": "c2", "quote": "I rebuilt the capacity model for our",
                          "checks": {**ALL_YES, "result": False, "quantified": False}}, GOOD)
    out = SS.aggregate([strong, weak], competency_ids=["c1", "c2"], asked_ids={"c1", "c2"})
    _assert(out["score"] == 80 and out["verdict_key"] == "close", f"80 with a weak spot → close, got {out}")
    print("PASS test_ready_needs_no_weak_competency")


if __name__ == "__main__":
    test_quote_gate()
    test_answered_and_quantified_gates()
    test_own_actions_gate()
    test_bands_and_verdicts()
    test_not_asked_excluded()
    test_junk_session_cannot_be_solid()
    test_typed_path_best_answer_per_competency()
    test_legacy_bands_still_parse()
    test_delta()
    test_ready_needs_no_weak_competency()
    print("all session-score tests passed")
