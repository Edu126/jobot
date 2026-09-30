"""P4 Answer cards (ADR-056, REQ-041) — the last toolkit call. It no longer
invents its own study questions: it ANSWERS the P2 likely questions, in the
candidate's own voice, so Get Ready is "rehearse what you'll say".

  - answers[] (one per P2 question): question_id (join key back to P2) +
    answer — 2–4 first-person sentences grounded in the résumé and the story
    P3 mapped to that question's competency — + point_to_land (one line: the
    message this answer should leave behind; replaces the old talking points);
  - questions_to_ask[] (3): smart questions the candidate asks the interviewer.

Runs AFTER P2 and P3 (it needs their output), so the cache key folds a
fingerprint of the brief, the questions and the mapping into the version: any of
them changes → a miss, never stale. Cache in `prep_artifacts`
(interview, 'answer_cards', lang, version+fingerprint); temperature=0.0. An
answer whose question_id P2 didn't define is dropped (no dangling join).

History: v1 (2026-09-21) wrote 8–12 free-standing flashcards + talking points.
Eduardo (2026-09-29): third-person trivia that echoed the Brief; cards should be
question → MY answer, NotebookLM-style, with self-rating (see card_reviews).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.settings import get_output_language, language_instruction

from . import prompts as P

PROMPT_VERSION = "2026-09-30-answers-v2"
ARTIFACT_KIND = "answer_cards"

MAX_ANSWERS = 12
MAX_QUESTIONS_TO_ASK = 3


@dataclass
class AnswerCard:
    question_id: str
    answer: str
    point_to_land: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StudyKit:
    answers: list[AnswerCard] = field(default_factory=list)
    questions_to_ask: list[str] = field(default_factory=list)
    created_at: str = ""

    def is_empty(self) -> bool:
        return not (self.answers or self.questions_to_ask)

    def by_question(self) -> dict[str, AnswerCard]:
        return {a.question_id: a for a in self.answers}

    def to_dict_for_cache(self) -> dict[str, Any]:
        return {
            "answers": [a.to_dict() for a in self.answers],
            "questions_to_ask": self.questions_to_ask,
        }


def _resolve_lang(lang: Optional[str]) -> str:
    return lang if lang is not None else get_output_language()


def _fingerprint(brief: dict, questions: list[dict], mapping: list[dict]) -> str:
    """Short digest of everything P4 stands on: the brief (role summary +
    competency ids/names), the P2 questions (id + text) and the P3 mapping
    (competency → story). Any change → a cache miss."""
    comps = sorted(
        (str(c.get("id", "")), str(c.get("name", "")))
        for c in (brief.get("competencies") or []) if isinstance(c, dict)
    )
    qs = [(str(q.get("id", "")), str(q.get("text", ""))) for q in questions if isinstance(q, dict)]
    mp = sorted(
        (str(m.get("competency_id", "")), str(m.get("story_id") or ""))
        for m in mapping if isinstance(m, dict)
    )
    blob = json.dumps({"r": str(brief.get("role_summary", "")), "c": comps, "q": qs, "m": mp},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _cache_version(brief: dict, questions: list[dict], mapping: list[dict]) -> str:
    return f"{PROMPT_VERSION}:{_fingerprint(brief, questions, mapping)}"


def _row_to_kit(row: dict) -> StudyKit:
    kit = _parse_kit(row.get("artifact") or {}, valid_qids=None)
    kit.created_at = row.get("created_at", "")
    return kit


def get_or_generate_answers(
    interview: dict,
    brief: dict,
    questions: list[dict],
    mapping: list[dict],
    stories: list[dict],
    resume_text: str,
    client: GeminiClient,
    *,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> Optional[StudyKit]:
    """Cache-aware entry point. `brief` = P1's cached dict, `questions` = P2 as
    dicts (id/text/type/competency_id), `mapping` = P3 as dicts
    (competency_id/story_id/angle_for_this_role), `stories` = the saved Story
    Bank (to name the mapped story). Returns the kit, generating + caching on a
    miss. None on failure, an empty kit, or no questions / résumé."""
    interview_id = interview.get("id")
    if not interview_id or not resume_text.strip() or not questions:
        return None
    lang = _resolve_lang(lang)
    version = _cache_version(brief, questions, mapping)

    if use_cache:
        cached = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
        if cached is not None:
            return _row_to_kit(cached)

    if client.all_models_exhausted():
        return None

    kit = _generate(interview, brief, questions, mapping, stories, resume_text, client, lang=lang)
    if kit is None or kit.is_empty():
        return None

    model_used = client.last_model_used or client.model_name or ""
    db.save_prep_artifact(interview_id, ARTIFACT_KIND, lang, version,
                          kit.to_dict_for_cache(), model_used, path=path)
    stored = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
    return _row_to_kit(stored) if stored else kit


def _generate(
    interview: dict, brief: dict, questions: list[dict], mapping: list[dict],
    stories: list[dict], resume_text: str, client: GeminiClient, *, lang: str,
) -> Optional[StudyKit]:
    prompt = _build_prompt(interview, brief, questions, mapping, stories, resume_text, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    valid = {str(q.get("id", "")) for q in questions if isinstance(q, dict)}
    return _parse_kit(raw, valid_qids=valid)


def _questions_block(questions: list[dict], mapping: list[dict], stories: list[dict]) -> str:
    """One line per question, with the story P3 mapped to its competency (title
    + angle) so every answer can lean on the SAME story the Stories tab shows."""
    by_comp = {str(m.get("competency_id", "")): m for m in mapping if isinstance(m, dict)}
    titles = {str(s.get("id", "")): str(s.get("title", "")).strip() for s in stories if isinstance(s, dict)}
    lines: list[str] = []
    for q in questions:
        if not isinstance(q, dict) or not str(q.get("text", "")).strip():
            continue
        line = f'- {q.get("id")} [{q.get("type", "behavioral")}]: {str(q.get("text")).strip()}'
        m = by_comp.get(str(q.get("competency_id") or ""))
        if m and m.get("story_id") and titles.get(str(m["story_id"])):
            line += f'\n    use my story: "{titles[str(m["story_id"])]}"'
            if m.get("angle_for_this_role"):
                line += f' — angle: {str(m["angle_for_this_role"]).strip()}'
        lines.append(line)
    return "\n".join(lines)


def _build_prompt(
    interview: dict, brief: dict, questions: list[dict], mapping: list[dict],
    stories: list[dict], resume_text: str, *, lang: str,
) -> str:
    company = (interview.get("company") or "").strip() or "(unknown company)"
    role = (interview.get("role_title") or "").strip() or "(unknown role)"
    resume = P.clip(resume_text, P.MAX_RESUME_CHARS)
    comps = P.format_competencies(brief.get("competencies") or [])

    return f"""You are helping me rehearse for a {role} interview at {company}. Write MY answers to the questions the interviewer will most likely ask.

{P.RULE_BLOCK}
- Write as me, in the first person ("I led…", "In my role at…"). Never use my name, never say "the candidate", never "he/she".
- Each answer is what I would actually say out loud: 2 to 4 sentences, concrete (the real employer, tools and numbers from my résumé), in a light Situation → Action → Result order.
- When a question has "use my story", build the answer on that story.
- If my résumé has no direct evidence for a question, do not invent it: answer honestly with the closest real experience and how it transfers.

{language_instruction(lang)}

Task:
1. For EVERY question below, write "answer" (my spoken answer) and "point_to_land" (one short line: the one thing the interviewer should remember from this answer). Keep each question's id.
2. Write {MAX_QUESTIONS_TO_ASK} smart questions I can ask the interviewer at the end, based on the role and the company.

Questions:
{_questions_block(questions, mapping, stories)}

What this role looks for (competencies):
{comps}

My résumé:
---
{resume}
---

Return JSON with this exact schema — no prose before or after:
{{
  "answers": [{{ "question_id": "q1", "answer": "string", "point_to_land": "string" }}],
  "questions_to_ask": ["string"]
}}"""


# ---------- parsing ----------

def _parse_kit(raw: Any, *, valid_qids: Optional[set[str]]) -> StudyKit:
    if not isinstance(raw, dict):
        return StudyKit()
    return StudyKit(
        answers=_parse_answers(raw.get("answers"), valid_qids=valid_qids),
        questions_to_ask=_parse_str_list(raw.get("questions_to_ask"), MAX_QUESTIONS_TO_ASK),
    )


def _parse_answers(items: Any, *, valid_qids: Optional[set[str]]) -> list[AnswerCard]:
    """Keep answers that point at a real P2 question (unknown/duplicate ids
    dropped — no dangling join); blank answers dropped. `valid_qids=None` (the
    cache-read path) trusts stored ids."""
    out: list[AnswerCard] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        qid = str(it.get("question_id", "")).strip()
        answer = str(it.get("answer", "")).strip()
        if not qid or not answer or qid in seen:
            continue
        if valid_qids is not None and qid not in valid_qids:
            continue
        seen.add(qid)
        out.append(AnswerCard(question_id=qid, answer=answer,
                              point_to_land=str(it.get("point_to_land", "")).strip()))
        if len(out) >= MAX_ANSWERS:
            break
    return out


def _parse_str_list(items: Any, cap: int) -> list[str]:
    if not isinstance(items, list):
        return []
    out = [str(x).strip() for x in items if str(x).strip()]
    return out[:cap]
