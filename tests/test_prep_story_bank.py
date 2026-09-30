"""Story Bank — P5 draft-from-résumé, P6 voice→STAR, the code-side strength
check, and the `stories` DB helpers (REQ-041 / ADR-050). Locks down:

  1. strength_check flags missing result / missing number / unclear 'I' role
     and picks the right badge (result > owner > number > strong) — deterministic;
  2. P5 keeps drafts with a title+action, filters tags to the known vocab, never
     invents a result/metric (null stays null);
  3. P6 parses one STAR story with the model's strength read + follow-up;
  4. stories helpers round-trip tags as a real list, list_stories hides drafts
     by default, update_story patches allowed fields + re-encodes tags.

No network: a fake GeminiClient supplies the JSON.
    .venv/bin/python tests/test_prep_story_bank.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.prep import story_bank as S  # noqa: E402


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


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "stories.sqlite"
    db.init_db(p)
    return p


# ---- strength check (deterministic, no LLM) ----

def test_strength_strong_when_complete():
    out = S.strength_check({"result": "Shipped to 3 regions", "metric": "cut cost 40%",
                            "action": "I led the migration by moving 40 services to Kubernetes with blue-green deploys"})
    _assert(out["flags"] == [], f"complete story has no flags, got {out}")
    _assert(out["badge"] == "strong" and out["badge_label"] == "Strong", "strong badge")
    print("PASS test_strength_strong_when_complete")


def test_strength_missing_result_wins():
    out = S.strength_check({"result": "", "metric": "", "action": "I built it"})
    _assert("missing_result" in out["flags"] and "missing_metric" in out["flags"], "both flagged")
    _assert(out["badge"] == "needs_result", "result outranks number")
    print("PASS test_strength_missing_result_wins")


def test_strength_number_detected_in_result():
    out = S.strength_check({"result": "grew signups by 25%", "action": "I ran an A/B test using Optimizely on the signup page"})
    _assert("missing_metric" not in out["flags"], "number in result counts")
    _assert(out["badge"] == "strong", "has result + number + I → strong")
    print("PASS test_strength_number_detected_in_result")


def test_strength_missing_how():
    """ADR-058: an Action that says WHAT but not HOW is flagged."""
    out = S.strength_check({"result": "Saved 60+ staff hours per month", "metric": "60h",
                            "action": "Created Power BI dashboards to support data preparation and resource optimization."})
    _assert(out["flags"] == ["missing_how"] and out["badge"] == "needs_how", f"what-not-how flagged, got {out}")
    ok = S.strength_check({"result": "Saved 60h/month", "action": "I automated the weekly pull with Power Query"})
    _assert("missing_how" not in ok["flags"], "a method connector clears it")
    print("PASS test_strength_missing_how")


def test_refine_story_uses_only_answers():
    class _C:
        def __init__(self, payload): self.payload, self.calls, self.prompts = payload, 0, []
        last_model_used = model_name = "fake"
        def all_models_exhausted(self): return False
        def generate_json(self, prompt, *, temperature=None, max_retries=2):
            self.calls += 1; self.prompts.append(prompt); return self.payload
    story = {"title": "CRA dashboards", "situation": "s", "task": "t", "action": "Created dashboards",
             "result": "Saved 60h", "metric": "60h", "tags": ["Data analysis"]}
    c = _C({"title": "CRA dashboards", "situation": "s", "task": "t",
            "action": "I automated the weekly pull with Power Query", "result": "Saved 60h/month", "metric": "60h"})
    d = S.refine_story(story, {"missing_how": "Power Query automation", "missing_metric": "  "}, c, lang="en")
    _assert(d is not None and d.action.startswith("I automated") and d.tags == ["Data analysis"], "preview built, tags kept")
    _assert("missing_how: Power Query automation" in c.prompts[0] and "missing_metric" not in c.prompts[0], "blank answers dropped")
    _assert("Do not add employers, tools, numbers" in c.prompts[0], "no-new-data rule")
    none = _C({})
    _assert(S.refine_story(story, {"missing_how": " "}, none, lang="en") is None and none.calls == 0, "no answers → no call")
    _assert(S.refine_story(story, {"missing_how": "x"}, _C({"action": ""}), lang="en") is None, "empty action → None")
    print("PASS test_refine_story_uses_only_answers")


def test_strength_unclear_role():
    out = S.strength_check({"result": "we won the deal 2x faster", "action": "we aligned the team"})
    _assert("unclear_personal_role" in out["flags"], "we-without-I flagged")
    _assert(out["badge"] == "needs_owner", "owner outranks number when result present")
    # an 'I' anywhere in the action clears it
    ok = S.strength_check({"result": "won 2x", "action": "I aligned our team"})
    _assert("unclear_personal_role" not in ok["flags"], "an explicit I clears the flag")
    print("PASS test_strength_unclear_role")


# ---- P5 draft-from-résumé ----

_DRAFTS = {
    "stories": [
        {"title": "ATIP backlog", "situation": "s", "task": "t", "action": "I built a pipeline",
         "result": None, "metric": None, "tags": ["Ownership", "Data analysis", "Nonsense tag"],
         "questions_for_candidate": ["What was the result?", ""]},
        {"title": "", "action": "dropped: no title"},         # dropped
        {"title": "no action", "action": ""},                  # dropped
    ]
}


def test_p5_parse_keeps_grounded_filters_tags():
    out = S._parse_drafts(_DRAFTS["stories"], valid_tags=set(S.DEFAULT_COMPETENCY_TAGS))
    _assert(len(out) == 1, f"only the well-formed draft kept, got {len(out)}")
    d = out[0]
    _assert(d.result is None and d.metric is None, "missing result/metric stay null (never invented)")
    _assert(d.tags == ["Ownership", "Data analysis"], f"unknown tag filtered, got {d.tags}")
    _assert(d.questions_for_candidate == ["What was the result?"], "blank question dropped")
    print("PASS test_p5_parse_keeps_grounded_filters_tags")


def test_p5_generate():
    client = _FakeClient(payload=_DRAFTS)
    out = S.draft_stories_from_resume("my résumé", client, lang="en")
    _assert(len(out) == 1 and out[0].title == "ATIP backlog", "P5 generates parsed drafts")
    _assert(S.draft_stories_from_resume("", client, lang="en") == [], "empty résumé → no call")
    print("PASS test_p5_generate")


# ---- P6 voice→STAR ----

_VOICE = {
    "title": "Cut release time", "situation": "s", "task": "t", "action": "I automated the pipeline",
    "result": "releases got faster", "metric": None, "tags": ["Execution & delivery"],
    "strength": "solid", "strength_reason": "clear action, no number",
    "flags": ["missing_metric"], "follow_up_question": "By how much did release time drop?",
}


def test_p6_parse():
    d = S._parse_voice(_VOICE, valid_tags=set(S.DEFAULT_COMPETENCY_TAGS))
    _assert(d is not None and d.title == "Cut release time", "voice story parsed")
    _assert(d.metric is None and d.follow_up_question.startswith("By how much"), "missing metric + follow-up")
    _assert(d.strength == "solid" and d.tags == ["Execution & delivery"], "strength + tag kept")
    _assert(S._parse_voice({"title": "", "action": ""}, valid_tags=set()) is None, "empty voice → None")
    print("PASS test_p6_parse")


# ---- stories DB helpers ----

def test_stories_crud_and_draft_filter():
    p = _fresh()
    saved = db.create_story("cand1", title="Saved one", action="I did X",
                            result="won", tags=["Ownership"], source="manual", path=p)
    draft = db.create_story("cand1", title="AI draft", action="I did Y",
                            source="ai_resume", status="draft", tags=["Data analysis"], path=p)
    got = db.get_story(saved, path=p)
    _assert(got["tags"] == ["Ownership"], "tags round-trip as a list")
    default = db.list_stories("cand1", path=p)
    _assert([s["id"] for s in default] == [saved], "default list hides drafts")
    every = db.list_stories("cand1", status=None, path=p)
    _assert(len(every) == 2, "status=None returns drafts too")
    db.update_story(draft, {"status": "saved", "tags": ["Communication"], "id": 999}, path=p)
    promoted = db.get_story(draft, path=p)
    _assert(promoted["status"] == "saved" and promoted["tags"] == ["Communication"], "update patches + re-encodes tags")
    _assert(promoted["id"] == draft, "id is not writable via update")
    db.delete_story(saved, path=p)
    _assert(len(db.list_stories("cand1", status=None, path=p)) == 1, "delete removes the story")
    print("PASS test_stories_crud_and_draft_filter")


if __name__ == "__main__":
    test_strength_strong_when_complete()
    test_strength_missing_result_wins()
    test_strength_number_detected_in_result()
    test_strength_unclear_role()
    test_strength_missing_how()
    test_refine_story_uses_only_answers()
    test_p5_parse_keeps_grounded_filters_tags()
    test_p5_generate()
    test_p6_parse()
    test_stories_crud_and_draft_filter()
    print("all story-bank tests passed")
