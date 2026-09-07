"""Prep vacancy matching (REQ-023 / ADR-026).

Find the job the user is interviewing for inside what we already hold, so the
kit reuses the stored JD / score / gaps / defense hooks instead of starting
fresh. The search space is the TAILORED set first, then this résumé's scored
jobs (`db.prep_match_candidates`).

The ladder:
  1. exact URL  → **auto-bind** (high confidence, no confirm needed);
  2. else fuzzy (company + title, or the pasted JD text) → **propose the top
     few** for a one-tap confirm;
  3. nothing clears the bar → go **fresh** (unbound session).

Below the exact-URL bar nothing binds silently: a wrong bind would ground the
whole kit on the wrong JD (GOV-005). Fuzzy uses stdlib `difflib` — no new
dependency, in keeping with the $0 POC.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlsplit

from core import db

# A candidate must clear this combined similarity (0..1) to be offered at all.
PROPOSE_THRESHOLD = 0.55
# The mockup shows a 2–3 chip confirm; never flood the user with maybes.
MAX_CANDIDATES = 3

# Query params that identify a *tracker*, not the posting — dropped so the same
# job matches across share-link variants (LinkedIn `trk`, Indeed `vjs`, utm_*…).
_TRACKING_PARAMS = {
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "referer", "referrer",
    "source", "src", "trk", "trkcampaign", "vjs", "from", "spa", "seed",
}

# Legal-entity suffixes stripped for company comparison (and the ADR-027 cache
# key). Conservative on purpose — dropping generic words like "group"/"tech"
# would over-merge distinct employers.
_COMPANY_SUFFIX = re.compile(
    r"\b(inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|gmbh|s\.?a\.?s?|plc|nv|ag)\b\.?",
    re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_company(name: str) -> str:
    """Lowercase, strip punctuation + legal suffixes, collapse whitespace.
    Shared with the `company_outlook` cache key (ADR-027), so keep it stable."""
    s = (name or "").lower().strip()
    s = _NON_WORD.sub(" ", s)
    s = _COMPANY_SUFFIX.sub(" ", s)
    return _WS.sub(" ", s).strip()


def normalize_url(url: str) -> str:
    """Scheme-agnostic, host de-www'd + lowercased, tracking params dropped,
    remaining params sorted, trailing slash trimmed — so the same posting
    matches whether it arrived as an http/https/share/tracked link. Empty
    string for junk so two blanks never 'match'."""
    if not url or not url.strip():
        return ""
    u = url.strip()
    if "://" not in u:
        u = "http://" + u
    parts = urlsplit(u)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""
    path = parts.path.rstrip("/")
    kept = sorted(
        (k, v) for k, v in parse_qsl(parts.query)
        if not (k.lower().startswith("utm_") or k.lower() in _TRACKING_PARAMS)
    )
    query = "&".join(f"{k}={v}" for k, v in kept)
    return f"{host}{path}?{query}" if query else f"{host}{path}"


def _ratio(a: str, b: str) -> float:
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass
class Candidate:
    job_id: str
    title: str
    company: str
    score: float          # combined similarity, 0..1
    tailored: bool        # from a tailor run → ranks first on ties


@dataclass
class MatchResult:
    """Either an auto-bind (`bound_job_id` set) OR a confirm list (`candidates`).
    Both empty ⇒ nothing matched, caller goes fresh."""
    bound_job_id: str | None
    candidates: list[Candidate]


def _score_candidate(
    cand: dict, *, company: str, role_title: str, text: str
) -> float:
    """Combine whatever signals the caller has. Company+title when we know them;
    otherwise the pasted JD blob vs the stored description, boosted if the
    candidate's company/title appear verbatim in the paste."""
    parts: list[tuple[float, float]] = []  # (value, weight)
    if company:
        parts.append((_ratio(normalize_company(company), normalize_company(cand["company"])), 0.5))
    if role_title:
        parts.append((_ratio(role_title, cand["title"]), 0.5))

    if text and not (company or role_title):
        blob = text.lower()
        s = _ratio(text[:3000], (cand["description"] or "")[:3000])
        nc = normalize_company(cand["company"])
        if nc and nc in _NON_WORD.sub(" ", blob):
            s = max(s, 0.85)
        if cand["title"] and cand["title"].lower() in blob:
            s = max(s, 0.75)
        parts.append((s, 1.0))

    if not parts:
        return 0.0
    total_w = sum(w for _, w in parts)
    return sum(v * w for v, w in parts) / total_w


def find_matches(
    resume_hash: str,
    *,
    url: str = "",
    text: str = "",
    company: str = "",
    role_title: str = "",
    path=db.DB_PATH,
) -> MatchResult:
    """Run the ladder. `url` alone can auto-bind; `company`/`role_title`/`text`
    drive the fuzzy confirm list."""
    cands = db.prep_match_candidates(resume_hash, path=path)
    if not cands:
        return MatchResult(bound_job_id=None, candidates=[])

    # 1) Exact-URL auto-bind — check both the board URL and the direct one.
    target = normalize_url(url)
    if target:
        for c in cands:
            if normalize_url(c["job_url"]) == target or normalize_url(c["job_url_direct"]) == target:
                return MatchResult(bound_job_id=c["job_id"], candidates=[])

    # 2) Fuzzy → propose. No signal to score on ⇒ straight to fresh.
    if not (company or role_title or text):
        return MatchResult(bound_job_id=None, candidates=[])

    scored = [
        Candidate(
            job_id=c["job_id"], title=c["title"], company=c["company"],
            score=_score_candidate(c, company=company, role_title=role_title, text=text),
            tailored=c["tailored"],
        )
        for c in cands
    ]
    scored = [c for c in scored if c.score >= PROPOSE_THRESHOLD]
    # Best score first; tailored breaks ties; job_id keeps it deterministic.
    scored.sort(key=lambda c: (round(c.score, 4), c.tailored, c.job_id), reverse=True)
    return MatchResult(bound_job_id=None, candidates=scored[:MAX_CANDIDATES])
