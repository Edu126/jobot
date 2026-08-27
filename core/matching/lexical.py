"""Dependency-free text normalization + stemming, shared by every matcher
that needs "does this term show up in this text" without pulling in a
real NLP stack.

Deliberately has ZERO third-party imports (stdlib `re` only) so importing
it never drags in `tfidf_match.py`'s scikit-learn/numpy dependency —
`core.matching.semantic_score` is on the live scoring hot path and needs
tolerant term matching (the REQ-005 grounding guard-rail) without paying
for a vectorizer it doesn't use. `tfidf_match.py` imports the same
functions instead of defining its own copy.
"""
from __future__ import annotations

import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9+#\s]")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, drop punctuation (keep + and # so
    tokens like 'c++'/'c#' survive)."""
    text = text.lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def stems(word: str) -> set[str]:
    """Return the word plus every plausible stem variant.

    Returning a SET (not a single stem) lets us match both
    'developed→develop' (strip -ed) and 'coordinated→coordinate'
    (silent-e past tense, strip just -d) without picking a winner.

    Without a real lemmatizer we can't tell which is right per word, so
    we keep both and rely on set intersection in the caller."""
    w = word.lower().rstrip("'s")
    if len(w) <= 3:
        return {w}
    out: set[str] = {w}
    if w.endswith("ies"):
        out.add(w[:-3] + "y")
    if w.endswith("ied"):
        out.add(w[:-3] + "y")
    if w.endswith("ing") and len(w) > 4:
        out.add(w[:-3])           # coordinating → coordinat
        out.add(w[:-3] + "e")     # coordinating → coordinate
    if w.endswith("ed") and len(w) > 3:
        out.add(w[:-2])           # developed → develop
        out.add(w[:-1])           # coordinated → coordinate (silent-e)
    if w.endswith("es") and len(w) > 3:
        out.add(w[:-2])
        out.add(w[:-1])
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        out.add(w[:-1])
    return out
