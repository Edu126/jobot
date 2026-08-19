"""Job-board search wrapping python-jobspy.

Scope:
- Tuned for Canada (Ottawa metro by default).
- Returns a list of clean Job dicts — never a DataFrame, never None.
- Detects English vs French descriptions (heuristic — see _detect_language)
  so the UI can hide French-required postings if asked.
- Catches jobspy/network failures so the UI can render the error instead
  of crashing the whole tab.

Out of scope (later slices):
- Persistent job DB. We cache by query-hash to disk (see cache.py) but
  the canonical store is still per-search files.
- Auto-apply. The user opens the job_url and applies manually.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

from jobspy import scrape_jobs


# ---------- country → jobspy country_indeed slug ----------
#
# jobspy's `country_indeed` param picks which Indeed regional index to
# search. Values are its own slugs — mostly ISO English country names
# lowercased, plus a few historical aliases ("usa", "uk"). Grown as
# real users arrive from new countries; canonical source is jobspy's
# `Country` enum in its source tree.
_COUNTRY_TO_INDEED: dict[str, str] = {
    "canada": "canada",
    "united states": "usa",   "usa": "usa",   "us": "usa",
    "united kingdom": "uk",   "uk": "uk",
    "spain": "spain",         "españa": "spain",
    "colombia": "colombia",
    "mexico": "mexico",       "méxico": "mexico",
    "argentina": "argentina",
    "chile": "chile",
    "france": "france",
    "germany": "germany",     "alemania": "germany",
}
_DEFAULT_COUNTRY_INDEED = "canada"
_DEFAULT_LOCATION = "Ottawa, Ontario, Canada"


def default_location() -> str:
    """Preferred search location — user's home city if set in settings,
    otherwise the historical Ottawa default. Read on every JobSearchParams
    construction via `field(default_factory=...)` so a Profile change
    takes effect on the next search without an app restart."""
    from core.settings import get
    return get("home_city", "") or _DEFAULT_LOCATION


def default_country_indeed() -> str:
    """Which Indeed regional index to hit — derived from `settings.home_country`.
    Unknown / unmapped countries fall back to canada so at least Indeed
    still responds; user can override at search time if needed."""
    from core.settings import get
    country = (get("home_country", "") or "").strip().lower()
    return _COUNTRY_TO_INDEED.get(country, _DEFAULT_COUNTRY_INDEED)


# ---------- params + result types ----------

@dataclass
class JobSearchParams:
    query: str
    # location + country_indeed both use factory defaults so a Profile
    # change (Sara in Spain, sister in Colombia) takes effect immediately
    # without touching this class or the many callers that construct
    # JobSearchParams with only `query=` positional.
    location: str = field(default_factory=default_location)
    distance: int = 50           # km radius
    # v0.5: added 'google' — jobspy already builds a google_search_term (see
    # scrape_jobs call below) so we just need to include the site. Google
    # often surfaces roles that Indeed/LinkedIn miss (small firm career pages
    # indexed by Google for Jobs). Cross-source duplicates are collapsed via
    # a normalized (company|title|location) key in _dedup_across_sources().
    sites: list[str] = field(default_factory=lambda: ["indeed", "linkedin", "google"])
    hours_old: int = 168         # 1 week
    results_wanted: int = 30
    is_remote: Optional[bool] = None
    country_indeed: str = field(default_factory=default_country_indeed)
    linkedin_fetch_description: bool = True

    def cache_key(self) -> str:
        """Stable string for cache hashing."""
        import hashlib, json
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha1(payload.encode()).hexdigest()[:16]


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    site: str
    date_posted: str
    job_url: str                        # link on the source board (LinkedIn, Indeed, etc.)
    description: str
    is_remote: bool
    min_salary: Optional[float]
    max_salary: Optional[float]
    detected_language: str              # 'en' | 'fr' | 'mixed' | 'unknown'
    french_required: bool
    # Direct link to the company's own career page for this posting, when the
    # board exposes it. Skipping the board's "Apply" wall saves the user 1-2
    # clicks per application. None when the board doesn't provide it.
    job_url_direct: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------- public API ----------

def search_jobs(params: JobSearchParams) -> list[Job]:
    """Scrape jobs and return a list of cleaned Job dicts.

    Raises RuntimeError on hard failure; returns [] if the scrape succeeds
    but finds nothing. On any failure we emit a search.blocked event so the
    Journey tab (or a future ops dashboard) can spot patterns — e.g.
    LinkedIn blocking us 3 days in a row = time for a mitigation.
    """
    try:
        df = scrape_jobs(
            site_name=params.sites,
            search_term=params.query,
            google_search_term=f"{params.query} jobs near {params.location} in the past week",
            location=params.location,
            distance=params.distance,
            results_wanted=params.results_wanted,
            hours_old=params.hours_old,
            is_remote=params.is_remote if params.is_remote is not None else False,
            country_indeed=params.country_indeed,
            linkedin_fetch_description=params.linkedin_fetch_description,
        )
    except Exception as exc:
        # Try to attribute the block to a specific site so we know WHO
        # rate-limited us. jobspy's exceptions often mention the source
        # in their str form ("linkedin: ...", "indeed: ..." etc).
        _emit_blocked_event(params, str(exc))
        raise RuntimeError(f"jobspy scrape failed: {exc}") from exc

    if df is None or len(df) == 0:
        return []

    jobs: list[Job] = []
    for _, row in df.iterrows():
        try:
            jobs.append(_row_to_job(row))
        except Exception:
            # one bad row shouldn't kill the whole result set
            continue
    return _dedup_across_sources(jobs)


def _dedup_across_sources(jobs: list[Job]) -> list[Job]:
    """Collapse duplicates across sources. jobspy IDs are per-source, so a
    LinkedIn listing and its Google-for-Jobs mirror don't dedupe by id.
    Falls back to a normalized (company|title|location) key. First seen wins
    — we prefer the earlier source in the search order (indeed, linkedin,
    google) because LinkedIn/Indeed have richer descriptions than Google's
    scraped snippets. When we drop a dup, we opportunistically fill the
    winner's job_url_direct from the loser if the winner lacked one."""
    seen: dict[str, int] = {}   # key → index into `out`
    out: list[Job] = []
    for j in jobs:
        norm_company = _norm_key(j.company, is_company=True)
        norm_title = _norm_key(j.title)
        norm_loc = _norm_key(j.location.split(",")[0] if j.location else "")
        # Also fall back to id-based dedup so the same source's exact repeat
        # (unlikely but possible) still collapses.
        keys = [
            f"id::{j.id}",
            f"ctl::{norm_company}|{norm_title}|{norm_loc}",
        ]
        matched_idx: Optional[int] = None
        for k in keys:
            if k in seen:
                matched_idx = seen[k]
                break
        if matched_idx is None:
            for k in keys:
                seen[k] = len(out)
            out.append(j)
        else:
            winner = out[matched_idx]
            # Opportunistically upgrade the winner with data the loser has
            if not winner.job_url_direct and j.job_url_direct:
                winner.job_url_direct = j.job_url_direct
            if not winner.description and j.description:
                winner.description = j.description
    return out


# Common corporate suffixes that create false negatives when comparing
# company names across sources ('Acme' vs 'Acme Inc' vs 'Acme, LLC').
# Applied only to the company field.
_CORP_SUFFIX_RE = re.compile(
    r"\s+(inc|incorporated|ltd|limited|llc|llp|plc|pllc|corp|corporation|"
    r"co|company|gmbh|group|holdings|international|intl|sa|nv)\.?$",
    re.IGNORECASE,
)


def _norm_key(s: str, *, is_company: bool = False) -> str:
    """Lowercase + strip + collapse whitespace + drop punctuation so
    'BIM Coordinator' and 'BIM  coordinator!' hash to the same string.
    When `is_company=True`, also strip corporate suffixes so 'Acme',
    'Acme Inc', and 'Acme, LLC' all collapse to the same key."""
    if not s:
        return ""
    s = str(s).lower()
    if is_company:
        # Strip iteratively so 'Acme Corp Inc' → 'acme'
        prev = None
        while prev != s:
            prev = s
            s = _CORP_SUFFIX_RE.sub("", s).strip().rstrip(",.")
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- normalization ----------

def _emit_blocked_event(params: JobSearchParams, err_msg: str) -> None:
    """Log a search.blocked event so the Journey view surfaces scraper
    friction. Attribution is best-effort — we look for site names in the
    error message. Import is local so search.py stays importable if
    events.py ever grows a hard dependency."""
    try:
        from core import events
    except Exception:  # noqa: BLE001
        return
    lower = err_msg.lower()
    site = "unknown"
    for candidate in ("linkedin", "indeed", "google", "glassdoor", "zip"):
        if candidate in lower:
            site = candidate
            break
    # Rough block-category heuristic — help future filtering without a
    # human having to parse raw errors.
    reason = "other"
    if "429" in err_msg or "rate" in lower or "throttle" in lower:
        reason = "rate_limit"
    elif "403" in err_msg or "forbidden" in lower or "cloudflare" in lower:
        reason = "blocked"
    elif "timeout" in lower or "timed out" in lower:
        reason = "timeout"
    events.track(
        events.SEARCH_BLOCKED,
        site=site,
        reason=reason,
        query=params.query,
        error=err_msg[:240],
    )


def _row_to_job(row) -> Job:
    description = _coerce_str(row.get("description"))
    title = _coerce_str(row.get("title"))
    detected = _detect_language(f"{title}\n{description}")
    french_required = _french_required(description)

    # Keep board URL and direct URL SEPARATE — the user needs both.
    # `job_url` is the LinkedIn/Indeed post; `job_url_direct` (when
    # present) is the company's own career page where you actually apply.
    # Skipping the board saves the user 1-2 clicks per application.
    board_url = _coerce_str(row.get("job_url"))
    direct_url = _coerce_str(row.get("job_url_direct")) or None
    # If we only have one URL total, put it in job_url so the UI has a
    # single button to fall back on.
    if not board_url and direct_url:
        board_url, direct_url = direct_url, None
    return Job(
        id=str(row.get("id") or f"{row.get('site')}-{hash(board_url or direct_url or title)}"),
        title=title or "(no title)",
        company=_coerce_str(row.get("company")) or "(unknown company)",
        location=_coerce_str(row.get("location")),
        site=_coerce_str(row.get("site")),
        date_posted=_coerce_date(row.get("date_posted")),
        job_url=board_url,
        job_url_direct=direct_url,
        description=description,
        is_remote=bool(row.get("is_remote")) if row.get("is_remote") is not None else False,
        min_salary=_coerce_float(row.get("min_amount")),
        max_salary=_coerce_float(row.get("max_amount")),
        detected_language=detected,
        french_required=french_required,
    )


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    try:
        # jobspy sometimes returns pandas Timestamps
        return str(value)[:10]
    except Exception:
        return ""


# ---------- language detection ----------

_FRENCH_MARKERS = {
    "et", "le", "la", "les", "des", "du", "de", "pour", "avec", "dans",
    "sur", "par", "aux", "votre", "nos", "nous", "vous", "cette", "ces",
    "son", "sa", "ses", "qui", "que", "est", "sont", "être", "faire",
    "ainsi", "selon", "afin", "auprès", "envers",
}
_ENGLISH_MARKERS = {
    "the", "and", "with", "for", "this", "that", "your", "our", "you",
    "we", "are", "have", "will", "has", "their", "these", "an", "from",
    "be", "is", "of", "in", "to", "as", "or", "by", "at",
}


def _detect_language(text: str) -> str:
    tokens = re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ]+", text.lower())
    if len(tokens) < 8:
        return "unknown"
    fr = sum(1 for t in tokens if t in _FRENCH_MARKERS)
    en = sum(1 for t in tokens if t in _ENGLISH_MARKERS)
    if fr == 0 and en == 0:
        return "unknown"
    if fr >= en * 1.5 and fr >= 5:
        return "fr"
    if en >= fr * 1.5 and en >= 5:
        return "en"
    return "mixed"


_FRENCH_REQUIRED_RE = re.compile(
    r"(bilingu(?:e|al)\s+(?:required|mandat|obligat|essential|must|is\s+required))"
    r"|(french[^.]{0,40}(?:required|mandatory|essential|must))"
    r"|(français[^.]{0,40}(?:obligatoire|requis|essentiel))"
    r"|(must\s+be\s+bilingual)"
    r"|(maîtrise\s+du\s+français)"
    r"|(fully\s+bilingual)",
    re.IGNORECASE,
)


def _french_required(description: str) -> bool:
    if not description:
        return False
    return bool(_FRENCH_REQUIRED_RE.search(description))
