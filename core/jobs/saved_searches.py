"""Pre-baked saved searches.

Tuned for the AEC/construction roles user's boyfriend is targeting in
Ottawa. Each entry is a label + JobSearchParams; the UI exposes them as
a dropdown.

To add more searches, edit this file — it's the cheapest source of truth
until we add per-profile config in slice 4.
"""
from __future__ import annotations

from .search import JobSearchParams


SAVED_SEARCHES: dict[str, JobSearchParams] = {
    "BIM Coordinator / Modeler": JobSearchParams(
        query="BIM coordinator",
        location="Ottawa, Ontario, Canada",
        distance=50,
        results_wanted=30,
        hours_old=168,
    ),
    "Construction Estimator": JobSearchParams(
        query="construction estimator",
        location="Ottawa, Ontario, Canada",
        distance=50,
        results_wanted=30,
        hours_old=168,
    ),
    "Junior Project Coordinator": JobSearchParams(
        query="junior project coordinator construction",
        location="Ottawa, Ontario, Canada",
        distance=50,
        results_wanted=30,
        hours_old=168,
    ),
}
