"""P4 Flashcards & talking points (ADR-048, REQ-041) — the last of the toolkit
fan-out. From the brief (P1) + résumé it writes short study material:

  - flashcards[] (8–12): front = a question the candidate should be able to
    answer; back = a 1–3 sentence answer grounded only in the inputs;
  - talking_points[] (5): each ties a résumé strength to a JD need;
  - questions_to_ask[] (3): smart questions the candidate asks the interviewer.

Depends on the brief's content, so — like P3 with the Story Bank — the cache key
folds a **brief fingerprint** into the version: regenerate the brief and the
flashcards are a miss, never stale. Cache in `prep_artifacts`
(interview, 'flashcards', lang, version+fingerprint); temperature=0.0. A
flashcard competency_id the brief didn't define is nulled (no dangling join).
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

PROMPT_VERSION = "2026-09-21-flashcards-v1"
ARTIFACT_KIND = "flashcards"

MIN_FLASHCARDS = 8
MAX_FLASHCARDS = 12
MAX_TALKING_POINTS = 5
MAX_QUESTIONS_TO_ASK = 3


@dataclass
class Flashcard:
    front: str
    back: str
    competency_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TalkingPoint:
    message: str
    resume_evidence: str
    jd_need: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StudyKit:
    flashcards: list[Flashcard] = field(default_factory=list)
    talking_points: list[TalkingPoint] = field(default_factory=list)
    questions_to_ask: list[str] = field(default_factory=list)
    created_at: str = ""

    def is_empty(self) -> bool:
        return not (self.flashcards or self.talking_points or self.questions_to_ask)

    def to_dict_for_cache(self) -> dict[str, Any]:
        return {
            "flashcards": [f.to_dict() for f in self.flashcards],
            "talking_points": [t.to_dict() for t in self.talking_points],
            "questions_to_ask": self.questions_to_ask,
        }


def _resolve_lang(lang: Optional[str]) -> str:
    return lang if lang is not None else get_output_language()


def _brief_fingerprint(brief: dict) -> str:
    """Short digest of the brief content P4 stands on (role summary + the
    competency ids/names). Any brief change → a flashcards cache miss."""
    comps = sorted(
        (str(c.get("id", "")), str(c.get("name", "")))
        for c in (brief.get("competencies") or []) if isinstance(c, dict)
    )
    blob = json.dumps({"r": str(brief.get("role_summary", "")), "c": comps},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _cache_version(brief: dict) -> str:
    return f"{PROMPT_VERSION}:{_brief_fingerprint(brief)}"


def _brief_competency_ids(brief: dict) -> set[str]:
    return {str(c.get("id", "")).strip() for c in (brief.get("competencies") or [])
            if isinstance(c, dict)}


def _row_to_kit(row: dict) -> StudyKit:
    a = row.get("artifact") or {}
    kit = _parse_kit(a, valid_ids=None)
    kit.created_at = row.get("created_at", "")
    return kit


def get_or_generate_flashcards(
    interview: dict,
    brief: dict,
    resume_text: str,
    client: GeminiClient,
    *,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> Optional[StudyKit]:
    """Cache-aware entry point. `brief` is P1's cached dict (needs competencies +
    role_summary); `resume_text` grounds the answers. Returns the study kit,
    generating + caching on a miss. None on failure, an empty kit, or a brief
    with no competencies (nothing to build from)."""
    interview_id = interview.get("id")
    if not interview_id or not resume_text.strip():
        return None
    if not (brief.get("competencies") if isinstance(brief, dict) else None):
        return None
    lang = _resolve_lang(lang)
    version = _cache_version(brief)

    if use_cache:
        cached = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
        if cached is not None:
            return _row_to_kit(cached)

    if client.all_models_exhausted():
        return None

    kit = _generate(interview, brief, resume_text, client, lang=lang)
    if kit is None or kit.is_empty():
        return None

    model_used = client.last_model_used or client.model_name or ""
    db.save_prep_artifact(interview_id, ARTIFACT_KIND, lang, version,
                          kit.to_dict_for_cache(), model_used, path=path)
    stored = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
    return _row_to_kit(stored) if stored else kit


def _generate(
    interview: dict, brief: dict, resume_text: str, client: GeminiClient, *, lang: str,
) -> Optional[StudyKit]:
    prompt = _build_prompt(interview, brief, resume_text, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    return _parse_kit(raw, valid_ids=_brief_competency_ids(brief))


def _build_prompt(interview: dict, brief: dict, resume_text: str, *, lang: str) -> str:
    company = (interview.get("company") or "").strip() or "(unknown company)"
    role = (interview.get("role_title") or "").strip() or "(unknown role)"
    resume = P.clip(resume_text, P.MAX_RESUME_CHARS)
    brief_block = json.dumps(_brief_for_prompt(brief), ensure_ascii=False, indent=2)

    return f"""You are helping a candidate prepare for a {role} interview at {company}.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Create short study material for this interview.

Do this:
1. Write {MIN_FLASHCARDS} to {MAX_FLASHCARDS} flashcards. Front: a question the candidate should be able to answer (about the role, the company, or their own experience). Back: a short answer in 1-3 sentences, based only on the inputs. Set competency_id to the competency it belongs to (from the brief), or null.
2. Write {MAX_TALKING_POINTS} talking points: key messages the candidate should land during the interview. Each one ties a résumé strength to a need in the job description.
3. Write {MAX_QUESTIONS_TO_ASK} smart questions the candidate can ask the interviewer, based on the brief and round type.

Brief:
{brief_block}

Résumé:
---
{resume}
---

Return JSON with this exact schema — no prose before or after:
{{
  "flashcards": [{{ "front": "string", "back": "string", "competency_id": "c1 | null" }}],
  "talking_points": [{{ "message": "string", "resume_evidence": "string", "jd_need": "string" }}],
  "questions_to_ask": ["string"]
}}"""


def _brief_for_prompt(brief: dict) -> dict:
    """A trimmed brief for the prompt — the fields P4 actually uses. Keeps the
    token cost down vs. dumping the whole cached blob (which carries evidence
    quotes and friction points P4 doesn't read)."""
    comps = [
        {"id": str(c.get("id", "")), "name": str(c.get("name", "")),
         "what_good_looks_like": str(c.get("what_good_looks_like", ""))}
        for c in (brief.get("competencies") or []) if isinstance(c, dict)
    ]
    snapshot = [
        {"point": str(p.get("point", ""))}
        for p in (brief.get("company_snapshot") or []) if isinstance(p, dict)
    ]
    return {
        "role_summary": str(brief.get("role_summary", "")),
        "company_snapshot": snapshot,
        "competencies": comps,
    }


# ---------- parsing ----------

def _parse_kit(raw: Any, *, valid_ids: Optional[set[str]]) -> StudyKit:
    if not isinstance(raw, dict):
        return StudyKit()
    return StudyKit(
        flashcards=_parse_flashcards(raw.get("flashcards"), valid_ids=valid_ids),
        talking_points=_parse_talking_points(raw.get("talking_points")),
        questions_to_ask=_parse_str_list(raw.get("questions_to_ask"), MAX_QUESTIONS_TO_ASK),
    )


def _parse_flashcards(items: Any, *, valid_ids: Optional[set[str]]) -> list[Flashcard]:
    out: list[Flashcard] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        front = str(it.get("front", "")).strip()
        back = str(it.get("back", "")).strip()
        if not front or not back:
            continue
        cid = it.get("competency_id")
        cid = str(cid).strip() if cid not in (None, "") else None
        if cid is not None and valid_ids is not None and cid not in valid_ids:
            cid = None
        out.append(Flashcard(front=front, back=back, competency_id=cid))
        if len(out) >= MAX_FLASHCARDS:
            break
    return out


def _parse_talking_points(items: Any) -> list[TalkingPoint]:
    out: list[TalkingPoint] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        message = str(it.get("message", "")).strip()
        if not message:
            continue
        out.append(TalkingPoint(
            message=message,
            resume_evidence=str(it.get("resume_evidence", "")).strip(),
            jd_need=str(it.get("jd_need", "")).strip(),
        ))
        if len(out) >= MAX_TALKING_POINTS:
            break
    return out


def _parse_str_list(items: Any, cap: int) -> list[str]:
    if not isinstance(items, list):
        return []
    out = [str(x).strip() for x in items if str(x).strip()]
    return out[:cap]
