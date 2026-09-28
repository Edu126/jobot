"""Practice pipeline (ADR-048/ADR-049, REQ-041) — the AI behind the mock
interview: P7 (live interviewer), P8 (answer evaluation), P9 (session debrief),
plus the delivery metrics that are computed in CODE, never by the model.

  - P7 `interviewer_system_prompt`: the system prompt for the real-time session
    (returns spoken text, not JSON — the app owns turn state). Used by the
    turn/voice engine; one question at a time, at most one follow-up.
  - P8 `evaluate_answer`: rate ONE answer against its competency rubric — five
    content ratings + an overall band + what-worked + one fix + a stronger
    version. Bands only (strong/solid/needs_work), never invents numbers.
  - `delivery_metrics`: seconds / words-per-minute / filler count / length band
    — REAL numbers, computed here (the model is unreliable at counting, per the
    pack). This is the one place real numbers are honest (design brief §4).
  - P9 `session_debrief`: the end-of-session takeaway, per-competency bands, top
    3 actions, stories to revisit, and the next drill.

Session shaping (`pick_session_questions`, lengths, targets) is code too. These
are per-session one-shots — NOT cached by prompt_version (each session is
unique); results persist on the practice tables (built with the Practice UI).
temperature=0.0. Grounded-or-honest throughout (GOV-005).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.settings import get_output_language, language_instruction

from . import prompts as P

P7_PROMPT_VERSION = "2026-09-21-interviewer-v1"
P8_PROMPT_VERSION = "2026-09-21-answer-eval-v1"
P9_PROMPT_VERSION = "2026-09-21-debrief-v1"

# Session length presets (D6/C2): Quick · Standard · Full round.
SESSION_LENGTHS = {"quick": 3, "standard": 5, "full": 8}
DEFAULT_LENGTH = "standard"

# Per-question speaking target (seconds) by question type — the "target" the
# delivery length band is measured against. Behavioral answers run longer.
TARGET_SECONDS = {"opener": 60, "behavioral": 90, "situational": 90, "technical": 75}
DEFAULT_TARGET = 90

MAX_ANSWER_CHARS = 6000

# Filler words counted in code (conservative — only unambiguous fillers, so we
# don't punish legitimate uses of "so"/"like"/"right"). EN + a few ES.
_FILLER_SINGLE = {
    "um", "uh", "er", "erm", "ah", "hmm", "uhh", "umm",   # en
    "eh", "em", "este", "pues",                            # es
}
_FILLER_PHRASES = ("you know", "i mean", "kind of", "sort of", "o sea")
_WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)


# ---------- P7: live interviewer system prompt ----------

def interviewer_system_prompt(
    interview: dict, *, lang: Optional[str] = None,
    coach_name: str = "", style: str = "",
) -> str:
    """P7 CORE — the SHORT system instruction pinned in the ephemeral token
    (ADR-052). Kept under ~1500 chars on purpose: the Live API **silently hangs**
    on system instructions over ~4000 chars (undocumented). Persona identity +
    behaviour + tone only; the candidate/company context + the question list are
    injected separately via `interviewer_context_turn` (sendClientContent)."""
    lang = lang if lang is not None else get_output_language()
    role = (interview.get("role_title") or "the role").strip()
    company = (interview.get("company") or "the company").strip()
    round_type = (interview.get("round_type") or "screening").strip()
    who = f"You are {coach_name}, a professional interviewer" if coach_name else "You are a professional interviewer"
    style_line = f"\nYour interviewing style: {style}" if style else ""
    return f"""{who} for the role of {role} at {company}. This is a {round_type} round.
You are an AI practice interviewer. If asked, say so.{style_line}

{language_instruction(lang)}
Speak and conduct the ENTIRE interview in English, even if the candidate answers in another language (gently continue in English).

You conduct this as a natural spoken conversation. The candidate/company context + your question list arrive as a first message — then greet the candidate in one short sentence (you're their AI interview coach, here to talk through their fit for {role} at {company}) and begin.

How to behave:
- Name the role and company only in that greeting. Afterward refer to them lightly ("the role", "here", "this position") — do NOT restate the full role title and company each turn.
- Ask questions in order. Precede each with ONE sentence of context, then ask it in your own words (keep its meaning). No lecturing.
- Be warm but neutral — an interviewer, not a cheerleader. Do NOT praise, judge, or use enthusiastic fillers like "that's interesting", "great", "awesome".
- Acknowledge each answer BRIEFLY, matching its tone: neutral for a factual answer ("Got it.", "Understood."); measured for a negative one ("Okay — thanks for being honest.") — never react positively to a negative statement.
- Vary your acknowledgments — a short listener cue is often enough ("Mm-hmm.", "I see.", "Right.").
- If the answer is vague, ask ONE short follow-up then move on. Never more than one follow-up per question; keep every turn to one or two sentences.
- If the candidate goes off-topic (product feedback, a refusal, or nonsense): briefly name it ("That's a bit off track — let's refocus.") and move to the NEXT question. Do NOT restart your greeting or repeat the opening question verbatim more than once. If they disengage for several questions in a row, wrap up early with your closing line.
- Speak like a real person — calm and unhurried, with natural pauses; give a beat to think after each question.
- No hints, coaching, or feedback during the session — never invent facts or numbers.
- When all questions are done, thank the candidate warmly in one sentence, then say exactly, as your final words: "That concludes our practice interview." """


def interviewer_context_turn(
    interview: dict, session_questions: list[dict], *,
    brief: Optional[dict] = None, persona: str = "",
) -> str:
    """The first user-role turn the client injects after connect (kept OUT of the
    pinned system instruction so it stays short). Carries the candidate/company
    context + the ordered questions, then tells the coach to begin."""
    ctx = _context_block(brief, persona)
    q_lines = "\n".join(
        f'{i+1}. {str(q.get("text","")).strip()}'
        for i, q in enumerate(session_questions) if str(q.get("text", "")).strip()
    )
    return f"""Context for this interview (use only this — never invent facts or numbers):
{ctx}
Questions to cover, in order:
{q_lines}

Now begin: greet me briefly, then ask your first question."""


def _context_block(brief: Optional[dict], persona: str) -> str:
    """A 'what you know' block from the cached brief + résumé persona, so the
    live coach isn't flying blind. Empty string when nothing is available."""
    if not brief and not persona:
        return ""
    lines: list[str] = ["\nWhat you know:"]
    if persona:
        lines.append(f"- The candidate: {persona.strip()}")
    if isinstance(brief, dict):
        summary = str(brief.get("role_summary", "")).strip()
        if summary:
            lines.append(f"- The role: {summary}")
        snapshot = [str(p.get("point", "")).strip()
                    for p in (brief.get("company_snapshot") or []) if isinstance(p, dict)]
        snapshot = [s for s in snapshot if s][:3]
        if snapshot:
            lines.append("- The company: " + "; ".join(snapshot))
        comps = [f'{str(c.get("name","")).strip()} ({str(c.get("what_good_looks_like","")).strip()})'
                 for c in (brief.get("competencies") or []) if isinstance(c, dict) and c.get("name")]
        if comps:
            lines.append("- Competencies you're probing: " + "; ".join(comps[:6]))
    return "\n".join(lines) + "\n"


# ---------- session shaping (code) ----------

def pick_session_questions(
    questions: list[dict], *, length: str = DEFAULT_LENGTH,
    focus_competency: Optional[str] = None,
) -> list[dict]:
    """Choose the questions for one session (D6): keep flow order, cap at the
    length preset, and — when a focus competency is set — lead with its questions
    (openers always allowed through so the session still opens naturally)."""
    n = SESSION_LENGTHS.get(length, SESSION_LENGTHS[DEFAULT_LENGTH])
    items = [q for q in questions if isinstance(q, dict) and str(q.get("text", "")).strip()]
    if focus_competency:
        focused = [q for q in items if q.get("competency_id") == focus_competency
                   or q.get("type") == "opener"]
        items = focused or items
    return items[:n]


def target_seconds_for(question: dict) -> int:
    return TARGET_SECONDS.get(str(question.get("type", "")).strip(), DEFAULT_TARGET)


# ---------- delivery metrics (code, real numbers) ----------

def delivery_metrics(transcript: str, seconds: int, target_seconds: int = DEFAULT_TARGET) -> dict:
    """Real, code-computed delivery numbers for one answer: word count, words per
    minute, filler count, and a length band vs the target. The model never counts
    these (unreliable) — this is the honest-numbers exception (design brief §4)."""
    text = (transcript or "").strip()
    words = _WORD_RE.findall(text.lower())
    wc = len(words)
    wpm = round(wc / (seconds / 60)) if seconds and seconds > 0 else 0

    joined = " ".join(words)
    fillers = sum(1 for w in words if w in _FILLER_SINGLE)
    for phrase in _FILLER_PHRASES:
        fillers += joined.count(phrase)

    if seconds and target_seconds:
        ratio = seconds / target_seconds
        length_band = "short" if ratio < 0.6 else ("long" if ratio > 1.4 else "on_target")
    else:
        length_band = "unknown"

    return {"seconds": int(seconds or 0), "word_count": wc, "wpm": wpm,
            "filler_count": fillers, "length_band": length_band}


# ---------- P8: evaluate one answer ----------

@dataclass
class AnswerEval:
    question_id: str
    ratings: dict           # answered_the_question, structure, personal_action, result_evidence, relevance
    overall: str            # strong | solid | needs_work
    what_worked: dict       # {quote, why}
    fix: str
    stronger_version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_RATING_KEYS = ("answered_the_question", "structure", "personal_action",
                "result_evidence", "relevance")


def evaluate_answer(
    question: dict,
    competency: Optional[dict],
    story: Optional[dict],
    transcript: str,
    client: GeminiClient,
    *,
    answer_seconds: int = 0,
    target_seconds: int = DEFAULT_TARGET,
    lang: Optional[str] = None,
) -> Optional[AnswerEval]:
    """P8 — rate one answer against its competency rubric. None on failure or an
    empty transcript. Delivery metrics are NOT asked of the model here (computed
    separately in `delivery_metrics`)."""
    if not (transcript or "").strip() or client.all_models_exhausted():
        return None
    lang = lang if lang is not None else get_output_language()
    prompt = _build_p8_prompt(question, competency, story, transcript,
                              answer_seconds, target_seconds, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    return _parse_eval(raw, question_id=str(question.get("id", "")))


def _build_p8_prompt(question, competency, story, transcript, seconds, target, *, lang) -> str:
    comp_name = (competency or {}).get("name", "(general)") if competency else "(general)"
    comp_good = (competency or {}).get("what_good_looks_like", "") if competency else ""
    story_block = "(none)"
    if story:
        story_block = (f"Title: {story.get('title','')}\n"
                       f"S: {story.get('situation','')}\nT: {story.get('task','')}\n"
                       f"A: {story.get('action','')}\nR: {story.get('result','')}")
    return f"""You are evaluating one interview answer for a practising candidate.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Evaluate one interview answer.

Rate each item as strong, solid, or needs_work:
1. answered_the_question: Did they answer what was asked?
2. structure: Is there a clear situation, action, and result?
3. personal_action: Is it clear what they did personally?
4. result_evidence: Is there a concrete result or number?
5. relevance: Does it show the competency this question tests?

Then:
- Overall band for the answer.
- One thing that worked (quote a short part of the answer).
- One thing to fix, as a clear instruction.
- If overall is needs_work or solid: write a stronger version in 4-6 sentences. Use only facts from the answer and the candidate's story. Do not invent numbers.

Question: {str(question.get('text','')).strip()}
Competency tested: {comp_name} — {comp_good}
Candidate's mapped story (may be empty):
{story_block}
Transcript of the answer (including any follow-up):
---
{P.clip(transcript, MAX_ANSWER_CHARS)}
---
Answer length: {seconds} seconds. Target: {target} seconds.

Return JSON with this exact schema — no prose before or after:
{{
  "ratings": {{ "answered_the_question": "strong|solid|needs_work", "structure": "...",
    "personal_action": "...", "result_evidence": "...", "relevance": "..." }},
  "overall": "strong|solid|needs_work",
  "what_worked": {{ "quote": "string", "why": "string" }},
  "fix": "string",
  "stronger_version": "string | null"
}}"""


def _parse_eval(raw: Any, *, question_id: str) -> Optional[AnswerEval]:
    if not isinstance(raw, dict):
        return None
    ratings_in = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    ratings = {k: P.band_or_default(ratings_in.get(k)) for k in _RATING_KEYS}
    ww_in = raw.get("what_worked") if isinstance(raw.get("what_worked"), dict) else {}
    what_worked = {"quote": str(ww_in.get("quote", "")).strip(),
                   "why": str(ww_in.get("why", "")).strip()}
    stronger = raw.get("stronger_version")
    stronger = str(stronger).strip() if stronger not in (None, "") else None
    return AnswerEval(
        question_id=question_id,
        ratings=ratings,
        overall=P.band_or_default(raw.get("overall")),
        what_worked=what_worked,
        fix=str(raw.get("fix", "")).strip(),
        stronger_version=stronger,
    )


# ---------- P9: session debrief ----------

@dataclass
class Debrief:
    takeaway: str = ""
    competency_bands: list[dict] = field(default_factory=list)   # [{competency_id, band}]
    top_actions: list[str] = field(default_factory=list)
    stories_to_revisit: list[dict] = field(default_factory=list)  # [{story_id, why}]
    next_drill: dict = field(default_factory=dict)                # {competency_id|null, question_id|null, reason}

    def is_empty(self) -> bool:
        return not (self.takeaway or self.competency_bands or self.top_actions)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def session_debrief(
    evaluations: list[dict],
    delivery_metrics_list: list[dict],
    competencies: list[dict],
    client: GeminiClient,
    *,
    lang: Optional[str] = None,
) -> Optional[Debrief]:
    """P9 — the end-of-session debrief from the per-answer evaluations + delivery
    metrics. None on failure or no evaluations."""
    if not evaluations or client.all_models_exhausted():
        return None
    lang = lang if lang is not None else get_output_language()
    prompt = _build_p9_prompt(evaluations, delivery_metrics_list, competencies, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    valid_comps = {str(c.get("id", "")).strip() for c in competencies if isinstance(c, dict)}
    return _parse_debrief(raw, valid_comps=valid_comps)


def session_debrief_from_transcript(
    transcript: list[dict],
    questions: list[dict],
    competencies: list[dict],
    client: GeminiClient,
    *,
    lang: Optional[str] = None,
) -> Optional[Debrief]:
    """P9 for the live-voice path — one debrief over the WHOLE conversation
    transcript (the model conducted the interview, so there are no per-answer P8
    evals to aggregate). Same output shape as `session_debrief`. None on failure
    or an empty transcript."""
    turns = [t for t in (transcript or []) if isinstance(t, dict) and str(t.get("text", "")).strip()]
    if not turns or client.all_models_exhausted():
        return None
    lang = lang if lang is not None else get_output_language()
    prompt = _build_p9_transcript_prompt(turns, questions, competencies, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    valid = {str(c.get("id", "")).strip() for c in competencies if isinstance(c, dict)}
    return _parse_debrief(raw, valid_comps=valid)


def _build_p9_transcript_prompt(turns, questions, competencies, *, lang) -> str:
    convo = "\n".join(
        f'{"Interviewer" if t.get("role") == "coach" else "Candidate"}: {str(t.get("text","")).strip()}'
        for t in turns
    )
    q_lines = "\n".join(f'- {str(q.get("text","")).strip()}'
                        for q in questions if str(q.get("text", "")).strip())
    return f"""You are debriefing a candidate's practice interview from its full transcript.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Write the debrief for this practice interview, judging the CANDIDATE's answers only.

Do this:
1. Write one takeaway sentence: the biggest strength and the biggest thing to improve.
2. Give one band per competency (strong/solid/needs_work), based on how the candidate's answers demonstrated it across the conversation.
3. List the top 3 actions for next time. Each action is specific and doable in one practice session.
4. Suggest the focus for the next drill: one competency or one question.

Questions the interview aimed to cover:
{q_lines}

Competencies:
{P.format_competencies(competencies)}

Transcript:
---
{convo}
---

Return JSON with this exact schema — no prose before or after:
{{
  "takeaway": "string",
  "competency_bands": [{{ "competency_id": "c1", "band": "strong|solid|needs_work" }}],
  "top_actions": ["string", "string", "string"],
  "stories_to_revisit": [],
  "next_drill": {{ "competency_id": "c1 | null", "question_id": null, "reason": "string" }}
}}"""


def _build_p9_prompt(evaluations, delivery, competencies, *, lang) -> str:
    import json
    return f"""You are writing the debrief for a candidate's practice interview session.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Write the debrief for a full practice session.

Do this:
1. Write one takeaway sentence: the biggest strength and the biggest thing to improve.
2. Give one band per competency practiced, based on the answer evaluations.
3. List the top 3 actions for next time. Each action is specific and doable in one practice session.
4. List any stories to revisit and why (one sentence each).
5. Suggest the focus for the next drill: one competency or one question.

Answer evaluations:
{json.dumps(evaluations, ensure_ascii=False)}

Delivery metrics per answer:
{json.dumps(delivery, ensure_ascii=False)}

Competencies:
{P.format_competencies(competencies)}

Return JSON with this exact schema — no prose before or after:
{{
  "takeaway": "string",
  "competency_bands": [{{ "competency_id": "c1", "band": "strong|solid|needs_work" }}],
  "top_actions": ["string", "string", "string"],
  "stories_to_revisit": [{{ "story_id": "s1", "why": "string" }}],
  "next_drill": {{ "competency_id": "c1 | null", "question_id": "q1 | null", "reason": "string" }}
}}"""


def _parse_debrief(raw: Any, *, valid_comps: set[str]) -> Optional[Debrief]:
    if not isinstance(raw, dict):
        return None
    bands = []
    for b in (raw.get("competency_bands") or []):
        if not isinstance(b, dict):
            continue
        cid = str(b.get("competency_id", "")).strip()
        if valid_comps and cid not in valid_comps:
            continue
        bands.append({"competency_id": cid, "band": P.band_or_default(b.get("band"))})
    actions = [str(a).strip() for a in (raw.get("top_actions") or []) if str(a).strip()][:3]
    revisit = [{"story_id": str(s.get("story_id", "")).strip(), "why": str(s.get("why", "")).strip()}
               for s in (raw.get("stories_to_revisit") or [])
               if isinstance(s, dict) and str(s.get("story_id", "")).strip()]
    nd_in = raw.get("next_drill") if isinstance(raw.get("next_drill"), dict) else {}
    next_drill = {
        "competency_id": (str(nd_in.get("competency_id")).strip()
                          if nd_in.get("competency_id") not in (None, "") else None),
        "question_id": (str(nd_in.get("question_id")).strip()
                        if nd_in.get("question_id") not in (None, "") else None),
        "reason": str(nd_in.get("reason", "")).strip(),
    }
    return Debrief(
        takeaway=str(raw.get("takeaway", "")).strip(),
        competency_bands=bands, top_actions=actions,
        stories_to_revisit=revisit, next_drill=next_drill,
    )
