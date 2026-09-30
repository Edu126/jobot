"""Prep toolkit orchestrator (REQ-041 / ADR-048). Locks down:

  1. build_toolkit runs P1, then P2 ∥ P3, then P4 — all four artifacts come back,
     status advances to toolkit_ready, and the fan-out joins line up (questions /
     mapping / flashcards all use the brief's re-id'd c1/c2);
  2. a failed P1 (empty brief) skips the fan-out entirely and leaves status short
     of toolkit_ready;
  3. use_cache=True on a second build does zero new LLM calls (all cache hits);
  4. failing sub-calls degrade to None without sinking the brief (and P4 is
     skipped when P2 produced no questions).

One MERGED payload feeds every stage — each module's parser reads only its own
top-level key, so a single fake serves brief+questions+mapping+flashcards.
    .venv/bin/python tests/test_prep_orchestrator.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.prep import pipeline as PL  # noqa: E402


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


class _Factory:
    """make_client that hands out a fresh fake per stage and remembers them all,
    so a test can sum LLM calls across the parallel branches."""
    def __init__(self, payload=None, raise_exc=None):
        self.payload = payload
        self.raise_exc = raise_exc
        self.created: list[_FakeClient] = []

    def __call__(self) -> _FakeClient:
        c = _FakeClient(payload=self.payload, raise_exc=self.raise_exc)
        self.created.append(c)
        return c

    @property
    def total_calls(self) -> int:
        return sum(c.calls for c in self.created)


# All four parsers read disjoint top-level keys, so one blob serves every stage.
# Brief re-ids competencies to c1,c2; the downstream joins reference c1/s1.
_MERGED = {
    "role_summary": "Own the analytics stack.",
    "company_snapshot": [{"point": "Series B fintech", "source_url": "https://x/a"}],
    "competencies": [
        {"id": "cA", "name": "Stakeholder", "what_good_looks_like": "aligns", "resume_match": "strong"},
        {"id": "cB", "name": "SQL", "what_good_looks_like": "joins", "resume_match": "solid"},
    ],
    "gaps": [{"competency_id": "c2", "gap": "no dbt", "action": "read the primer"}],
    "interviewer_lens": ["impact"],
    "friction_points": ["fintech domain"],
    "questions": [
        {"text": "Tell me about yourself.", "type": "opener", "competency_id": None,
         "why_they_ask": "warm up", "follow_up": "why here?"},
        {"text": "A stakeholder conflict?", "type": "behavioral", "competency_id": "c1",
         "why_they_ask": "alignment", "follow_up": "what did you do?"},
    ],
    "mapping": [
        {"competency_id": "c1", "story_id": "s1", "why_it_fits": "fits", "angle_for_this_role": "angle"},
        {"competency_id": "c2", "story_id": None},
    ],
    "answers": [{"question_id": "q2", "answer": "I aligned three teams on one launch.",
                 "point_to_land": "I align teams"}],
    "questions_to_ask": ["What does success look like in 90 days?"],
}

_STORIES = [{"id": "s1", "title": "Launch", "situation": "s", "task": "t",
             "action": "I led it", "result": "shipped", "metric": "3 teams", "tags": ["Stakeholder"]}]


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "orch.sqlite"
    db.init_db(p)
    return p


def _seed(p: Path) -> dict:
    iid = db.create_interview("cand1", "Acme", "Data Analyst", "Analyze data.",
                              "en", "pasted_text", round_type="behavioral", path=p)
    return db.get_interview(iid, path=p)


def test_build_toolkit_full():
    p = _fresh()
    interview = _seed(p)
    factory = _Factory(payload=_MERGED)
    res = asyncio.run(PL.build_toolkit(
        interview, "résumé text", make_client=factory,
        stories=_STORIES, research=[{"title": "t", "url": "u", "content": "c"}],
        lang="en", path=p))
    _assert(res.brief_ready, "brief present")
    _assert([c.id for c in res.brief.competencies] == ["c1", "c2"], "brief re-ids competencies")
    _assert(res.questions is not None and len(res.questions) == 2, "questions built")
    _assert(res.questions[1].competency_id == "c1", "question join lines up with brief id")
    _assert(res.mapping is not None and res.mapping[0].story_id == "s1", "mapping joins the story")
    _assert(res.flashcards is not None and [a.question_id for a in res.flashcards.answers] == ["q2"],
            "answer cards built on the P2 question ids (P4 after P2/P3)")
    _assert(db.get_interview(interview["id"], path=p)["status"] == "toolkit_ready", "status advanced")
    _assert(len(factory.created) == 4, "one client per stage (P1 + P2/P3/P4)")
    print("PASS test_build_toolkit_full")


def test_empty_brief_skips_fanout():
    p = _fresh()
    interview = _seed(p)
    factory = _Factory(payload={"role_summary": "x", "competencies": []})
    res = asyncio.run(PL.build_toolkit(interview, "résumé", make_client=factory, lang="en", path=p))
    _assert(res.brief is None, "empty brief → None")
    _assert(res.questions is None and res.mapping is None and res.flashcards is None, "fan-out skipped")
    _assert(len(factory.created) == 1, "only P1 attempted, no fan-out clients")
    _assert(db.get_interview(interview["id"], path=p)["status"] != "toolkit_ready", "status not advanced")
    print("PASS test_empty_brief_skips_fanout")


def test_second_build_is_all_cache():
    p = _fresh()
    interview = _seed(p)
    f1 = _Factory(payload=_MERGED)
    asyncio.run(PL.build_toolkit(interview, "résumé", make_client=f1, stories=_STORIES, lang="en", path=p))
    _assert(f1.total_calls == 4, f"first build = 4 LLM calls, got {f1.total_calls}")
    f2 = _Factory(payload=_MERGED)
    res = asyncio.run(PL.build_toolkit(interview, "résumé", make_client=f2, stories=_STORIES, lang="en", path=p))
    _assert(res.brief_ready and res.questions and res.flashcards, "cached build still returns everything")
    _assert(f2.total_calls == 0, f"second build = all cache hits, got {f2.total_calls}")
    print("PASS test_second_build_is_all_cache")


def test_one_failing_subcall_degrades():
    p = _fresh()
    interview = _seed(p)
    # P1 succeeds (needs a real brief to fan out); make P4 blow up by feeding a
    # brief-only client, then a raising client for the fan-out flashcards branch.
    # Simplest: a factory whose clients raise only on the flashcards-shaped call
    # is fiddly — instead force ALL fan-out calls to raise and confirm the build
    # still returns the brief with the three degraded to None.
    calls = {"n": 0}

    def make_client():
        calls["n"] += 1
        # first client (P1) returns the brief; the rest raise
        return _FakeClient(payload=_MERGED) if calls["n"] == 1 else _FakeClient(raise_exc=RuntimeError("boom"))

    res = asyncio.run(PL.build_toolkit(interview, "résumé", make_client=make_client,
                                       stories=_STORIES, lang="en", path=p))
    _assert(res.brief_ready, "brief still built when fan-out fails")
    # mapping with a non-empty Story Bank calls the LLM → raises → None;
    # questions raises → None; flashcards raises → None.
    _assert(res.questions is None and res.flashcards is None, "raising sub-calls degrade to None")
    print("PASS test_one_failing_subcall_degrades")


if __name__ == "__main__":
    test_build_toolkit_full()
    test_empty_brief_skips_fanout()
    test_second_build_is_all_cache()
    test_one_failing_subcall_degrades()
    print("all orchestrator tests passed")
