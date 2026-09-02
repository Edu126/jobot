"""Shared cleanup for LLM-generated, user-facing text.

Gemini (like most chat models) is trained on markdown and habitually
backslash-escapes ASCII punctuation that markdown treats as special — most
often a leading hyphen (`\\-`) so it won't start a list, but also `\\.`,
`\\(`, `\\#`, etc. Those escapes are meaningless in our plain-text surfaces
(résumé bullets, cover letters, score reasoning, matched/gap chips), and the
backslash survives `json.loads` (the model emits `"\\\\-"` → Python `"\\-"`),
so it renders literally as `\\-` in the UI.

This is the one place that strips those stray escapes. Apply it at every
boundary where LLM output becomes text we show the user — the contract-layer
fix (clean at parse time) instead of escaping in templates or asking the user
to tolerate it.
"""
from __future__ import annotations

import re

# A backslash immediately before a punctuation char that markdown treats as
# special. We do NOT touch `\n` / `\t` etc. — by the time we have a Python
# string those are already real control characters, not a backslash + letter.
_MD_ESCAPE_RE = re.compile(r"\\([-_*#`~>.!+()\[\]{}])")


def strip_md_escapes(text: str) -> str:
    """Remove markdown-style backslash escapes the model added to plain text.

    `"\\- five years"` → `"- five years"`; `"B\\.Sc\\."` → `"B.Sc."`.
    Idempotent and safe on text with no escapes (returns it unchanged).
    Non-str input is coerced via str() so callers can pass it defensively.
    """
    if not isinstance(text, str):
        text = str(text)
    if "\\" not in text:          # fast path — the vast majority of strings
        return text
    return _MD_ESCAPE_RE.sub(r"\1", text)
