"""Prep AI pipeline P1 Brief + P2 Questions (REQ-041 / ADR-048). Locks down:

  1. Brief parsing: competencies re-id'd dense c1..cN, unknown/blank band →
     needs_work (never rounded up), snapshot/gaps/str-lists well-formed & capped,
     garbage is safe, a brief with no competencies is_empty;
  2. Questions parsing: re-id q1..qN, bad type → behavioral, a competency_id the
     brief didn't define is NULLED (no dangling join), cap at MAX_QUESTIONS;
  3. get_or_generate_brief / _questions generate + cache on a miss, second call
     is a cache hit (no re-generation);
  4. empty brief → None; questions fan out on the brief's competency ids.

No network: a fake GeminiClient supplies the JSON.
    .venv/bin/python tests/test_prep_pipeline.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.prep import brief as B  # noqa: E402
from core.prep import flashcards as F  # noqa: E402
from core.prep import mapping as M  # noqa: E402
from core.prep import prompts as P  # noqa: E402
from core.prep import questions as Q  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


class _FakeClient:
    def __init__(self, payload=None, raise_exc=None):
        self.payload = payload
        self.raise_exc = raise_exc
        self.calls = 0
        self.last_model_used = "fake"
        self.model_name = "fake"

    def all_models_exhausted(self):
        return False

    def generate_json(self, prompt, *, temperature=None, max_retries=2):
        self.calls += 1
        if self.raise_exc:
            raise self.raise_exc
        return self.payload


_BRIEF = {
    "role_summary": "Own the analytics stack. Partner with product on metrics.",
    "company_snapshot": [
        {"point": "Series B fintech, 300 people", "source_url": "https://x.com/a"},
        {"point": "no url still keeps the point", "source_url": None},
        {"point": "", "source_url": "https://x.com/drop"},  # dropped: no point
    ],
    "competencies": [
        {"id": "cX", "name": "Stakeholder management",
         "what_good_looks_like": "aligns partners", "resume_match": "strong",
         "evidence": "Led 3 cross-team launches"},
        {"id": "c99", "name": "SQL depth", "what_good_looks_like": "writes complex joins",
         "resume_match": "banana", "evidence": None},          # bad band → needs_work
        {"name": "", "what_good_looks_like": "x"},               # dropped: no name
    ],
    "gaps": [
        {"competency_id": "c2", "gap": "no dbt experience", "action": "read the dbt primer"},
        {"competency_id": None, "gap": "", "action": "x"},       # dropped: no gap
    ],
    "interviewer_lens": ["cares about impact", "", "cares about rigor", "extra", "over-cap"],
    "friction_points": ["gap in fintech domain"],
}

_QUESTIONS = {
    "questions": [
        {"id": "qZ", "text": "Tell me about yourself.", "type": "opener",
         "competency_id": None, "why_they_ask": "warm up", "follow_up": "what drew you here?"},
        {"id": "q7", "text": "Walk me through a stakeholder conflict.", "type": "behavioral",
         "competency_id": "c1", "why_they_ask": "probe alignment", "follow_up": "what did you do?"},
        {"id": "q8", "text": "Bad type falls back.", "type": "trivia",
         "competency_id": "c99", "why_they_ask": "x", "follow_up": "y"},  # type→behavioral, cid nulled
        {"text": "", "type": "opener"},                                    # dropped: no text
    ]
}


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "prep.sqlite"
    db.init_db(p)
    return p


def _seed_interview(p: Path) -> int:
    return db.create_interview(
        "cand1", "Acme", "Data Analyst", "Analyze product data and build dashboards.",
        "en", "pasted_text", round_type="behavioral", path=p)


# ---- brief parsers ----

def test_brief_parse_reids_and_bands():
    b = B._parse_brief(_BRIEF)
    _assert([c.id for c in b.competencies] == ["c1", "c2"], f"dense re-id, got {[c.id for c in b.competencies]}")
    _assert(b.competencies[0].resume_match == "strong", "valid band kept")
    _assert(b.competencies[1].resume_match == "needs_work", "unknown band → needs_work (never rounded up)")
    _assert(b.competencies[1].evidence is None, "null evidence stays None")
    _assert(len(b.company_snapshot) == 2, "empty-point snapshot item dropped")
    _assert(b.company_snapshot[1].source_url is None, "missing url → None")
    _assert(len(b.gaps) == 1 and b.gaps[0].gap.startswith("no dbt"), "only well-formed gap kept")
    _assert(b.interviewer_lens == ["cares about impact", "cares about rigor", "extra"], "blanks dropped, capped at 3")
    _assert(not b.is_empty(), "brief with competencies is not empty")
    print("PASS test_brief_parse_reids_and_bands")


def test_brief_no_competencies_is_empty():
    b = B._parse_brief({"role_summary": "x", "competencies": []})
    _assert(b.is_empty(), "no competencies → is_empty (useless downstream)")
    for bad in (None, "nope", 42, {"competencies": "no"}):
        _assert(B._parse_brief(bad).is_empty(), f"garbage brief → empty for {bad!r}")
    print("PASS test_brief_no_competencies_is_empty")


def test_band_or_default():
    _assert(P.band_or_default("Strong") == "strong", "case-insensitive band")
    _assert(P.band_or_default("") == "needs_work", "blank → needs_work")
    _assert(P.band_or_default(None) == "needs_work", "None → needs_work")
    print("PASS test_band_or_default")


# ---- question parsers ----

def test_questions_parse_reid_type_and_join():
    valid = {"c1", "c2"}
    out = Q._parse_questions(_QUESTIONS["questions"], valid_ids=valid)
    _assert([q.id for q in out] == ["q1", "q2", "q3"], f"dense re-id, got {[q.id for q in out]}")
    _assert(out[0].competency_id is None, "opener keeps null competency")
    _assert(out[1].competency_id == "c1", "valid competency id kept")
    _assert(out[2].type == "behavioral", "bad type → behavioral default")
    _assert(out[2].competency_id is None, "c99 not in brief → nulled (no dangling join)")
    print("PASS test_questions_parse_reid_type_and_join")


def test_questions_garbage_safe():
    for bad in (None, "nope", [1, None, {}], [{"type": "opener"}]):
        _assert(Q._parse_questions(bad, valid_ids={"c1"}) == [], f"garbage → empty for {bad!r}")
    print("PASS test_questions_garbage_safe")


# ---- end to end ----

def test_brief_generate_then_cache():
    p = _fresh()
    iid = _seed_interview(p)
    client = _FakeClient(payload=_BRIEF)
    interview = db.get_interview(iid, path=p)
    out = B.get_or_generate_brief(interview, "my résumé text", client, lang="en", path=p)
    _assert(out is not None and not out.is_empty(), "miss should generate a brief")
    _assert([c.id for c in out.competencies] == ["c1", "c2"], "parsed brief cached")
    _assert(out.created_at, "created_at from stored row")
    out2 = B.get_or_generate_brief(interview, "my résumé text", client, lang="en", path=p)
    _assert(out2 is not None and client.calls == 1, "cache hit must not re-generate")
    print("PASS test_brief_generate_then_cache")


def test_empty_brief_returns_none():
    p = _fresh()
    iid = _seed_interview(p)
    client = _FakeClient(payload={"role_summary": "x", "competencies": []})
    out = B.get_or_generate_brief(db.get_interview(iid, path=p), "résumé", client, lang="en", path=p)
    _assert(out is None, "empty brief → None")
    print("PASS test_empty_brief_returns_none")


def test_questions_generate_then_cache():
    p = _fresh()
    iid = _seed_interview(p)
    interview = db.get_interview(iid, path=p)
    competencies = [{"id": "c1", "name": "Stakeholder", "what_good_looks_like": "aligns"},
                    {"id": "c2", "name": "SQL", "what_good_looks_like": "joins"}]
    client = _FakeClient(payload=_QUESTIONS)
    out = Q.get_or_generate_questions(interview, competencies, client, lang="en", path=p)
    _assert(out is not None and len(out) == 3, f"miss generates questions, got {out}")
    _assert(out[2].competency_id is None, "fan-out nulls a competency the brief lacks")
    out2 = Q.get_or_generate_questions(interview, competencies, client, lang="en", path=p)
    _assert(out2 is not None and client.calls == 1, "cache hit must not re-generate")
    # no competencies → None, no call
    empty_client = _FakeClient(payload=_QUESTIONS)
    _assert(Q.get_or_generate_questions(interview, [], empty_client, lang="en", path=p) is None,
            "no competencies → None")
    _assert(empty_client.calls == 0, "no competencies → no generation")
    print("PASS test_questions_generate_then_cache")


_COMPS = [{"id": "c1", "name": "Stakeholder", "what_good_looks_like": "aligns"},
          {"id": "c2", "name": "SQL", "what_good_looks_like": "joins"}]
_STORIES = [
    {"id": "s1", "title": "Cross-team launch", "situation": "sit", "task": "t",
     "action": "a", "result": "shipped", "metric": "3 teams", "tags": ["Stakeholder"]},
    {"id": "s2", "title": "Query rewrite", "situation": "sit", "task": "t",
     "action": "a", "result": "faster", "metric": "40%", "tags": ["SQL"]},
]
_MAPPING = {
    "mapping": [
        {"competency_id": "c1", "story_id": "s1", "why_it_fits": "shows alignment",
         "angle_for_this_role": "lead with the 3-team scope"},
        {"competency_id": "c2", "story_id": "s99",  # unknown story → nulled
         "why_it_fits": "x", "angle_for_this_role": "y"},
        {"competency_id": "cZ", "story_id": "s1"},   # unknown competency → dropped
        {"competency_id": "c1", "story_id": "s2"},   # dup competency → dropped
    ]
}
_STUDY = {
    "answers": [
        {"question_id": "q1", "answer": "I led the launch across three teams.", "point_to_land": "I align teams"},
        {"question_id": "q99", "answer": "unknown question id"},     # dangling → dropped
        {"question_id": "q2", "answer": ""},                          # blank answer → dropped
        {"question_id": "q1", "answer": "duplicate id"},              # dup → dropped
    ],
    "questions_to_ask": ["What does success look like in 90 days?", "", "How is the team structured?"],
}
_QS = [{"id": "q1", "text": "Tell me about a launch.", "type": "behavioral", "competency_id": "c1"},
       {"id": "q2", "text": "Why us?", "type": "opener", "competency_id": None}]
_MAP = [{"competency_id": "c1", "story_id": "s1", "angle_for_this_role": "lead with scope"}]


# ---- P3 mapping ----

def test_mapping_parse_joins_and_dedup():
    out = M._parse_mapping(_MAPPING["mapping"],
                           valid_competencies={"c1", "c2"}, valid_stories={"s1", "s2"})
    _assert([m.competency_id for m in out] == ["c1", "c2"], f"unknown/dup competency handled, got {[m.competency_id for m in out]}")
    _assert(out[0].story_id == "s1" and out[0].why_it_fits.startswith("shows"), "valid story kept with why")
    _assert(out[1].story_id is None, "unknown story → nulled")
    _assert(out[1].why_it_fits is None, "nulled story drops its why/angle")
    print("PASS test_mapping_parse_joins_and_dedup")


def test_mapping_empty_bank_no_llm():
    p = _fresh()
    iid = _seed_interview(p)
    interview = db.get_interview(iid, path=p)
    client = _FakeClient(payload=_MAPPING)
    out = M.get_or_generate_mapping(interview, _COMPS, [], client, lang="en", path=p)
    _assert(out is not None and len(out) == 2, "empty bank → one null row per competency")
    _assert(all(m.story_id is None for m in out), "empty bank → all gaps")
    _assert(client.calls == 0, "empty bank must NOT call the LLM")
    print("PASS test_mapping_empty_bank_no_llm")


def test_mapping_fingerprint_invalidates_on_story_edit():
    p = _fresh()
    iid = _seed_interview(p)
    interview = db.get_interview(iid, path=p)
    client = _FakeClient(payload=_MAPPING)
    M.get_or_generate_mapping(interview, _COMPS, _STORIES, client, lang="en", path=p)
    _assert(client.calls == 1, "first mapping generates")
    M.get_or_generate_mapping(interview, _COMPS, _STORIES, client, lang="en", path=p)
    _assert(client.calls == 1, "same stories → cache hit")
    edited = [dict(_STORIES[0], result="shipped and scaled"), _STORIES[1]]
    M.get_or_generate_mapping(interview, _COMPS, edited, client, lang="en", path=p)
    _assert(client.calls == 2, "edited story content → cache miss (fingerprint)")
    print("PASS test_mapping_fingerprint_invalidates_on_story_edit")


# ---- P4 answer cards (ADR-056) ----

def test_answers_parse_joins_and_caps():
    kit = F._parse_kit(_STUDY, valid_qids={"q1", "q2"})
    _assert([a.question_id for a in kit.answers] == ["q1"], f"dangling/blank/dup dropped, got {kit.answers}")
    _assert(kit.answers[0].point_to_land == "I align teams", "point to land kept")
    _assert(kit.questions_to_ask == ["What does success look like in 90 days?", "How is the team structured?"],
            "blank question dropped")
    _assert(not kit.is_empty(), "kit with content is not empty")
    print("PASS test_answers_parse_joins_and_caps")


def test_answers_prompt_first_person_and_story():
    brief = {"role_summary": "own analytics", "competencies": _COMPS}
    prompt = F._build_prompt({"company": "Acme", "role_title": "Analyst"}, brief, _QS, _MAP,
                             _STORIES, "résumé text", lang="en")
    _assert("first person" in prompt and "Never use my name" in prompt, "prompt demands first person, no name")
    _assert('use my story: "Cross-team launch"' in prompt, "mapped story is named on its question")
    _assert("q2 [opener]: Why us?" in prompt, "every question is listed with its id")
    print("PASS test_answers_prompt_first_person_and_story")


def test_answers_generate_then_cache_and_fingerprint():
    p = _fresh()
    iid = _seed_interview(p)
    interview = db.get_interview(iid, path=p)
    brief = {"role_summary": "own analytics", "competencies": _COMPS}
    client = _FakeClient(payload=_STUDY)
    out = F.get_or_generate_answers(interview, brief, _QS, _MAP, _STORIES, "résumé text", client, lang="en", path=p)
    _assert(out is not None and len(out.answers) == 1, f"miss generates a kit, got {out}")
    F.get_or_generate_answers(interview, brief, _QS, _MAP, _STORIES, "résumé text", client, lang="en", path=p)
    _assert(client.calls == 1, "same inputs → cache hit")
    remapped = [dict(_MAP[0], story_id="s2")]
    F.get_or_generate_answers(interview, brief, _QS, remapped, _STORIES, "résumé text", client, lang="en", path=p)
    _assert(client.calls == 2, "a different story mapping → cache miss (fingerprint)")
    none_client = _FakeClient(payload=_STUDY)
    _assert(F.get_or_generate_answers(interview, brief, [], _MAP, _STORIES, "r", none_client, lang="en", path=p) is None,
            "no questions → None")
    _assert(none_client.calls == 0, "no questions → no generation")
    print("PASS test_answers_generate_then_cache_and_fingerprint")


if __name__ == "__main__":
    test_brief_parse_reids_and_bands()
    test_brief_no_competencies_is_empty()
    test_band_or_default()
    test_questions_parse_reid_type_and_join()
    test_questions_garbage_safe()
    test_brief_generate_then_cache()
    test_empty_brief_returns_none()
    test_questions_generate_then_cache()
    test_mapping_parse_joins_and_dedup()
    test_mapping_empty_bank_no_llm()
    test_mapping_fingerprint_invalidates_on_story_edit()
    test_answers_parse_joins_and_caps()
    test_answers_prompt_first_person_and_story()
    test_answers_generate_then_cache_and_fingerprint()
    print("all prep-pipeline tests passed")
