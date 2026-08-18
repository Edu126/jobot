"""Per-ATS adapter registry and dispatch.

The extractor waterfall lives in `core.jobs.from_url.job_from_url()`:
    matching adapter → JSON-LD fallback → LLM fallback

Adapters here are tried in priority order (fastest / highest-confidence
first). The first adapter whose `matches(url)` returns True gets a chance;
if its `fetch(url)` fails, we log an `extract.failed` event and fall
through — we never raise up to the caller for a per-adapter failure.

Adding a new adapter:
    1. Implement `AtsAdapter` in a new module here.
    2. Add its instance to `_REGISTRY` below.
    3. Add a canary URL to `scripts/probe_adapters.py` (PR 3).
"""
from __future__ import annotations

from typing import Optional

from core import events

from .base import AtsAdapter
from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter
from .oracle_hcm import OracleHcmAdapter


# Order matters — most specific first. Oracle HCM ahead of any generic
# fallback because its URL pattern is unambiguous and the REST endpoint
# is fast; the SPA HTML fallback would return nothing.
_REGISTRY: list[AtsAdapter] = [
    OracleHcmAdapter(),
    GreenhouseAdapter(),
    LeverAdapter(),
]


def dispatch(url: str) -> Optional[dict]:
    """Try each registered adapter. Returns a Job-shaped dict on first
    success, or None if no adapter matched or every matching adapter
    failed to fetch. Callers should fall through to JSON-LD / LLM on None.

    Per-adapter failures emit `EXTRACT_FAILED` with the adapter name so
    silent rot shows up in the event log before a user reports garbage
    output."""
    if not url:
        return None
    for adapter in _REGISTRY:
        try:
            if not adapter.matches(url):
                continue
        except Exception as exc:  # noqa: BLE001 — matches() must never crash dispatch
            events.track(
                events.EXTRACT_FAILED,
                adapter=adapter.name,
                stage="matches",
                url=url[:240],
                reason=str(exc)[:240],
            )
            continue
        try:
            result = adapter.fetch(url)
        except Exception as exc:  # noqa: BLE001 — fetch failure = fall through
            events.track(
                events.EXTRACT_FAILED,
                adapter=adapter.name,
                stage="fetch",
                url=url[:240],
                reason=str(exc)[:240],
            )
            continue
        if result:
            return result
    return None


__all__ = ["AtsAdapter", "dispatch"]
