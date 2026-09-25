"""P2 Likely questions (ADR-048, REQ-041) — the second pipeline call, fanning
out from P1's competencies. Writes the 8–12 questions this interview will most
likely include, 1–2 per competency plus the standard openers, following the
round-type mix (D7). Each question carries its competency_id (the join key back
to the brief), why they ask it, and one likely follow-up.

Runs AFTER the brief is cached — it takes the brief's `competencies` as input so
every question traces to a competency (ADR-048: no orphan questions). Read-only
cache in `prep_artifacts` keyed (interview, lang, prompt_version);
temperature=0.0. Questions with no text are dropped; a competency_id the brief
didn't define is nulled (never a dangling join).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.settings import get_output_language, language_instruction

from . import prompts as P

PROMPT_VERSION = "2026-09-21-questions-v1"
ARTIFACT_KIND = "questions"

MIN_QUESTIONS = 8
MAX_QUESTIONS = 12
VALID_TYPES = ("opener", "behavioral", "situational", "technical")
DEFAULT_TYPE = "behavioral"


@dataclass
class Question:
    id: str
    text: str
    type: str
    competency_id: Optional[str]
    why_they_ask: str
    follow_up: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_lang(lang: Optional[str]) -> str:
    return lang if lang is not None else get_output_language()


def _row_to_questions(row: dict) -> list[Question]:
    a = row.get("artifact") or {}
    items = a.get("questions") if isinstance(a, dict) else None
    return _parse_questions(items, valid_ids=None)


def get_or_generate_questions(
    interview: dict,
    competencies: list[dict],
    client: GeminiClient,
    *,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> Optional[list[Question]]:
    """Cache-aware entry point. `competencies` is P1's list (dicts with id/name/
    what_good_looks_like) — pass the cached brief's competencies so the ids
    line up. Returns the question list, generating + caching on a miss. None on
    failure or an empty list."""
    interview_id = interview.get("id")
    if not interview_id or not competencies:
        return None
    lang = _resolve_lang(lang)

    if use_cache:
        cached = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, PROMPT_VERSION, path=path)
        if cached is not None:
            return _row_to_questions(cached)

    if client.all_models_exhausted():
        return None

    valid_ids = {str(c.get("id", "")).strip() for c in competencies if isinstance(c, dict)}
    questions = _generate(interview, competencies, client, lang=lang, valid_ids=valid_ids)
    if not questions:
        return None

    model_used = client.last_model_used or client.model_name or ""
    db.save_prep_artifact(
        interview_id, ARTIFACT_KIND, lang, PROMPT_VERSION,
        {"questions": [q.to_dict() for q in questions]}, model_used, path=path)
    return questions


def _generate(
    interview: dict, competencies: list[dict], client: GeminiClient,
    *, lang: str, valid_ids: set[str],
) -> list[Question]:
    prompt = _build_prompt(interview, competencies, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return []
    items = raw.get("questions") if isinstance(raw, dict) else None
    return _parse_questions(items, valid_ids=valid_ids)


def _build_prompt(interview: dict, competencies: list[dict], *, lang: str) -> str:
    round_type = (interview.get("round_type") or "screening").strip()
    jd = P.clip(interview.get("jd_text") or "", P.MAX_JD_CHARS)
    jd_block = jd if jd else "(not provided — use the role title and competencies)"

    return f"""You are helping a candidate prepare for a {round_type} interview.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Write the questions this interview will most likely include.

Do this:
1. Write 1 or 2 questions per competency. Use behavioral questions ("Tell me about a time...") and situational questions ("What would you do if...").
2. Add the standard openers that fit this round: "Tell me about yourself", "Why this company?", "Why this role?".
3. Follow this mix for the round type:
   - screening: mostly openers and motivation, 1-2 behavioral
   - behavioral: mostly behavioral, one per competency
   - technical: role knowledge questions plus 1-2 behavioral
   - case: situational and problem-solving questions
   - hiring_manager: behavioral, situational, and one "first 90 days" question
   - final_panel: a mix of all, harder
4. For each question: say why they ask it (one sentence) and give one likely follow-up.
5. For each question, set competency_id to the id of the competency it tests (from the list below), or null for a general opener.
6. Total: {MIN_QUESTIONS} to {MAX_QUESTIONS} questions. Order them as a real interview would flow.

Round type: {round_type}

Competencies (from the brief — use these ids):
{P.format_competencies(competencies)}

Job description:
---
{jd_block}
---

Return JSON with this exact schema — no prose before or after:
{{
  "questions": [
    {{ "id": "q1", "text": "string", "type": "opener | behavioral | situational | technical",
       "competency_id": "c1 | null", "why_they_ask": "string", "follow_up": "string" }}
  ]
}}"""


def _parse_questions(items: Any, *, valid_ids: Optional[set[str]]) -> list[Question]:
    """Keep well-formed questions, re-id them q1..qN so ordering is dense, cap at
    MAX_QUESTIONS. A competency_id not in `valid_ids` is nulled — we never keep a
    join that points at a competency the brief didn't define. `valid_ids=None`
    (the cache-read path) trusts the stored ids as-is."""
    out: list[Question] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text", "")).strip()
        if not text:
            continue
        qtype = str(it.get("type", "")).strip().lower()
        if qtype not in VALID_TYPES:
            qtype = DEFAULT_TYPE
        cid = it.get("competency_id")
        cid = str(cid).strip() if cid not in (None, "") else None
        if cid is not None and valid_ids is not None and cid not in valid_ids:
            cid = None
        out.append(Question(
            id=f"q{len(out) + 1}",
            text=text,
            type=qtype,
            competency_id=cid,
            why_they_ask=str(it.get("why_they_ask", "")).strip(),
            follow_up=str(it.get("follow_up", "")).strip(),
        ))
        if len(out) >= MAX_QUESTIONS:
            break
    return out
