"""Cheap deterministic per-job affinity — used to prioritise which jobs
get expensive LLM scoring first, and to order the initial results-page
render before any LLM score exists.

ADR-010, Slice 3. Explicitly NOT a replacement for the LLM score:
  - No vocabulary building (unlike core/matching/tfidf_match.py which
    fits a fresh TF-IDF vectorizer per (resume, JD) pair — those scores
    aren't comparable across jobs).
  - Just set intersection over already-normalised tokens. Fast at
    n≤60 jobs, no state, no persistence.
  - Location is ignored on purpose: the search params already narrow
    to a location; adding a location bonus would double-count.

Weights: title tokens count 3× as much as description tokens. The title
is the strongest signal of what the candidate does; JD prose has too
much boilerplate (benefits, culture, EEO) to weigh equally.

Values are raw comparable numbers — not normalised to 0..1 — because
we only use them for sort order, never for display. Higher = better fit
against the resume vocabulary. Ties are stable via the caller's
secondary sort key (date_posted).
"""
from __future__ import annotations

import re
from functools import lru_cache


# Words that carry no signal in either direction. Deliberately short —
# we want the intersection to be dominated by domain vocabulary. Larger
# stopword lists (nltk, spacy) would strip out useful discriminators.
_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "you", "your", "our", "will", "are",
    "have", "has", "this", "that", "from", "not", "but", "any", "all",
    "who", "was", "were", "been", "being", "which", "what", "when",
    "where", "into", "over", "than", "such", "also", "may", "can",
    "must", "should", "would", "could", "does", "did", "one", "two",
    "three", "years", "year", "team", "teams", "work", "role", "roles",
    "job", "jobs", "position", "positions", "company", "companies",
    "candidate", "candidates", "responsibilities", "duties",
    "qualifications", "requirements", "applicant", "applicants",
    "including", "based", "across", "various", "strong", "excellent",
    "responsible", "ability", "experience", "join", "looking", "seeking",
    "hire", "hiring", "preferred", "required", "essential",
})

# Match tokens like "revit", "python3", "c++", "civil-3d". Keep short
# tokens like "bim" (3 chars) — they're domain-specific acronyms.
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#]{2,}")

# How much of the JD description to consider. Titles are separately +
# heavily weighted, so the description tail matters less. First 2000
# chars typically includes the key-requirements section on Indeed /
# LinkedIn / Google Jobs.
_DESC_HEAD_CHARS = 2000


@lru_cache(maxsize=8)
def resume_hints(resume_text: str) -> frozenset[str]:
    """Extract salient tokens from a resume once so per-job affinity is
    a single set intersection. Called from every /jobs/results render,
    every /growth poll (every 2s during discovery), and every
    /score-batch call — LRU-cached because the same resume text
    produces the same hints. Cache size 8 covers typical concurrent
    resumes (single-user POC) with room for a resume swap or two."""
    if not resume_text:
        return frozenset()
    tokens = _TOKEN_RE.findall(resume_text.lower())
    return frozenset(t for t in tokens if t not in _STOPWORDS)


def compute_affinity(job: dict, hints: frozenset[str]) -> int:
    """Return a raw affinity count for `job` against pre-extracted resume
    `hints`. Higher = better vocabulary overlap. Not normalised — used
    for sort order only, never shown to the user.

    Zero hints (no resume, or resume didn't tokenise) → returns 0 for
    every job, which is fine: the caller's secondary sort key
    (date_posted) still produces a stable order."""
    if not hints:
        return 0

    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "")[:_DESC_HEAD_CHARS].lower()

    title_toks = set(_TOKEN_RE.findall(title)) - _STOPWORDS
    desc_toks = set(_TOKEN_RE.findall(desc)) - _STOPWORDS

    title_hits = len(title_toks & hints)
    desc_hits = len(desc_toks & hints)
    return title_hits * 3 + desc_hits
