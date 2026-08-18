"""Kill-switch env vars — checked at every request, not at import time.

`fly secrets set LLM_DISABLED=1` should stop the bleeding without a
deploy. That only works if we read `os.environ` on each call — capturing
the value at import time would silently ignore a live change.

Truthy values: `1`, `true`, `yes`, `on` (case-insensitive). Everything
else (including unset) counts as "not disabled".

Handlers check these near the top and return a clean 503 with a
human-readable message. Individual flags let us cut off one surface
(e.g. tailoring blew up quota) without disabling the whole app.

Naming: verb-negated ("is_llm_disabled") reads naturally at call sites
(`if is_llm_disabled(): return ...`). Env var names stay the affirmative
noun form ("LLM_DISABLED") to match `fly secrets set` ergonomics.
"""
from __future__ import annotations

import os


_TRUTHY = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUTHY


def is_llm_disabled() -> bool:
    """When True, refuse every Gemini path. Overrides everything else —
    if the paid-tier quota alarm goes off, flip this and redeploy is
    unnecessary."""
    return _flag("LLM_DISABLED")


def is_scrape_disabled() -> bool:
    """When True, refuse jobspy scrape paths (search, multi, bulk,
    refresh, expand). Use when we're getting IP-blocked and need to
    stop hammering the source."""
    return _flag("SCRAPE_DISABLED")


def is_tailor_disabled() -> bool:
    """When True, refuse resume-tailoring paths only. Lets scoring and
    URL-import keep working during a tailor-specific incident."""
    return _flag("TAILOR_DISABLED")


# Standardized HTTP status + user-facing text for kill-switch responses.
# 503 rather than 429 — this is "server chose to say no", not "you're
# over quota". Clients (and any future monitoring) can distinguish.
KILL_SWITCH_STATUS = 503


def llm_disabled_message() -> str:
    return (
        "AI features are temporarily paused by the operator. "
        "Try again shortly — everything non-LLM (search, filters, saved jobs) still works."
    )


def scrape_disabled_message() -> str:
    return (
        "Job scraping is temporarily paused by the operator. "
        "Cached results and saved searches are still available."
    )


def tailor_disabled_message() -> str:
    return (
        "Resume tailoring is temporarily paused by the operator. "
        "Job scoring and URL import still work."
    )
