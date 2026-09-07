"""Orchestrate a single rewrite: parsed resume + JD + level → tailored
parsed resume.

The output has the same shape as the parser's output, so writer.render_docx
can consume it directly.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from .gemini import GeminiClient
from .prompts import Level, build_rewrite_prompt
from .sanitize import strip_md_escapes


# LLMs sometimes emit placeholders in the cover letter or summary even when
# told not to. Belt-and-suspenders: post-process every string to substitute
# the real name. Case-insensitive, matches with or without brackets.
_PLACEHOLDER_PATTERNS = [
    re.compile(r"\[?\s*your\s+name\s*\]?", re.IGNORECASE),
    re.compile(r"\[\s*name\s*\]", re.IGNORECASE),
    re.compile(r"\[\s*candidate(?:\s+name)?\s*\]", re.IGNORECASE),
    re.compile(r"\[\s*applicant(?:\s+name)?\s*\]", re.IGNORECASE),
]


def _substitute_name(text: str, name: str) -> str:
    """Replace all known placeholder variants with the real name."""
    if not name or not text:
        return text
    out = text
    for pat in _PLACEHOLDER_PATTERNS:
        out = pat.sub(name, out)
    return out


def _section_pct(original: list[str], tailored: list[str]) -> int:
    """Rough measure of how much a section's content changed.
    0 = identical, 100 = entirely different. Uses SequenceMatcher on
    lowercased joined text (case-insensitive so 'Led' vs 'led' isn't scored
    as a change)."""
    orig_text = "\n".join(str(s).strip() for s in (original or [])).lower()
    new_text = "\n".join(str(s).strip() for s in (tailored or [])).lower()
    if not orig_text and not new_text:
        return 0
    if not orig_text:
        return 100
    ratio = difflib.SequenceMatcher(None, orig_text, new_text).ratio()
    return int(round((1 - ratio) * 100))


def _compute_change_summary(original: dict, tailored: dict) -> dict:
    """Return a structured change report the UI can render.

    {
      "overall_pct": int,
      "per_section": [{"section": "summary", "pct": 45}, ...],
      "one_liner": "~32% changed overall · Summary 45% · Experience 28%"
    }

    Overall is computed on the concatenated text of all sections (not an
    average of per-section pcts — that would double-count identical sections
    with different lengths). Per-section only reports sections that appear in
    either dict AND that changed at all.
    """
    keys = sorted(set(original.keys()) | set(tailored.keys()))
    per_section: list[dict] = []
    orig_join_parts: list[str] = []
    new_join_parts: list[str] = []
    for k in keys:
        if k == "header":
            continue
        orig = original.get(k, [])
        new = tailored.get(k, [])
        pct = _section_pct(orig, new)
        if pct > 0:
            per_section.append({"section": k, "pct": pct})
        orig_join_parts.append("\n".join(str(x).strip() for x in orig).lower())
        new_join_parts.append("\n".join(str(x).strip() for x in new).lower())

    all_orig = "\n".join(orig_join_parts)
    all_new = "\n".join(new_join_parts)
    if not all_orig and not all_new:
        overall_pct = 0
    elif not all_orig:
        overall_pct = 100
    else:
        overall_pct = int(round((1 - difflib.SequenceMatcher(None, all_orig, all_new).ratio()) * 100))

    if not per_section:
        one_liner = f"~{overall_pct}% changed overall — mostly reorder / light edits."
    else:
        breakdown = " · ".join(f"{p['section'].title()} {p['pct']}%" for p in per_section[:5])
        one_liner = f"~{overall_pct}% changed overall · {breakdown}"

    return {
        "overall_pct": overall_pct,
        "per_section": per_section,
        "one_liner": one_liner,
    }


def rewrite_resume(
    parsed: dict[str, Any],
    job_description: str,
    level: Level,
    client: GeminiClient,
    company_context: str = "",
    resume_id: int | None = None,
    persona: str | None = None,
) -> dict[str, Any]:
    """Generate a tailored version of the parsed resume.

    Returns a new dict with the same schema as `parsed`, plus:
        - "tailoring_notes": str   — LLM's explanation
        - "tailoring_warnings": list[str]
        - "tailoring_level": Level

    The original `parsed` is not mutated.

    `resume_id`, when the caller has one, resolves the domain-neutral
    persona line (ADR-007 + ADR-013) via `core.resume.ai_summary` — the
    same profile scoring uses, so the candidate reads as the same person
    across both. Pass `persona` directly instead when the caller already
    resolved it (e.g. the tailor route also calls `score_single_no_cache`
    for the same resume_id in the same request — resolve once, pass to
    both, rather than triggering `ai_summary.persona_line` twice).
    """
    if persona is None:
        from core.resume import ai_summary
        persona = ai_summary.persona_line(resume_id)
    sections = parsed.get("sections", {}) or {}
    contact = parsed.get("contact", {}) or {}

    # We only send a contact summary for context — never let the model
    # rewrite contact info.
    contact_summary = {
        "name": contact.get("name", ""),
        "location": contact.get("location", ""),
    }

    # Drop the 'header' bucket — it's noise from the parser (lines that
    # appeared before the first section header). Keep the rest.
    editable_sections = {k: v for k, v in sections.items() if k != "header" and v}

    # Fallback: if section detection failed entirely (common with PDFs
    # that use non-standard headings), package raw_text as a single
    # 'experience' block so the LLM has something to work with. This
    # avoids the failure mode where the LLM says "the original resume
    # was empty".
    if not editable_sections:
        raw = (parsed.get("raw_text") or "").strip()
        if raw:
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            editable_sections = {"experience": lines}

    # Output language comes from user settings — a Colombian user with
    # a Spanish resume applying to a multinational Bogotá office may
    # explicitly want English tailored output (or vice versa). Setting
    # is toggled in Profile; we read it at each rewrite call.
    from core.settings import get_output_language

    prompt = build_rewrite_prompt(
        parsed_sections=editable_sections,
        contact_summary=contact_summary,
        job_description=job_description,
        level=level,
        company_context=company_context,
        output_language=get_output_language(),
        persona=persona,
    )

    # Structural-fidelity guard. On real resumes, gemini-flash-lite emits
    # valid, complete JSON that occasionally COLLAPSES a whole section — a
    # 22-item experience list comes back with 5 (~20% of aggressive runs,
    # verified on a real user's resume against the Fly deploy; NOT a token
    # cutoff — the JSON parses and the cover letter is fully present). A
    # rewrite that silently drops most of someone's experience is worse than
    # no tailoring, so we (1) retry once — the collapse is per-call random,
    # not deterministic — and (2) if a section is STILL collapsed, restore it
    # verbatim from the original. No role, employer, or degree is ever lost.
    # This is the ADR-005 pattern (quality in the contract layer via silent
    # retry + validation, not a user-facing "Regenerate" button).
    response = client.generate_json(prompt)
    new_sections = _coerce_sections(response.get("sections") or {})
    if _collapsed_sections(editable_sections, new_sections):
        response = client.generate_json(prompt)
        new_sections = _coerce_sections(response.get("sections") or {})
    for key in _collapsed_sections(editable_sections, new_sections):
        new_sections[key] = list(editable_sections[key])

    # Re-attach the original header bucket so nothing is silently lost.
    if sections.get("header"):
        new_sections.setdefault("header", sections["header"])

    cover_letter = response.get("cover_letter")
    if isinstance(cover_letter, list):
        # Some LLM outputs split paragraphs into a list — re-join.
        cover_letter = "\n\n".join(str(p).strip() for p in cover_letter if p)
    cover_letter = strip_md_escapes((cover_letter or "").strip())

    # Post-process placeholders. Belt-and-suspenders next to the prompt rule.
    candidate_name = contact.get("name", "").strip()
    if candidate_name:
        cover_letter = _substitute_name(cover_letter, candidate_name)
        new_sections = {
            k: [_substitute_name(item, candidate_name) for item in v]
            for k, v in new_sections.items()
        }

    # Compute how much actually changed, section by section. Gives the user a
    # concrete signal for how much fact-checking they should do post-generation.
    change_summary = _compute_change_summary(editable_sections, new_sections)

    return {
        **parsed,
        "sections": new_sections,
        "cover_letter": cover_letter,
        "tailoring_notes": str(response.get("notes", "")).strip(),
        "tailoring_warnings": list(response.get("warnings") or []),
        "tailoring_change": change_summary,
        "tailoring_level": level,
    }


def tailored_to_text(tailored: dict[str, Any]) -> str:
    """Flatten a tailored parsed-resume dict back into plain text suitable
    for scoring. Preserves section order + names so the LLM sees the same
    shape it does when scoring the original."""
    from core.resume.writer import SECTION_ORDER, SECTION_TITLES

    parts: list[str] = []
    contact = tailored.get("contact", {}) or {}
    name = (contact.get("name") or "").strip()
    if name:
        parts.append(name)
    contact_line = " | ".join(
        b for b in [
            contact.get("location"),
            contact.get("email"),
            contact.get("phone"),
            contact.get("linkedin"),
        ] if b
    )
    if contact_line:
        parts.append(contact_line)

    sections = tailored.get("sections", {}) or {}
    for key in SECTION_ORDER:
        items = sections.get(key)
        if not items:
            continue
        parts.append("")
        parts.append(SECTION_TITLES.get(key, key.upper()))
        for item in items:
            parts.append(str(item).strip())
    return "\n".join(parts).strip()


# Sections where a big item-count drop means the model dropped whole entries
# (a role, an employer, a degree) rather than legitimately trimming bullets.
# Skills/summary can shrink for real; experience/education shrinking that hard
# is data loss.
_FIDELITY_SECTIONS = ("experience", "education")


def _collapsed_sections(original: dict, tailored: dict) -> list[str]:
    """Return the fidelity-critical sections whose tailored item count fell so
    far below the original that entries were almost certainly dropped, not
    trimmed. Threshold: under 60% of the original items, and the original had
    enough items (>=4) for the ratio to mean something (a 3-bullet role
    legitimately becoming 2 isn't a collapse)."""
    collapsed = []
    for key in _FIDELITY_SECTIONS:
        orig_n = len(original.get(key) or [])
        new_n = len(tailored.get(key) or [])
        if orig_n >= 4 and new_n < 0.6 * orig_n:
            collapsed.append(key)
    return collapsed


def _coerce_sections(raw: Any) -> dict[str, list[str]]:
    """Defensive cleanup of the LLM's sections dict.

    Trusts the structure but normalizes types — Gemini occasionally returns
    a single string instead of a list, or nested dicts for experience.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        out[key] = _coerce_section_value(value)
    return out


def _coerce_section_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [strip_md_escapes(value.strip())] if value.strip() else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    result.append(strip_md_escapes(item.strip()))
            elif isinstance(item, dict):
                # flatten "title: ... | bullets: [...]" shapes if the LLM
                # ignores the format instruction
                title = item.get("title") or item.get("role") or item.get("heading")
                if title:
                    result.append(strip_md_escapes(str(title).strip()))
                bullets = item.get("bullets") or item.get("achievements") or []
                if isinstance(bullets, list):
                    for b in bullets:
                        if isinstance(b, str) and b.strip():
                            result.append(strip_md_escapes(b.strip()))
            elif item is not None:
                result.append(strip_md_escapes(str(item)))
        return result
    if isinstance(value, dict):
        # treat as a single titled block
        return _coerce_section_value([value])
    return [str(value)]
