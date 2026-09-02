"""The gap map — all of a candidate's REAL gaps in one place (REQ-019 / ADR-022).

Where gap_enhance.py answers a gap inside one job's detail (JD-specific, lazy),
this collects gaps across ALL the résumé's scored jobs and ranks the REAL ones
by how many target roles they block — the candidate-level "distance between who
you are and the job you want" (product vision: gap monetized 3×).

Mechanism (ADR-022):
1. `db.gap_counts_for_resume` aggregates every gap across `job_scores` with a
   frequency count — pure SQL, no LLM.
2. Each DISTINCT gap is classified JD-FREE (résumé × gap → wording|real +
   suggestion) in ONE batched call, cached per-gap in `gap_classification`, so
   repeat renders are ~free and only newly-seen gaps cost a call.
3. The map shows REAL gaps ranked by count, each with its defense hook. Wording
   gaps stay per-job (ADR-021) — the reword is JD-specific.

Honesty is the product (GOV-005): when unsure a gap is classified REAL, and a
real gap's suggestion is an honest defense hook (lead with transferable
strength), never an invented skill or a course pitch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.llm.sanitize import strip_md_escapes
from core.matching import semantic_score as ss
from core.resume import ai_summary
from core.settings import get_reasoning_language, language_instruction

# Own prompt version (JD-free classification) — bump to invalidate the
# gap_classification cache without deleting it (ADR-006 convention).
PROMPT_VERSION = "2026-09-02-jdfree-defense"

MAX_RESUME_CHARS = 12000
MAX_GAPS_PER_CALL = 40   # distinct gaps; short phrases, one call comfortably fits
VALID_KINDS = ("wording", "real")


@dataclass
class GapMapEntry:
    gap: str
    count: int          # how many of the user's scored roles flag this gap
    kind: str           # "wording" | "real"
    suggestion: str     # defense hook (real) / reword (wording)


def _resolve_lang(lang: str | None) -> str:
    return lang if lang is not None else get_reasoning_language()


def build_gap_map(
    resume_id: int,
    resume_text: str,
    client: GeminiClient | None,
    *,
    lang: str | None = None,
) -> list[GapMapEntry]:
    """Return the candidate's REAL gaps, ranked by frequency across their scored
    jobs, each with a defense hook. Empty when nothing's scored or the résumé is
    text-less. `client` may be None (no API key) — then we render from cached
    classifications only and never classify new gaps. Gaps we can't classify
    (no client / quota out) still appear, honestly, as real with no suggestion —
    never dropped or faked."""
    if not resume_text.strip():
        return []
    lang = _resolve_lang(lang)

    counts = db.gap_counts_for_resume(
        resume_id, lang, ss.PROMPT_VERSION, ss.SCORING_VERSION,
    )
    if not counts:
        return []

    cached = db.get_gap_classifications(resume_id, list(counts), lang, PROMPT_VERSION)
    missing = [g for g in counts if g not in cached]

    if missing and client is not None and not client.all_models_exhausted():
        persona = ai_summary.persona_line(resume_id)
        fresh = _classify(resume_text, missing[:MAX_GAPS_PER_CALL], client, lang=lang, persona=persona)
        if fresh:
            db.save_gap_classifications(
                resume_id, lang, PROMPT_VERSION,
                [{"gap": g, "kind": k, "suggestion": s} for g, (k, s) in fresh.items()],
            )
            cached.update({g: {"kind": k, "suggestion": s} for g, (k, s) in fresh.items()})

    entries: list[GapMapEntry] = []
    for gap, count in counts.items():
        c = cached.get(gap)
        # Unclassified (quota out) → honest default: real, no suggestion.
        kind = (c or {}).get("kind", "real")
        if kind not in VALID_KINDS:
            kind = "real"
        if kind != "real":
            continue   # wording gaps live per-job (ADR-021), not in the map
        entries.append(GapMapEntry(
            gap=gap, count=count, kind="real",
            suggestion=(c or {}).get("suggestion", ""),
        ))

    # Rank: most-blocking first, then alphabetical for stable ties.
    entries.sort(key=lambda e: (-e.count, e.gap.lower()))
    return entries


def _classify(
    resume_text: str,
    gaps: list[str],
    client: GeminiClient,
    *,
    lang: str,
    persona: str,
) -> dict[str, tuple[str, str]]:
    """One JD-free call → {gap: (kind, suggestion)} for the given gaps. [] on any
    failure (caller degrades to honest 'real, no suggestion')."""
    resume_snippet = resume_text.strip()[:MAX_RESUME_CHARS]
    prompt = _build_prompt(resume_snippet, gaps, persona=persona, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return {}
    return _parse_response(raw, gaps)


def _build_prompt(resume: str, gaps: list[str], *, persona: str, lang: str) -> str:
    gaps_block = "\n".join(f"- {g}" for g in gaps)
    return f"""You are helping {persona} understand the gaps between their résumé and the jobs they are targeting — HONESTLY. Below is the résumé and a list of GAPS collected across many job postings (requirements a scoring pass did not clearly find in the résumé).

{language_instruction(lang)}

For EACH gap, decide, judging ONLY by what the résumé below contains:
- "wording": the candidate genuinely HAS this (it appears in the résumé — possibly under a synonym, abbreviation, another language, or a tail section), just not phrased the way jobs name it. suggestion = the concrete, honest rewording, mapping to real résumé content.
- "real": the résumé does NOT evidence this in any form. suggestion = a DEFENSE HOOK: an honest way the candidate can address it if a recruiter or interviewer raises it — lead with the closest transferable strength actually in the résumé, then frame the gap plainly, without apologizing or overclaiming.

RULES (non-negotiable):
1. NEVER invent, assume, or suggest claiming something the résumé does not support. If unsure the candidate truly has it, classify "real". When in doubt, "real".
2. Do NOT recommend courses, certifications, or training (out of scope).
3. Echo each gap's text back EXACTLY as given so it can be matched.

RÉSUMÉ:
---
{resume}
---

GAPS:
{gaps_block}

Return JSON with this exact schema — no prose before or after:
{{
  "classifications": [
    {{ "gap": "<exact gap text>", "kind": "wording" | "real", "suggestion": "<one honest, concrete sentence>" }}
  ]
}}

One entry per gap above."""


def _parse_response(raw: dict, gaps: list[str]) -> dict[str, tuple[str, str]]:
    """{gap: (kind, suggestion)} for gaps the model returned. Missing/garbled
    gaps are simply omitted (caller keeps them as honest 'real')."""
    items = raw.get("classifications")
    by_gap: dict[str, dict] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                g = str(item.get("gap", "")).strip()
                if g:
                    by_gap.setdefault(g, item)

    out: dict[str, tuple[str, str]] = {}
    for gap in gaps:
        item = by_gap.get(gap) or _fuzzy(gap, by_gap)
        if not item:
            continue
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in VALID_KINDS:
            kind = "real"
        suggestion = strip_md_escapes(str(item.get("suggestion", "")).strip())
        out[gap] = (kind, suggestion)
    return out


def _fuzzy(gap: str, by_gap: dict[str, dict]) -> dict | None:
    low = gap.strip().lower()
    for k, v in by_gap.items():
        if k.strip().lower() == low:
            return v
    return None
