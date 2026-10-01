"""The one-call Get Ready toolkit (ADR-057). Locks down:

  1. parsing validates every join in code: questions re-id'd q1..qN, bad type →
     behavioral, unknown competency → null; story picks: unknown / duplicate
     competency dropped, unknown story id → no story, a draft only when there is
     no story, every brief competency gets a row; questions-to-ask keep why/shows;
  2. the prompt is first person, carries the candidate's fact answers, the Story
     Bank ids and the brief competencies;
  3. generate → cache; a changed fact answer or story is a miss (fingerprint);
  4. read_cached_toolkit / read_cached_mapping never generate;
  5. the pipeline: P1 then the toolkit — 2 LLM calls total, a second build is
     all cache, a failing toolkit call degrades to None.

No network: a fake GeminiClient supplies the JSON.
    .venv/bin/python tests/test_prep_toolkit.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.prep import pipeline as PL  # noqa: E402
from core.prep import toolkit as T  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


class _FakeClient:
    def __init__(self, payload=None, raise_exc=None):
        self.payload, self.raise_exc, self.calls = payload, raise_exc, 0
        self.last_model_used = self.model_name = "fake"
        self.prompts: list[str] = []

    def all_models_exhausted(self):
        return False

    def generate_json(self, prompt, *, temperature=None, max_retries=2):
        self.calls += 1
        self.prompts.append(prompt)
        if self.raise_exc:
            raise self.raise_exc
        return self.payload


_BRIEF = {
    "role_summary": "Own IT budgets.",
    "competencies": [
        {"id": "c1", "name": "Budgeting", "what_good_looks_like": "tracks spend", "resume_match": "solid"},
        {"id": "c2", "name": "Stakeholders", "what_good_looks_like": "aligns", "resume_match": "needs_work"},
        {"id": "c3", "name": "Reporting", "what_good_looks_like": "clear", "resume_match": "strong"},
    ],
    "clarify_questions": [{"id": "f1", "question": "How big was the budget?", "example": "scale"}],
}
_TOOLKIT = {
    "questions": [
        {"text": "Tell me about yourself.", "type": "opener", "competency_id": None,
         "why_they_ask": "warm up", "follow_up": "why us?", "point_to_land": "finance + data",
         "frame": [{"section": "now", "points": ["I lead finance analytics at CRA."]},
                   {"section": "why_here", "points": ["Housing mission."]}]},
        {"text": "How do you approach managing budgets?", "type": "approach", "competency_id": "c1",
         "why_they_ask": "scale", "follow_up": "overruns?", "point_to_land": "I own budgets",
         "frame": [{"section": "approach", "points": ["I split opex and capex [[hint: your cadence — e.g. monthly variance review]]",
                                                      "I give each cost driver an owner", "p3", "p4 over cap"]},
                   {"section": "situation", "points": ["not in the approach template"]},
                   {"section": "result", "points": ["$3M+ in savings"]}]},
        {"text": "Bad competency.", "type": "trivia", "competency_id": "c99",
         "frame": [{"section": "action", "points": ["We ensured alignment effectively."]}]},
        {"text": "", "type": "opener"},
    ],
    "stories": [
        {"competency_id": "c1", "story_id": "SID", "why_it_fits": "fits", "angle_for_this_role": "lead with $"},
        {"competency_id": "c2", "story_id": "999", "why_it_fits": "bad id",
         "draft": {"title": "Aligning HR", "situation": "s", "task": "t", "action": "I led", "result": "done",
                   "metric": "null"}},
        {"competency_id": "c1", "story_id": None},          # duplicate → dropped
        {"competency_id": "cZ", "story_id": None},          # unknown → dropped
    ],
    "questions_to_ask": [
        {"question": "What does success look like in 90 days?", "why": "shows focus", "shows": "results focus"},
        "A bare string question",
        {"question": ""},
    ],
}


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "tk.sqlite"
    db.init_db(p)
    return p


def _seed(p: Path) -> tuple[dict, list[dict], int]:
    iid = db.create_interview("cand1", "CMHC", "IT Finance", "Own IT budgets.", "en", "pasted_text", path=p)
    sid = db.create_story("cand1", title="CRA dashboards", situation="s", task="t", action="I built",
                          result="saved 60h", metric="60h", path=p)
    return db.get_interview(iid, path=p), db.list_stories("cand1", status="saved", path=p), sid


def _payload_with(sid: int) -> dict:
    import copy
    d = copy.deepcopy(_TOOLKIT)
    d["stories"][0]["story_id"] = str(sid)
    return d


def test_parse_validates_joins():
    tk = T._parse_toolkit(_payload_with(7), valid_comps={"c1", "c2", "c3"}, valid_stories={"7"},
                          all_comps=["c1", "c2", "c3"])
    _assert([q.id for q in tk.questions] == ["q1", "q2", "q3"], f"dense re-id, blank dropped: {tk.questions}")
    q_open, q_how, q_bad = tk.questions
    _assert(q_how.type == "approach", "approach type kept")
    _assert([f["section"] for f in q_how.frame] == ["approach", "result"], f"template sections only, got {q_how.frame}")
    _assert(len(q_how.frame[0]["points"]) == T.MAX_POINTS, "bullets capped")
    _assert(q_how.needs_input and not q_how.filler, "a hint slot → needs_input")
    _assert(q_bad.type == "behavioral" and q_bad.competency_id is None, "bad type → behavioral, unknown comp → null")
    _assert(q_bad.filler == ["effectively", "ensured alignment"] and q_bad.needs_input, "filler detected → needs_input")
    _assert(not q_open.needs_input, "a clean skeleton needs no input")
    _assert(T.FRAMES["behavioral"] == ("situation", "task", "action", "result"), "behavioral is full STAR (the T is back)")
    beh = T._parse_frame([{"section": s_, "points": [s_]} for s_ in ("result", "task", "situation", "action")], "behavioral")
    _assert([f["section"] for f in beh] == ["situation", "task", "action", "result"], "STAR order enforced")
    by = {s.competency_id: s for s in tk.stories}
    _assert(list(by) == ["c1", "c2", "c3"], f"dup/unknown dropped, missing added, got {list(by)}")
    _assert(by["c1"].story_id == "7" and by["c1"].angle_for_this_role == "lead with $", "valid story kept")
    _assert(by["c2"].story_id is None and by["c2"].why_it_fits is None, "unknown story → no story, why dropped")
    _assert(by["c2"].draft and by["c2"].draft["metric"] is None, "draft kept, 'null' metric → None")
    _assert(by["c3"].story_id is None and by["c3"].draft is None, "missing competency → empty gap row")
    _assert([a.shows for a in tk.questions_to_ask] == ["results focus", ""], "why/shows kept; bare string ok")
    print("PASS test_parse_validates_joins")


def test_hints_split_and_prompt_rules():
    _assert(T.split_hints("I track opex [[hint: cadence]] and more") ==
            [("t", "I track opex "), ("h", "cadence"), ("t", " and more")], "hint split")
    _assert(T.split_hints("unclosed [[hint: x") == [("t", "unclosed [[hint: x")], "unclosed hint stays text")
    prompt = T._build_prompt({"company": "C", "role_title": "R"}, _BRIEF, [], {}, "résumé", lang="en")
    _assert("NOT prose" in prompt and "[[hint:" in prompt, "skeleton + hint slot instructions")
    _assert('approach / situational → "approach"' in prompt, "per-type sections spelled out")
    _assert("Never use these filler words" in prompt, "filler ban")
    print("PASS test_hints_split_and_prompt_rules")


def test_prompt_first_person_facts_and_ids():
    p = _fresh()
    interview, stories, sid = _seed(p)
    T.save_facts(interview["id"], {"How big was the budget?": "$4M across 3 programs", "Other?": "  "}, path=p)
    _assert(T.read_facts(interview["id"], path=p) == {"How big was the budget?": "$4M across 3 programs"},
            "keyed by question text; blank answers dropped")
    prompt = T._build_prompt(interview, _BRIEF, stories, T.read_facts(interview["id"], path=p), "résumé", lang="en")
    _assert("first person" in prompt and "Never use my name" in prompt, "first person, no name")
    _assert("MY CLARIFICATIONS" in prompt and "Q: How big was the budget?" in prompt
            and "A (my own words): $4M across 3 programs" in prompt,
            "fact answers in context")
    _assert("Never add numbers together" in prompt and "not \"25% of the budget\"" in prompt,
            "number-fidelity rule present")
    _assert("at most 15 words" in prompt, "questions to ask kept short")
    _assert(f"- {sid}: CRA dashboards" in prompt, "Story Bank ids offered")
    _assert('"id": "c2"' in prompt, "brief competencies with ids")
    print("PASS test_prompt_first_person_facts_and_ids")


def test_facts_submitted_tracks_the_question_set():
    p = _fresh()
    interview, _stories, _sid = _seed(p)
    iid, qs = interview["id"], ["How did you track spend?", "Which tool?"]
    _assert(not T.facts_submitted(iid, qs, path=p), "nothing saved yet")
    T.save_facts(iid, {}, asked=qs, path=p)
    _assert(not T.facts_submitted(iid, qs, path=p), "a marker with no answers and no skip is NOT done (old skip bug)")
    T.save_facts(iid, {}, asked=qs, skipped=True, path=p)
    _assert(T.facts_submitted(iid, qs, path=p), "an explicit skip counts for this set")
    _assert(not T.facts_submitted(iid, ["A new question?"], path=p), "a new question set asks again")
    _assert(T.read_facts(iid, path=p) == {}, "the marker is never read as an answer")
    T.save_facts(iid, {"How did you track spend?": "weekly SAP pull"}, path=p)   # legacy row, no marker
    _assert(T.facts_submitted(iid, qs, path=p), "a legacy row answering these questions counts")
    _assert(not T.facts_submitted(iid, ["Other?"], path=p), "…but not for other questions")
    print("PASS test_facts_submitted_tracks_the_question_set")


def test_card_gaps_become_questions():
    tk = T.Toolkit(questions=[T.ToolkitQuestion(
        id="q1", text="How do you approach budgets?", type="approach", competency_id=None,
        frame=[{"section": "approach", "points": [
            "I review targets [[hint: specify your review cadence — e.g. monthly variance review in Excel]].",
            "Again [[hint: specify your review cadence — e.g. monthly variance review in Excel]]",
            "x [[hint: detail your method]]"]}])])
    gaps = T.card_gaps(tk)
    _assert(len(gaps) == 2, f"one question per distinct gap, got {gaps}")
    _assert(gaps[0]["question"] == "Specify your review cadence" and gaps[0]["example"] == "monthly variance review in Excel",
            "hint split into question + e.g. example")
    _assert(gaps[0]["key"] == T.gap_key("How do you approach budgets?", "specify your review cadence — e.g. monthly variance review in Excel"),
            "same key as the card's inline field")
    _assert(gaps[1]["example"] == "", "no e.g. → no example")
    print("PASS test_card_gaps_become_questions")


def test_generate_cache_and_fingerprint():
    p = _fresh()
    interview, stories, sid = _seed(p)
    c = _FakeClient(payload=_payload_with(sid))
    tk = T.get_or_generate_toolkit(interview, _BRIEF, stories, "résumé", c, lang="en", path=p)
    _assert(tk is not None and len(tk.questions) == 3 and c.calls == 1, "miss generates")
    T.get_or_generate_toolkit(interview, _BRIEF, stories, "résumé", c, lang="en", path=p)
    _assert(c.calls == 1, "same inputs → cache hit")
    T.save_facts(interview["id"], {"How big was the budget?": "$4M"}, path=p)
    T.get_or_generate_toolkit(interview, _BRIEF, stories, "résumé", c, lang="en", path=p)
    _assert(c.calls == 2, "a new fact answer → miss")
    edited = [dict(stories[0], result="saved 80h")]
    T.get_or_generate_toolkit(interview, _BRIEF, edited, "résumé", c, lang="en", path=p)
    _assert(c.calls == 3, "an edited story → miss")
    none = _FakeClient(payload=_TOOLKIT)
    _assert(T.get_or_generate_toolkit(interview, {"competencies": []}, stories, "r", none, lang="en", path=p) is None
            and none.calls == 0, "no competencies → None, no call")
    print("PASS test_generate_cache_and_fingerprint")


_MERGED = dict(_BRIEF, **{"company_snapshot": [], "gaps": [], "interviewer_lens": [], "friction_points": []})
_MERGED["competencies"] = [dict(c, id="x" + c["id"]) for c in _BRIEF["competencies"]]  # P1 re-ids to c1..c3
_MERGED["clarify_questions"] = [{"question": "How big was the budget?", "example": "scale"}]


def _merged(sid: int) -> dict:
    return {**_MERGED, **_payload_with(sid)}


def test_pipeline_two_calls_then_cache_and_reads():
    p = _fresh()
    interview, stories, sid = _seed(p)
    made: list[_FakeClient] = []

    def make():
        made.append(_FakeClient(payload=_merged(sid)))
        return made[-1]

    res = asyncio.run(PL.build_toolkit(interview, "résumé", make_client=make, stories=stories, lang="en", path=p))
    _assert(res.brief_ready and res.toolkit is not None, "brief + toolkit built")
    _assert(sum(c.calls for c in made) == 2, f"exactly 2 LLM calls (P1 + toolkit), got {sum(c.calls for c in made)}")
    _assert(db.get_interview(interview["id"], path=p)["status"] == "toolkit_ready", "status advanced")
    # cache-only readers
    cached = T.read_cached_toolkit(interview["id"], stories, lang="en", path=p)
    _assert(cached is not None and [q.id for q in cached.questions] == ["q1", "q2", "q3"], "read_cached_toolkit hits")
    picks = T.read_cached_mapping(interview["id"], stories, lang="en", path=p)
    _assert(picks and picks[0].story_id == str(sid), "read_cached_mapping exposes the P3 contract")
    made.clear()
    asyncio.run(PL.build_toolkit(interview, "résumé", make_client=make, stories=stories, lang="en", path=p))
    _assert(sum(c.calls for c in made) == 0, "second build is all cache")
    print("PASS test_pipeline_two_calls_then_cache_and_reads")


def test_toolkit_failure_degrades():
    p = _fresh()
    interview, stories, sid = _seed(p)
    n = {"i": 0}

    def make():
        n["i"] += 1
        return _FakeClient(payload=_merged(sid)) if n["i"] == 1 else _FakeClient(raise_exc=RuntimeError("boom"))

    res = asyncio.run(PL.build_toolkit(interview, "résumé", make_client=make, stories=stories, lang="en", path=p))
    _assert(res.brief_ready and res.toolkit is None, "brief kept, toolkit → None")
    _assert(T.read_cached_toolkit(interview["id"], stories, lang="en", path=p) is None, "nothing cached on failure")
    print("PASS test_toolkit_failure_degrades")


if __name__ == "__main__":
    test_parse_validates_joins()
    test_hints_split_and_prompt_rules()
    test_prompt_first_person_facts_and_ids()
    test_facts_submitted_tracks_the_question_set()
    test_card_gaps_become_questions()
    test_generate_cache_and_fingerprint()
    test_pipeline_two_calls_then_cache_and_reads()
    test_toolkit_failure_degrades()
    print("all toolkit tests passed")
