"""Disk cache for job search results.

Keyed by params.cache_key(). A scrape can take 30-60 seconds and hit
rate limits, so we cache aggressively and let the user force-refresh.

Cache files live in data/jobs_cache/<key>.json.

Each file now stores the params dict alongside the results so we can
reconstruct the JobSearchParams when listing the user's recent
searches.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

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


def load(params: JobSearchParams) -> Optional[CachedResult]:
    path = cache_path(params)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CachedResult(
            fetched_at=data["fetched_at"],
            params_label=data.get("params_label", ""),
            jobs=[Job(**j) for j in data.get("jobs", [])],
        )
    except Exception:
        # Corrupt cache file — pretend it doesn't exist.
        return None


def save(params: JobSearchParams, jobs: list[Job], label: str = "") -> CachedResult:
    result = CachedResult(
        fetched_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        params_label=label,
        jobs=jobs,
    )
    payload = {
        "fetched_at": result.fetched_at,
        "params_label": result.params_label,
        "params": asdict(params),
        "jobs": [j.to_dict() for j in result.jobs],
    }
    cache_path(params).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return result


def list_recent(limit: int = 5) -> list[RecentSearch]:
    """Return the user's most recent searches, newest first.

    Older cache files (saved before we stored params) are skipped — we
    can't reconstruct the params, so we'd have no way to re-run them.
    """
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
        items.append(RecentSearch(
            label=data.get("params_label") or params.query,
            fetched_at=data.get("fetched_at", ""),
            job_count=len(data.get("jobs", [])),
            params=params,
        ))
    items.sort(key=lambda r: r.fetched_at, reverse=True)
    return items[:limit]
