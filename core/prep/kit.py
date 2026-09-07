"""Prep kit generation (REQ-023 / ADR-028) — the STAR Q&A bank + reverse
interview questions behind the mockup's two lower panels.

One JSON-mode Gemini call turns (résumé × job/vacancy × any known real gaps)
into:
  - star_qa: likely interview questions across kinds. Experience-backed ones
    (behavioral / situational) answer as a STAR grounded ONLY in real résumé
    experience — if nothing in the résumé supports it, the item is DROPPED,
    never invented (grounded-or-none, ADR-005 / GOV-005). why_you / culture_fit
    / defensive_gap answer as honest talking points.
  - reverse_qs: smart questions the candidate asks, grouped by category.

Defense reuse (ADR-028): when the session is bound to a job we've already
enhanced (REQ-018), its REAL gaps + defense hooks seed the defensive_gap
questions — the enhance→prepare seam. A real gap IS the likely objection.

Read-only cache in `prep_kits` keyed (session, lang, prompt_version); no
user-edit layer (copy-first). temperature=0.0 for reproducibility.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.matching import gap_enhance
from core.resume import ai_summary
from core.settings import get_output_language, language_instruction

# Bump on any prompt change — a version mismatch on read is a miss (regenerate),
# never a delete (same convention as gap_enhance.PROMPT_VERSION).
PROMPT_VERSION = "2026-09-03-star-reverse-v1"

MAX_RESUME_CHARS = 12000
MAX_JD_CHARS = 2500
MAX_QA = 8
MAX_REVERSE = 9

STAR_KINDS = ("behavioral", "situational")
TALKING_KINDS = ("why_you", "culture_fit", "defensive_gap")
VALID_KINDS = STAR_KINDS + TALKING_KINDS


@dataclass
class QAItem:
    kind: str
    question: str
    star: Optional[dict] = None          # {situation, task, action, result}
    talking_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "question": self.question}
        if self.star:
            d["star"] = self.star
        if self.talking_points:
            d["talking_points"] = self.talking_points
        return d


@dataclass
class ReverseQ:
    category: str
    question: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PrepKit:
    star_qa: list[QAItem] = field(default_factory=list)
    reverse_qs: list[ReverseQ] = field(default_factory=list)
    created_at: str = ""

    def is_empty(self) -> bool:
        return not (self.star_qa or self.reverse_qs)

    def to_dict_for_cache(self) -> dict[str, Any]:
        return {
            "star_qa": [q.to_dict() for q in self.star_qa],
            "reverse_qs": [r.to_dict() for r in self.reverse_qs],
        }


def _resolve_lang(lang: Optional[str]) -> str:
    return lang if lang is not None else get_output_language()


def _row_to_kit(row: dict) -> PrepKit:
    k = row.get("kit") or {}
    return PrepKit(
        star_qa=_parse_qa(k.get("star_qa")),
        reverse_qs=_parse_reverse(k.get("reverse_qs")),
        created_at=row.get("created_at", ""),
    )


def _defense_seeds(session: dict, resume_id: int, lang: str, path) -> list[dict]:
    """REAL gaps + their defense hooks for a job-bound session (REQ-018 reuse).
    Empty when the session is unbound or the job was never gap-enhanced — the
    prompt then infers likely objections from the résumé × JD instead."""
    job_id = session.get("job_id")
    if not job_id:
        return []
    cached = db.get_cached_gap_enhancement(
        job_id, resume_id, lang, gap_enhance.PROMPT_VERSION, path=path)
    if not cached:
        return []
    return [
        {"gap": c.get("gap", ""), "defense_hook": c.get("suggestion", "")}
        for c in cached
        if c.get("kind") == "real" and c.get("gap")
    ]


def get_or_generate_kit(
    session: dict,
    resume_id: int,
    resume_text: str,
    client: GeminiClient,
    *,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> Optional[PrepKit]:
    """Cache-aware entry point. `session` is a prep_sessions row dict (needs id,
    company, role_title, jd_text, job_id). Returns the kit, generating + caching
    it on a miss. None on failure or an empty kit — the caller renders nothing."""
    session_id = session.get("id")
    if not session_id or not resume_text.strip():
        return None
    lang = _resolve_lang(lang)

    if use_cache:
        cached = db.get_prep_kit(session_id, lang, PROMPT_VERSION, path=path)
        if cached is not None:
            return _row_to_kit(cached)

    if client.all_models_exhausted():
        return None

    persona = ai_summary.persona_line(resume_id)
    seeds = _defense_seeds(session, resume_id, lang, path)
    kit = _generate(resume_text, session, seeds, client, lang=lang, persona=persona)
    if kit is None or kit.is_empty():
        return None

    model_used = client.last_model_used or client.model_name or ""
    db.save_prep_kit(session_id, lang, PROMPT_VERSION, kit.to_dict_for_cache(),
                     model_used, path=path)
    stored = db.get_prep_kit(session_id, lang, PROMPT_VERSION, path=path)
    return _row_to_kit(stored) if stored else kit


def _generate(
    resume_text: str, session: dict, seeds: list[dict], client: GeminiClient,
    *, lang: str, persona: str,
) -> Optional[PrepKit]:
    prompt = _build_prompt(resume_text.strip()[:MAX_RESUME_CHARS], session, seeds,
                           persona=persona, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    return PrepKit(star_qa=_parse_qa(raw.get("star_qa")),
                   reverse_qs=_parse_reverse(raw.get("reverse_qs")))


def _build_prompt(resume: str, session: dict, seeds: list[dict], *, persona: str, lang: str) -> str:
    title = session.get("role_title") or "(unknown role)"
    company = session.get("company") or "(unknown company)"
    jd = (session.get("jd_text") or "").strip()[:MAX_JD_CHARS]
    jd_block = f"JOB DESCRIPTION:\n---\n{jd}\n---" if jd else "JOB DESCRIPTION: (not provided — use the role title and résumé)"
    if seeds:
        seed_lines = "\n".join(
            f'- Gap: "{s["gap"]}" — honest defense hook already prepared: {s["defense_hook"]}'
            for s in seeds if s["gap"]
        )
        seed_block = (
            "KNOWN REAL GAPS (turn EACH into one defensive_gap question — the likely "
            "interview objection — and answer with the honest defense below, leading "
            "with the closest transferable strength; never deny the gap, never fake "
            "having it):\n" + seed_lines
        )
    else:
        seed_block = ("KNOWN REAL GAPS: none supplied. You MAY add at most one "
                      "defensive_gap question if the résumé clearly lacks something "
                      "the role needs — framed honestly, never fabricating a skill.")

    return f"""You are preparing {persona} for a job interview. Produce an honest interview-prep kit from their résumé and this specific role. This is preparation and rehearsal — NEVER fabricate experience, and never coach them to misrepresent themselves.

{language_instruction(lang)}

ROLE: {title} at {company}
{jd_block}

RÉSUMÉ:
---
{resume}
---

{seed_block}

Produce TWO things.

1) "star_qa": up to {MAX_QA} likely interview questions, each with kind ∈ [behavioral, situational, why_you, culture_fit, defensive_gap]:
   - behavioral / situational → answer as a STAR grounded ONLY in a REAL experience from the résumé above. Object shape: "star": {{"situation","task","action","result"}}. If NO real résumé experience genuinely supports a question, DROP that question — do not invent a scenario.
   - why_you / culture_fit → answer as "talking_points": a list of 2–4 honest, specific points grounded in the résumé and the company/role.
   - defensive_gap → use the KNOWN REAL GAPS section. "talking_points" with the honest defense (transferable strength first, then the gap stated plainly, no apology, no overclaim).

2) "reverse_qs": up to {MAX_REVERSE} smart questions the CANDIDATE should ask the employer, grouped by "category" (e.g. "Culture & Team", "Role Success (90-Day Goals)", "Tech & Data"). Each: {{"category","question"}}.

Return JSON with this exact schema — no prose before or after:
{{
  "star_qa": [
    {{ "kind": "behavioral", "question": "...", "star": {{ "situation": "...", "task": "...", "action": "...", "result": "..." }} }},
    {{ "kind": "why_you", "question": "...", "talking_points": ["...", "..."] }}
  ],
  "reverse_qs": [
    {{ "category": "Culture & Team", "question": "..." }}
  ]
}}"""


def _parse_qa(items: Any) -> list[QAItem]:
    """Keep only well-formed items with a grounded answer. An item with neither
    a usable STAR nor talking points is DROPPED (grounded-or-none) — we never
    render a question we couldn't honestly answer."""
    out: list[QAItem] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        kind = str(it.get("kind", "")).strip()
        question = str(it.get("question", "")).strip()
        if kind not in VALID_KINDS or not question:
            continue
        star = it.get("star")
        star_clean = None
        if isinstance(star, dict):
            s = {k: str(star.get(k, "")).strip() for k in ("situation", "task", "action", "result")}
            if any(s.values()):
                star_clean = s
        points = [str(p).strip() for p in it.get("talking_points", []) if str(p).strip()] \
            if isinstance(it.get("talking_points"), list) else []
        if not star_clean and not points:
            continue  # grounded-or-none: no answer → drop
        out.append(QAItem(kind=kind, question=question, star=star_clean, talking_points=points))
        if len(out) >= MAX_QA:
            break
    return out


def _parse_reverse(items: Any) -> list[ReverseQ]:
    out: list[ReverseQ] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        q = str(it.get("question", "")).strip()
        if not q:
            continue
        cat = str(it.get("category", "")).strip() or "General"
        out.append(ReverseQ(category=cat, question=q))
        if len(out) >= MAX_REVERSE:
            break
    return out
