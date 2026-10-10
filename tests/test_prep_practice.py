"""Practice pipeline P7/P8/P9 + delivery metrics (REQ-041 / ADR-048/049). Locks:
  1. delivery_metrics computes real numbers in code — wpm, filler count (single
     + phrases), length band vs target — and is safe on empty/zero;
  2. pick_session_questions caps at the length preset and honours a focus
     competency (openers still allowed through);
  3. P7 system prompt lists the session questions in order + names role/company;
  4. P8 parse coerces bad bands → needs_work, keeps what_worked/fix, nulls a
     blank stronger_version;
  5. P9 parse caps top_actions at 3, drops competency bands the brief didn't
     define, nulls blank next_drill ids;
  6. P8/P9 generate via a fake client and degrade to None on empty input.
    .venv/bin/python tests/test_prep_practice.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.prep import practice as PR  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


class _FakeClient:
    def __init__(self, payload=None):
        self.payload = payload
        self.calls = 0
        self.last_model_used = "fake"
        self.model_name = "fake"

    def all_models_exhausted(self):
        return False

    def generate_json(self, prompt, *, temperature=None, max_retries=2):
        self.calls += 1
        return self.payload


# ---- delivery metrics (code) ----

def test_delivery_metrics():
    # 60 words in 60s → 60 wpm; fillers: "um" x1, "uh" x1, "you know" x1
    text = "um so I led the project uh and you know we shipped it " + ("word " * 48)
    m = PR.delivery_metrics(text, seconds=60, target_seconds=90)
    _assert(m["wpm"] == m["word_count"], f"60s → wpm==word_count, got {m}")
    _assert(m["filler_count"] == 3, f"um+uh+you-know = 3, got {m['filler_count']}")
    _assert(m["length_band"] == "on_target", f"60/90=0.67 → on_target, got {m['length_band']}")
    print("PASS test_delivery_metrics")


def test_delivery_length_bands_and_safety():
    _assert(PR.delivery_metrics("a b c", 30, 90)["length_band"] == "short", "0.33 → short")
    _assert(PR.delivery_metrics("a b c", 90, 90)["length_band"] == "on_target", "1.0 → on_target")
    _assert(PR.delivery_metrics("a b c", 200, 90)["length_band"] == "long", "2.2 → long")
    z = PR.delivery_metrics("", 0, 90)
    _assert(z["wpm"] == 0 and z["filler_count"] == 0 and z["length_band"] == "unknown", f"empty safe, got {z}")
    print("PASS test_delivery_length_bands_and_safety")


# ---- session shaping ----

_QS = [
    {"id": "q1", "text": "Tell me about yourself.", "type": "opener", "competency_id": None},
    {"id": "q2", "text": "A stakeholder conflict?", "type": "behavioral", "competency_id": "c1"},
    {"id": "q3", "text": "A SQL problem?", "type": "technical", "competency_id": "c2"},
    {"id": "q4", "text": "Another c1?", "type": "situational", "competency_id": "c1"},
    {"id": "q5", "text": "Why us?", "type": "opener", "competency_id": None},
]


def test_pick_questions_length_and_focus():
    _assert(len(PR.pick_session_questions(_QS, length="quick")) == 3, "quick = 3")
    _assert(len(PR.pick_session_questions(_QS, length="full")) == 5, "full caps at available 5")
    focused = PR.pick_session_questions(_QS, length="standard", focus_competency="c1")
    ids = [q["id"] for q in focused]
    _assert("q3" not in ids, f"focus c1 excludes c2 question, got {ids}")
    _assert("q1" in ids or "q5" in ids, "openers still allowed through under focus")
    print("PASS test_pick_questions_length_and_focus")


def test_pick_questions_prefer_missed():
    """ADR-056: answer cards rated "missed" lead the session, right after one opener."""
    ids = [q["id"] for q in PR.pick_session_questions(_QS, length="quick", prefer_ids={"q4"})]
    _assert(ids[1] == "q4", f"missed card comes right after the opener, got {ids}")
    _assert(ids[0] == next(q["id"] for q in _QS if q.get("type") == "opener"), "session still opens with an opener")
    plain = [q["id"] for q in PR.pick_session_questions(_QS, length="quick")]
    _assert([q["id"] for q in PR.pick_session_questions(_QS, length="quick", prefer_ids={"zz"})] == plain,
            "unknown preferred ids change nothing")
    print("PASS test_pick_questions_prefer_missed")


def test_target_seconds():
    _assert(PR.target_seconds_for({"type": "behavioral"}) == 90, "behavioral target")
    _assert(PR.target_seconds_for({"type": "opener"}) == 60, "opener target")
    _assert(PR.target_seconds_for({"type": "weird"}) == PR.DEFAULT_TARGET, "unknown → default")
    print("PASS test_target_seconds")


# ---- P7 system prompt (split: short core + separate context turn) ----

def test_p7_core_prompt_short_and_toned():
    iv = {"role_title": "PD", "company": "Stripe", "round_type": "behavioral"}
    p = PR.interviewer_system_prompt(iv, lang="en", coach_name="David", style="direct and probing")
    _assert("Stripe" in p and "PD" in p, "names role + company")
    _assert("David" in p and "direct and probing" in p, "persona name + style folded in")
    # tone tweaks: no cheerleader fillers + a backchannel cue + one-follow-up
    _assert("cheerleader" in p.lower() and "that's interesting" in p.lower(), "bans enthusiastic fillers")
    # REQ-048: acknowledge by restating a detail, never a bare "Mm-hmm"
    _assert("restating one concrete detail" in p and "Never reply with only a listener sound" in p,
            "acks show listening, no bare listener sound")
    _assert("Never start two acknowledgments the same way" in p and "Thanks — so you" not in p,
            "acks vary: no single example for the model to copy every turn")
    _assert("one follow-up" in p.lower(), "one-follow-up rule present")
    # must stay well under the ~4000-char Live silent-hang limit
    _assert(len(p) < 2500, f"core prompt must be short, got {len(p)} chars")
    print(f"  P7 core prompt: {len(p)} chars")
    _assert("1. Tell me about yourself" not in p, "questions are NOT in the core prompt (split out)")
    # professional opening: greeting + candidate name, then the coach's name
    g = PR.interviewer_system_prompt(iv, lang="en", coach_name="Maya", candidate_name="Eduardo")
    _assert("Hello Eduardo, I'm Maya." in g, "greets the candidate by name, then introduces itself")
    _assert("Hello, I'm Maya." in PR.interviewer_system_prompt(iv, lang="en", coach_name="Maya"),
            "no name known → plain 'Hello'")
    _assert("HR interviewer" in g and "salesy" in g, "calm HR delivery, not salesy")
    _assert("JSON" not in g, "no JSON-language rule in a spoken prompt")
    print("PASS test_p7_core_prompt_short_and_toned")


def test_p7_context_turn_carries_questions():
    iv = {"role_title": "PD", "company": "Stripe", "round_type": "behavioral"}
    c = PR.interviewer_context_turn(iv, _QS[:2],
                                    brief={"role_summary": "own analytics",
                                           "competencies": [{"id": "c1", "name": "Stakeholder", "what_good_looks_like": "aligns"}]},
                                    persona="a data analyst")
    _assert("1. Tell me about yourself." in c and "2. A stakeholder conflict?" in c, "numbered questions in order")
    _assert("Stakeholder" in c and "data analyst" in c, "context carries competencies + persona")
    _assert("begin" in c.lower(), "tells the coach to begin")
    print("PASS test_p7_context_turn_carries_questions")


# ---- P8 evaluate ----

_EVAL = {
    "ratings": {"answered_the_question": "strong", "structure": "banana",
                "personal_action": "solid", "result_evidence": "needs_work", "relevance": "solid"},
    "overall": "solid",
    "what_worked": {"quote": "I cut turnaround 40%", "why": "concrete result"},
    "fix": "Lead with the metric earlier.",
    "stronger_version": "",
}


def test_p8_parse():
    ev = PR._parse_eval(_EVAL, question_id="q2")
    _assert(ev.ratings["structure"] == "needs_work", "bad band → needs_work")
    _assert(ev.ratings["answered_the_question"] == "strong", "valid band kept")
    _assert(ev.what_worked["quote"].startswith("I cut"), "what_worked kept")
    _assert(ev.stronger_version is None, "blank stronger_version → None")
    _assert(ev.question_id == "q2", "question id carried")
    print("PASS test_p8_parse")


def test_p8_generate_and_empty():
    client = _FakeClient(payload=_EVAL)
    ev = PR.evaluate_answer({"id": "q2", "text": "Q", "type": "behavioral"},
                            {"name": "Stakeholder", "what_good_looks_like": "aligns"},
                            None, "I aligned the team and we won", client, lang="en")
    _assert(ev is not None and ev.overall == "solid", "generates eval")
    # empty transcript → None, no call
    c2 = _FakeClient(payload=_EVAL)
    _assert(PR.evaluate_answer({"id": "q2"}, None, None, "  ", c2, lang="en") is None, "empty → None")
    _assert(c2.calls == 0, "empty → no call")
    print("PASS test_p8_generate_and_empty")


# ---- P9 debrief ----

_DEBRIEF = {
    "takeaway": "Strong ownership; quantify results more.",
    "competency_bands": [{"competency_id": "c1", "band": "solid"},
                         {"competency_id": "cX", "band": "strong"}],  # cX dropped
    "top_actions": ["Add numbers", "Lead with I", "Tighten structure", "Extra action"],  # capped to 3
    "stories_to_revisit": [{"story_id": "s1", "why": "needs a metric"}, {"why": "no id"}],
    "next_drill": {"competency_id": "c1", "question_id": "", "reason": "weakest"},
}


def test_p9_parse():
    d = PR._parse_debrief(_DEBRIEF, valid_comps={"c1", "c2"})
    _assert([b["competency_id"] for b in d.competency_bands] == ["c1"], "unknown competency dropped")
    _assert(len(d.top_actions) == 3, "top_actions capped at 3")
    _assert(len(d.stories_to_revisit) == 1, "story with no id dropped")
    _assert(d.next_drill["competency_id"] == "c1" and d.next_drill["question_id"] is None, "blank drill id → None")
    _assert(not d.is_empty(), "has content")
    print("PASS test_p9_parse")


def test_p9_generate_and_empty():
    client = _FakeClient(payload=_DEBRIEF)
    d = PR.session_debrief([{"question_id": "q1"}], [{"wpm": 120}],
                           [{"id": "c1", "name": "Stakeholder", "what_good_looks_like": "x"}], client, lang="en")
    _assert(d is not None and d.takeaway.startswith("Strong"), "generates debrief")
    _assert(PR.session_debrief([], [], [], _FakeClient(payload=_DEBRIEF), lang="en") is None, "no evals → None")
    print("PASS test_p9_generate_and_empty")


def test_p9_from_transcript():
    # voice path: one debrief over the whole conversation; reuses the P9 parser.
    transcript = [{"role": "coach", "text": "Tell me about yourself."},
                  {"role": "you", "text": "I led a data team and cut turnaround 40%."}]
    comps = [{"id": "c1", "name": "Stakeholder", "what_good_looks_like": "aligns"},
             {"id": "c2", "name": "SQL", "what_good_looks_like": "joins"}]
    client = _FakeClient(payload=_DEBRIEF)
    d = PR.session_debrief_from_transcript(transcript, [{"text": "Tell me about yourself."}], comps, client, lang="en")
    _assert(d is not None and d.takeaway.startswith("Strong"), "generates debrief from transcript")
    _assert([b["competency_id"] for b in d.competency_bands] == ["c1"], "unknown competency dropped (cX)")
    _assert(len(d.top_actions) == 3, "top_actions capped at 3")
    # empty transcript → None, no call
    empty = _FakeClient(payload=_DEBRIEF)
    _assert(PR.session_debrief_from_transcript([], [], comps, empty, lang="en") is None, "empty transcript → None")
    _assert(empty.calls == 0, "empty → no call")
    print("PASS test_p9_from_transcript")


def test_audio_score_helpers():
    from core.prep import audio_score as A
    # Delivery is counted in CODE (ADR-059) — 120 words over 60s = 120 wpm.
    d = A.code_delivery(" ".join(["word"] * 118 + ["um", "uh"]), 60)
    _assert(d["wpm"] == 120 and d["filler_count"] == 2, "wpm + fillers counted in code")
    _assert(d["pace"] == "on_target", "pace from wpm thresholds")
    _assert(A.code_delivery("", 0)["pace"] == "unknown", "no speech → unknown, not a guess")
    prompt = A._build_prompt([{"text": "Tell me about yourself"}],
                             [{"id": "c1", "name": "Stakeholder", "what_good_looks_like": "aligns"}],
                             [{"role": "coach", "text": "Walk me through a budget you managed"}], lang="en")
    _assert("Tell me about yourself" in prompt and "Stakeholder" in prompt, "prompt carries Qs + competencies")
    _assert("Walk me through a budget" in prompt, "prompt carries what the coach actually asked")
    _assert("competency_evidence" in prompt and "clean_transcript" in prompt, "schema asks for evidence + transcript")
    _assert('"wpm"' not in prompt and "confidence" not in prompt, "no model-guessed delivery")
    print("PASS test_audio_score_helpers")


def test_audio_quotes_verify_against_live_transcript():
    """Code-review 2026-10-07: a quote the audio model invents AND copies into its
    own clean_transcript must not verify — only the live transcript counts."""
    import json as _json
    import types
    import google.genai as genai
    from core.llm import usage as llm_usage
    from core.prep import audio_score as A
    from core.prep import session_score as SS

    invented = "I cut costs by 20 percent by renegotiating every vendor contract"
    raw = {"takeaway": "t", "top_actions": [], "clean_transcript": invented,
           "competency_evidence": [{"competency_id": "c1", "asked": True, "quote": invented,
                                    "checks": {k: True for k in SS.CHECKS}}]}

    class _Files:
        def upload(self, file): return types.SimpleNamespace(name="f1")
        def delete(self, name): pass

    class _Models:
        def generate_content(self, **kw): return types.SimpleNamespace(text=_json.dumps(raw))

    class _Client:
        def __init__(self, **kw): self.files, self.models = _Files(), _Models()

    orig = (genai.Client, A.resolve_api_key, llm_usage.check_and_charge)
    genai.Client, A.resolve_api_key, llm_usage.check_and_charge = _Client, lambda: "k", lambda **kw: None
    try:
        comps = [{"id": "c1", "name": "Budget", "what_good_looks_like": "x"}]
        qs = [{"id": "q1", "text": "Budget?", "competency_id": "c1"}]
        said = [{"role": "coach", "text": "Budget?"},
                {"role": "you", "text": "um budgets are important you just have to watch them"}]
        out = A.score_from_audio(b"RIFF", qs, comps, turns=said, candidate_seconds=10, lang="en")
        ev = out["competency_evidence"][0]
        _assert(not ev["verified"] and ev["points"] == 0, f"invented quote earns nothing: {ev}")
        # No live transcript at all → the model's transcript is the only source.
        out2 = A.score_from_audio(b"RIFF", qs, comps, turns=[], candidate_seconds=10, lang="en")
        _assert(out2["competency_evidence"][0]["verified"], "falls back to clean_transcript when no live text")
    finally:
        genai.Client, A.resolve_api_key, llm_usage.check_and_charge = orig
    print("PASS test_audio_quotes_verify_against_live_transcript")


def test_setup_labels_translated():
    """Code-review 2026-10-07: Practice setup showed English personality/voice
    labels to Spanish users. Every option must resolve in en AND es."""
    from core.prep import live as L
    from ui_web import i18n
    keys = [f"prep2.personality.{pid}.{part}" for pid in L.PERSONALITIES for part in ("label", "blurb")]
    keys += [f"prep2.voice.trait.{m[1].lower()}" for m in L.VOICES.values()]
    keys += [f"prep2.voice.{m[0]}" for m in L.VOICES.values()]
    for lang in ("en", "es"):
        missing = [k for k in keys if k not in i18n.TRANSLATIONS[lang]]
        _assert(not missing, f"{lang} missing {missing}")
    print("PASS test_setup_labels_translated")


if __name__ == "__main__":
    test_delivery_metrics()
    test_delivery_length_bands_and_safety()
    test_pick_questions_length_and_focus()
    test_pick_questions_prefer_missed()
    test_target_seconds()
    test_p7_core_prompt_short_and_toned()
    test_p7_context_turn_carries_questions()
    test_p8_parse()
    test_p8_generate_and_empty()
    test_p9_parse()
    test_p9_generate_and_empty()
    test_p9_from_transcript()
    test_audio_score_helpers()
    test_audio_quotes_verify_against_live_transcript()
    test_setup_labels_translated()
    print("all practice-pipeline tests passed")
