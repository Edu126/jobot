"""Shared building blocks for the Prep AI pipeline (ADR-048, REQ-041).

The pack (`04-ai-pipeline-and-prompts.md`) prepends the SAME rule block to every
prompt and speaks the same band vocabulary everywhere. Keeping both here means a
change to the honesty stance is one edit, not nine. Every P-call module imports
`RULE_BLOCK`, `BANDS`, and the small formatting helpers from here.
"""
from __future__ import annotations

from typing import Any

# The three-band vocabulary — the ONLY grades the pipeline ever emits. No
# 9.4/10, no fake percentages (ADR-048 / design brief §4). Delivery metrics
# (seconds, WPM, filler count) are real numbers computed in code, never here.
BANDS = ("strong", "solid", "needs_work")
DEFAULT_BAND = "needs_work"

# Prepended to every prompt (pack "Shared rule block"). The never-invent rule is
# the same grounded-or-honest stance as GOV-005 / ADR-005 elsewhere in Jobot.
RULE_BLOCK = """Rules:
- Use only the information given below. Do not invent facts, names, numbers, or company details.
- If something is unknown, use null.
- Write in plain, simple language, in the output language these instructions ask for. Short sentences.
- Return only valid JSON that matches the schema."""

# Input clamps — the same defensive truncation kit.py uses so a huge JD or
# résumé can't blow the token budget.
MAX_RESUME_CHARS = 12000
MAX_JD_CHARS = 4000
MAX_RESEARCH_CHARS = 3000
MAX_NOTES_CHARS = 1200


def band_or_default(value: Any) -> str:
    """Coerce a model-returned grade to one of BANDS, defaulting to needs_work.
    An unknown/blank band is treated as the weakest — we never round UP an
    ungraded item into looking better than the evidence supports."""
    v = str(value or "").strip().lower()
    return v if v in BANDS else DEFAULT_BAND


def clip(text: str, limit: int) -> str:
    return (text or "").strip()[:limit]


def format_research(research: list[dict] | None, limit: int = MAX_RESEARCH_CHARS) -> str:
    """Render Tavily company-research hits as a compact, source-tagged block for
    a prompt. Each hit keeps its URL so the model can cite it (D3: research shows
    its source link). Empty/malformed research → a plain 'none' marker so the
    prompt still runs from the JD alone (the research-failed path)."""
    if not research:
        return "(no company research available — build from the job description alone)"
    lines: list[str] = []
    used = 0
    for hit in research:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title", "")).strip()
        url = str(hit.get("url", "")).strip()
        content = str(hit.get("content", "")).strip()
        block = f"- {title} ({url})\n  {content}"
        if used + len(block) > limit:
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines) if lines else \
        "(no company research available — build from the job description alone)"


def format_stories(stories: list[dict] | None) -> str:
    """Render the account-level Story Bank (P5/P6 output) as the input block P3
    maps against — id + title + STAR + metric + tags, compact. The `id` is the
    join key the mapping points back to (a story_id the bank didn't define is
    nulled downstream). Empty bank → a plain marker so P3 can return an
    all-null mapping (every competency shows a 'no story yet' gap)."""
    if not stories:
        return "(the Story Bank is empty — return story_id null for every competency)"
    out: list[str] = []
    for s in stories:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id", "")).strip() or "s?"
        title = str(s.get("title", "")).strip()
        star = " | ".join(
            f"{k[0].upper()}: {str(s.get(k, '')).strip()}"
            for k in ("situation", "task", "action", "result")
            if str(s.get(k, "")).strip()
        )
        metric = str(s.get("metric") or "").strip()
        tags = ", ".join(str(t).strip() for t in (s.get("tags") or []) if str(t).strip())
        parts = [f"- {sid}: {title}"]
        if star:
            parts.append(f"    {star}")
        if metric:
            parts.append(f"    metric: {metric}")
        if tags:
            parts.append(f"    tags: {tags}")
        out.append("\n".join(parts))
    return "\n".join(out) if out else \
        "(the Story Bank is empty — return story_id null for every competency)"


def format_competencies(competencies: list[dict] | None) -> str:
    """Render the brief's competencies (P1 output) as the input block P2/P3/P4
    consume — id + name + what-good-looks-like, one per line. The `id` is the
    join key (ADR-048) so downstream questions trace back to the brief."""
    if not competencies:
        return "(no competencies available)"
    out = []
    for c in competencies:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", "")).strip() or "c?"
        name = str(c.get("name", "")).strip()
        good = str(c.get("what_good_looks_like", "")).strip()
        out.append(f"- {cid}: {name} — a strong answer shows: {good}")
    return "\n".join(out) if out else "(no competencies available)"
