"""LLM re-parse pass for resumes whose deterministic parse looks off.

The regex/heuristic parser in parser.py handles clean DOCX cleanly, but
PDF exports with unusual layout (columns, tables-as-layout, decorative
headers) often produce reflowed raw_text where the deterministic section
splitter can't tell headers from body. This module hands the raw_text to
Gemini and asks it to re-derive the `sections` dict — one call, no
schema surprises: same keys the parser produces, same list-of-strings
shape per section, so downstream (writer.py, tailor, anomalies.analyze)
keeps working unchanged.

Contact / raw_text / source_format / docx_meta are NOT touched — the LLM
only re-derives sections. Stats are recomputed from the new section
content so bullet_count and word_count match what's actually there.
"""
from __future__ import annotations

import re
from typing import Any

from core.llm.gemini import GeminiClient


# Must stay in sync with core.resume.anomalies._REPORT_SECTIONS keys, which
# is itself aligned with the JSON Resume standard. The template + tailor
# both index into these keys, so drift here breaks the rest of the app.
_ALLOWED_SECTIONS = (
    "summary", "experience", "education", "skills", "certifications",
    "projects", "publications", "volunteer", "awards", "languages",
    "interests", "references",
)


def regenerate_sections(parsed: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Return a NEW parsed dict with sections re-derived by Gemini.

    Raises `GeminiError` from the underlying client — the route handler
    catches and shows the error inline rather than swallowing here (a
    silent no-op after the user hits "Regenerate cleanly" is worse than
    an error message).
    """
    raw_text = (parsed.get("raw_text") or "").strip()
    if not raw_text:
        # Nothing to regenerate from — return parsed unchanged. Caller
        # decides how to surface this (currently: contact + raw_text are
        # the only things a re-upload would help with).
        return parsed

    prompt = f"""You are re-parsing a resume that a deterministic regex parser
choked on (PDF reflow, unusual layout, etc.). Your job: read the raw
extracted text and split it into the standard resume sections. Do NOT
rewrite, summarize, translate, or invent content — only reorganize what's
there into the correct sections.

Return JSON with this exact shape (all keys optional, omit if the resume
truly has no content for that section):
{{
  "summary":        ["one paragraph of prose"],
  "experience":     ["Job Title | Company | Dates", "achievement bullet", "achievement bullet", "Next Job Title | ...", ...],
  "education":      ["Degree — School — Year", ...],
  "skills":         ["Category: item, item, item", ...] OR ["Skill1", "Skill2", ...],
  "certifications": ["Cert name — issuer — year", ...],
  "projects":       ["Project Title — one-line context", "bullet", ...],
  "publications":   ["Title — venue — year", ...],
  "volunteer":      ["Role — org — dates", "bullet", ...],
  "awards":         ["Award — issuer — year", ...],
  "languages":      ["English (native)", "French (B2)", ...],
  "interests":      ["Interest 1", "Interest 2", ...],
  "references":     ["Name — role — contact", ...]
}}

Rules:
- For experience and projects, put the header line (title/company/dates)
  as its own list item, then each achievement bullet as its own item, in
  the order they appear. Do not merge a title with its bullets.
- Keep the candidate's original wording. Fix only obvious PDF-extraction
  artifacts (broken hyphenation, mid-word line splits like "coordina\ntion").
- If a section header exists in the resume but has no content beneath,
  omit that key entirely — don't emit an empty list.
- If you cannot identify any section confidently (raw text is garbage),
  return {{}} — the caller keeps the old parse.

RAW RESUME TEXT:
---
{raw_text[:12000]}
---
"""

    client = GeminiClient(api_key=api_key)
    raw = client.generate_json(prompt)

    new_sections = _sanitize_sections(raw)
    if not new_sections:
        # Model failed to produce anything usable — keep old parse
        # rather than nuking the sections dict to empty.
        return parsed

    updated = dict(parsed)
    updated["sections"] = new_sections
    updated["stats"] = _recompute_stats(parsed.get("raw_text", ""), new_sections)
    return updated


def _sanitize_sections(raw: Any) -> dict[str, list[str]]:
    """Coerce whatever the model returned into `{allowed_key: [str, ...]}`.
    Silently drops unknown keys, non-list values, and empty items — the
    downstream shape contract is stricter than the model's honor system."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key in _ALLOWED_SECTIONS:
        val = raw.get(key)
        if not isinstance(val, list):
            continue
        cleaned = [str(item).strip() for item in val if str(item).strip()]
        if cleaned:
            out[key] = cleaned
    return out


def _recompute_stats(raw_text: str, sections: dict[str, list[str]]) -> dict[str, int]:
    """Stats derived from the NEW sections (so bullet_count reflects the
    re-parse, not the old broken one). word_count stays tied to raw_text
    since regeneration doesn't add or remove words."""
    word_count = len(re.findall(r"\b\w+\b", raw_text))
    page_estimate = max(1, round(word_count / 500))
    bullet_count = sum(len(v) for v in sections.values())
    return {
        "word_count": word_count,
        "page_estimate": page_estimate,
        "bullet_count": bullet_count,
    }
