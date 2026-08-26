"""Illustrative saved-search examples — not wired into any live route.

REQ-006: this module used to hardcode 3 AEC/Ottawa presets for a single
early user. The actual saved-searches feature is DB-backed
(`db.list_saved_searches()` / the `saved_searches` table) and per-user
editable, seeded empty (see `db._seed_saved_searches_if_empty`'s
docstring) — a Sales/BI/tech user should never see AEC-tuned defaults.
This module is kept only as a domain-neutral reference of the
`JobSearchParams` shape for future template/preset work; nothing reads
`SAVED_SEARCHES` at runtime today.
"""
from __future__ import annotations

from .search import JobSearchParams


SAVED_SEARCHES: dict[str, JobSearchParams] = {
    "BI / Data Analyst": JobSearchParams(
        query="BI analyst",
        location="Toronto, Ontario, Canada",
        distance=50,
        results_wanted=30,
        hours_old=168,
    ),
    "B2B Account Executive": JobSearchParams(
        query="B2B account executive",
        location="Bogota, Colombia",
        distance=50,
        results_wanted=30,
        hours_old=168,
    ),
    "Junior Project Coordinator": JobSearchParams(
        query="junior project coordinator",
        location="Madrid, Spain",
        distance=50,
        results_wanted=30,
        hours_old=168,
    ),
}
