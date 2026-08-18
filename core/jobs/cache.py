"""Disk cache for job search results.

Keyed by params.cache_key(). A scrape can take 30-60 seconds and hit
rate limits, so we cache aggressively and let the user force-refresh.

Cache files live in data/jobs_cache/<key>.json.

**Format (as of PR 2):** each file stores only pointers into the shared
`jobs` SQLite table — {fetched_at, params, params_label, job_ids: [...]}.
Full Job dicts live in the DB, upserted by `search_jobs` callers. This
means an Expand pass can merge new jobs into the same cache entry without
re-storing the whole result set, and the recent-searches picker doesn't
duplicate megabytes of job descriptions across many files.

**Lazy migration:** the reader accepts both the new pointer format and
the legacy `{jobs: [...]}` format. Old files keep working; new writes
use the pointer format; old files age out naturally over normal use.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from core import db

from .search import Job, JobSearchParams


CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "jobs_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class CachedResult:
    fetched_at: str           # ISO-8601 UTC-ish
    params_label: str         # human label, for the UI
    jobs: list[Job]


@dataclass
class RecentSearch:
    """Light summary of a past search — for the Find Jobs picker."""
    label: str
    fetched_at: str
    job_count: int
    params: JobSearchParams


def cache_path(params: JobSearchParams) -> Path:
    return CACHE_DIR / f"{params.cache_key()}.json"


def cache_path_for_key(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.json"


def load(params: JobSearchParams) -> Optional[CachedResult]:
    """Load a cache entry by params. Returns None if not present or the
    file is corrupt (treated as a cache miss — safer than crashing).

    Handles both pointer format (`job_ids`) and legacy inline format
    (`jobs`). Pointer entries hydrate from `db.jobs` via `db.get_jobs()`;
    ids missing from the DB are silently dropped from the returned list."""
    return load_by_key(params.cache_key())


def load_by_key(cache_key: str) -> Optional[CachedResult]:
    path = cache_path_for_key(cache_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    fetched_at = data.get("fetched_at", "")
    params_label = data.get("params_label", "")
    jobs = _hydrate_jobs(data)
    return CachedResult(fetched_at=fetched_at, params_label=params_label, jobs=jobs)


def _hydrate_jobs(data: dict) -> list[Job]:
    """Turn a cache-file payload into a list of Job dataclasses."""
    if "job_ids" in data:
        rows = db.get_jobs(data.get("job_ids") or [])
        return [_job_from_db_row(r) for r in rows]
    # Legacy: inline jobs (pre-PR 2 files).
    return [Job(**j) for j in data.get("jobs", [])]


def _job_from_db_row(row: dict) -> Job:
    """Convert a `jobs` table row (sqlite Row/dict) to a Job dataclass.

    The DB row has more columns than Job (first_seen, last_seen); only
    Job's declared fields are copied. Missing optional fields default."""
    return Job(
        id=row["id"],
        title=row.get("title") or "",
        company=row.get("company") or "",
        location=row.get("location") or "",
        site=row.get("site") or "",
        date_posted=row.get("date_posted") or "",
        job_url=row.get("job_url") or "",
        description=row.get("description") or "",
        is_remote=bool(row.get("is_remote")),
        min_salary=row.get("min_salary"),
        max_salary=row.get("max_salary"),
        detected_language=row.get("detected_language") or "",
        french_required=bool(row.get("french_required")),
        job_url_direct=row.get("job_url_direct"),
    )


def save(params: JobSearchParams, jobs: list[Job], label: str = "") -> CachedResult:
    """Persist the search result as a pointer file. Assumes the caller has
    already `db.upsert_jobs()`d the full Job dicts — this only stores IDs.

    Returns a CachedResult mirroring what was written, so callers can use
    it without re-loading from disk."""
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    payload = {
        "fetched_at": fetched_at,
        "params_label": label,
        "params": asdict(params),
        "job_ids": [j.id for j in jobs],
    }
    cache_path(params).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return CachedResult(fetched_at=fetched_at, params_label=label, jobs=list(jobs))


def merge_into(cache_key: str, new_jobs: list[Job], new_label: Optional[str] = None) -> Optional[CachedResult]:
    """Append `new_jobs` to an existing cache entry, deduping by Job.id.
    Refreshes `fetched_at`. Optionally updates the label (used by Expand
    to switch label from "{query}" to "{query} (expanded)").

    Returns the updated CachedResult, or None if the cache entry is gone.

    Caller must have `db.upsert_jobs`d the new jobs first — this only
    manipulates the pointer file."""
    path = cache_path_for_key(cache_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Normalize existing data to pointer shape so we don't re-write legacy
    # inline entries as-is.
    if "job_ids" in data:
        existing_ids: list[str] = list(data.get("job_ids") or [])
    else:
        existing_ids = [j.get("id") for j in (data.get("jobs") or []) if j.get("id")]

    seen = set(existing_ids)
    merged_ids = list(existing_ids)
    for j in new_jobs:
        if j.id not in seen:
            merged_ids.append(j.id)
            seen.add(j.id)

    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    label = new_label if new_label is not None else data.get("params_label", "")
    payload = {
        "fetched_at": fetched_at,
        "params_label": label,
        "params": data.get("params") or {},
        "job_ids": merged_ids,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    hydrated = db.get_jobs(merged_ids)
    return CachedResult(
        fetched_at=fetched_at,
        params_label=label,
        jobs=[_job_from_db_row(r) for r in hydrated],
    )


def age_seconds(fetched_at: str) -> Optional[float]:
    """Seconds since `fetched_at` (ISO-8601). Returns None on parse error."""
    if not fetched_at:
        return None
    try:
        dt = datetime.fromisoformat(fetched_at.rstrip("Z"))
    except (TypeError, ValueError):
        return None
    return (datetime.utcnow() - dt).total_seconds()


def list_recent(limit: int = 5) -> list[RecentSearch]:
    """Return the user's most recent searches, newest first.

    Older cache files (saved before we stored params) are skipped — we
    can't reconstruct the params, so we'd have no way to re-run them.

    Counts jobs from whichever format the file uses (`job_ids` for new
    pointer format, `jobs` for legacy inline)."""
    items: list[RecentSearch] = []
    for path in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        params_raw = data.get("params")
        if not params_raw:
            continue
        try:
            params = JobSearchParams(**params_raw)
        except Exception:
            continue
        count = len(data.get("job_ids") or data.get("jobs") or [])
        items.append(RecentSearch(
            label=data.get("params_label") or params.query,
            fetched_at=data.get("fetched_at", ""),
            job_count=count,
            params=params,
        ))
    items.sort(key=lambda r: r.fetched_at, reverse=True)
    return items[:limit]
