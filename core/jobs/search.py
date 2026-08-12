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


# ---------- params + result types ----------

@dataclass
class JobSearchParams:
    query: str
    location: str = "Ottawa, Ontario, Canada"
    distance: int = 50           # km radius
    sites: list[str] = field(default_factory=lambda: ["indeed", "linkedin"])
    hours_old: int = 168         # 1 week
    results_wanted: int = 30
    is_remote: Optional[bool] = None
    country_indeed: str = "canada"
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
    job_url: str
    description: str
    is_remote: bool
    min_salary: Optional[float]
    max_salary: Optional[float]
    detected_language: str        # 'en' | 'fr' | 'mixed' | 'unknown'
    french_required: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------- public API ----------

def search_jobs(params: JobSearchParams) -> list[Job]:
    """Scrape jobs and return a list of cleaned Job dicts.

    Raises RuntimeError on hard failure; returns [] if the scrape succeeds
    but finds nothing.
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
    return jobs


# ---------- normalization ----------

def _row_to_job(row) -> Job:
    description = _coerce_str(row.get("description"))
    title = _coerce_str(row.get("title"))
    detected = _detect_language(f"{title}\n{description}")
    french_required = _french_required(description)

    return Job(
        id=str(row.get("id") or f"{row.get('site')}-{hash(row.get('job_url') or title)}"),
        title=title or "(no title)",
        company=_coerce_str(row.get("company")) or "(unknown company)",
        location=_coerce_str(row.get("location")),
        site=_coerce_str(row.get("site")),
        date_posted=_coerce_date(row.get("date_posted")),
        job_url=_coerce_str(row.get("job_url") or row.get("job_url_direct")),
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
