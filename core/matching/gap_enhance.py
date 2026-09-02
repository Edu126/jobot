"""Gap enhancement — turn a job's score-time `gaps` into honest next actions.

REQ-018 / ADR-021. Scoring (semantic_score.py) already produces, per job, a
short `gaps` list: requirements the résumé doesn't evidence. A gap list with
no next action is the blank-page moment the product exists to carry. This
module classifies each gap and proposes an on-paper move:

- WORDING gap: the candidate actually HAS the thing, but the JD's exact-title
  language isn't on the page. → suggest the honest rewording the AI ranker
  rewards ("be seen · be ranked · be real", never "beat the ATS").
- REAL gap: the candidate genuinely lacks it. → give a DEFENSE HOOK: an honest
  way to address it if a recruiter/interviewer raises it, leading with the
  closest transferable strength in the résumé (the enhance→prepare seam — a
  real gap IS the likely interview objection). NO invented skill, NO course
  pitch (the "close it for real" rev-share is Phase 3, governance-gated).

Honesty is the product (GOV-005 — enhance ≠ fabricate). The safe failure mode
is baked into the prompt: when unsure, classify as REAL and never suggest an
unearned rewording.

Mechanism (ADR-021): reuse the score-time `gaps` as input — no second gap
analysis. One light Gemini call, grounded in the résumé the user affirmed,
at temperature=0.0 (reproducible like scoring). Cached per (job, résumé-text,
lang) in the `gap_enhancements` table, generated lazily on detail open.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.llm.sanitize import strip_md_escapes
from core.resume import ai_summary
from core.settings import get_reasoning_language, language_instruction

# Bump when the prompt changes — logically invalidates cached rows (a version
# mismatch on read is a miss → regenerate), never deletes them (ADR-006 /
# ADR-021, same convention as semantic_score.PROMPT_VERSION).
PROMPT_VERSION = "2026-09-02-real-defense-hook"

MAX_RESUME_CHARS = 12000   # match semantic_score — see its note on tail sections
MAX_JD_CHARS = 2500
VALID_KINDS = ("wording", "real")


@dataclass
class GapEnhancement:
    gap: str                # the original gap phrase (echoed from input)
    kind: str               # "wording" | "real"
    suggestion: str         # the honest on-paper move (may be short for real gaps)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_lang(lang: str | None) -> str:
    return lang if lang is not None else get_reasoning_language()


def enhance_gaps_cached(
    resume_id: int,
    resume_text: str,
    job: dict,
    gaps: list[str],
    client: GeminiClient,
    *,
    lang: str | None = None,
    use_cache: bool = True,
) -> list[GapEnhancement]:
    """Cache-aware entry point. Returns the per-gap enhancement list for this
    job, generating (and caching) it lazily on a miss. Empty list when there
    are no gaps, the résumé is text-less, or the model/quota is unavailable —
    the caller renders nothing rather than blocking the detail pane."""
    if not gaps or not resume_text.strip():
        return []
    lang = _resolve_lang(lang)

    if use_cache:
        cached = db.get_cached_gap_enhancement(job["id"], resume_id, lang, PROMPT_VERSION)
        if cached is not None:
            return [_row_to_enhancement(r) for r in cached]

    if client.all_models_exhausted():
        return []

    persona = ai_summary.persona_line(resume_id)
    enhancements = _enhance(resume_text, job, gaps, client, lang=lang, persona=persona)
    if enhancements:
        model_used = client.last_model_used or client.model_name or ""
        db.save_gap_enhancement(
            job["id"], resume_id, lang, PROMPT_VERSION,
            [e.to_dict() for e in enhancements], model_used,
        )
    return enhancements


def _enhance(
    resume_text: str,
    job: dict,
    gaps: list[str],
    client: GeminiClient,
    *,
    lang: str,
    persona: str,
) -> list[GapEnhancement]:
    """One Gemini call classifying every gap. Returns [] on any failure so a
    flaky enhancement never breaks the detail pane."""
    resume_snippet = resume_text.strip()[:MAX_RESUME_CHARS]
    prompt = _build_prompt(resume_snippet, job, gaps, persona=persona, lang=lang)
    try:
        # temperature=0.0: same gap list must yield the same enhancement across
        # runs (ADR-021, mirroring scoring's determinism stance).
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return []
    return _parse_response(raw, gaps)


def _build_prompt(
    resume: str, job: dict, gaps: list[str], *, persona: str, lang: str
) -> str:
    """Prompt: classify each gap wording-vs-real, grounded ONLY in the résumé
    text, and propose an honest on-paper move. GOV-005 is enforced in the
    instructions, not with a thumb on the scale — when unsure, REAL."""
    jd = (job.get("description") or "").strip()[:MAX_JD_CHARS]
    title = job.get("title") or "(unknown title)"
    company = job.get("company") or "(unknown company)"
    gaps_block = "\n".join(f'- {g}' for g in gaps)

    return f"""You are helping {persona} close the gaps between their résumé and a specific job — HONESTLY, on paper. You will be given the résumé, the job, and a list of GAPS that a scoring pass flagged as requirements the résumé does not clearly evidence.

{language_instruction(lang)}

For EACH gap, decide which of two kinds it is, judging ONLY by what the résumé below actually contains:

- "wording": the candidate genuinely HAS this (the skill, tool, or experience appears in the résumé — possibly under a synonym, an abbreviation, another language, or a tail section), it just isn't phrased the way this job names it. The gap is a visibility problem, not a real deficit.
- "real": the résumé does NOT evidence this in any form. It is a genuine gap.

RULES (these are non-negotiable):
1. NEVER invent, assume, or suggest claiming something the résumé does not support. If you are not sure the candidate truly has it, classify it "real". When in doubt, "real".
2. For a "wording" gap: the suggestion is the concrete, honest rewording — name what the résumé already shows and how to phrase it using the job's own term, so a recruiter and an AI ranker can see it. It must map to real content in the résumé.
3. For a "real" gap: the suggestion is a DEFENSE HOOK — an honest way the candidate can address this gap if a recruiter or interviewer raises it. Lead with the closest transferable strength actually present in the résumé, then frame the gap plainly, without apologizing and without overclaiming. Do NOT recommend courses, certifications, or training (out of scope). Do NOT fabricate experience the résumé doesn't show. One or two sentences.
4. Echo each gap's text back EXACTLY as given so it can be matched.

RÉSUMÉ:
---
{resume}
---

JOB: {title} at {company}
JOB DESCRIPTION:
---
{jd}
---

GAPS TO ENHANCE:
{gaps_block}

Return JSON with this exact schema — no prose before or after:
{{
  "enhancements": [
    {{
      "gap": "<exact gap text from the list>",
      "kind": "wording" | "real",
      "suggestion": "<one honest, concrete sentence>"
    }}
  ]
}}

The enhancements array MUST contain exactly one entry per gap above, in the same order."""


def _parse_response(raw: dict, gaps: list[str]) -> list[GapEnhancement]:
    """Extract valid enhancements, one per input gap. Defensive against a
    missing/renamed gap, a bad kind, or a dropped entry: any gap the model
    didn't return (or mangled) falls back to an honest "real" with no
    suggestion — never fabricate a wording rewrite we can't verify."""
    items = raw.get("enhancements")
    by_gap: dict[str, dict] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                g = str(item.get("gap", "")).strip()
                if g:
                    by_gap.setdefault(g, item)

    out: list[GapEnhancement] = []
    for gap in gaps:
        item = by_gap.get(gap) or _fuzzy_match(gap, by_gap)
        kind = str((item or {}).get("kind", "")).strip().lower()
        if kind not in VALID_KINDS:
            kind = "real"   # GOV-005 safe default
        suggestion = strip_md_escapes(str((item or {}).get("suggestion", "")).strip())
        out.append(GapEnhancement(gap=gap, kind=kind, suggestion=suggestion))
    return out


def _fuzzy_match(gap: str, by_gap: dict[str, dict]) -> dict | None:
    """The model occasionally re-cases or trims a gap phrase. Fall back to a
    case-insensitive match before giving up on it."""
    low = gap.strip().lower()
    for k, v in by_gap.items():
        if k.strip().lower() == low:
            return v
    return None


def _row_to_enhancement(row: Any) -> GapEnhancement:
    """Cached JSON dict → GapEnhancement, defensive against hand-edited rows."""
    if not isinstance(row, dict):
        return GapEnhancement(gap="", kind="real", suggestion="")
    kind = str(row.get("kind", "")).strip().lower()
    return GapEnhancement(
        gap=str(row.get("gap", "")),
        kind=kind if kind in VALID_KINDS else "real",
        suggestion=str(row.get("suggestion", "")),
    )
