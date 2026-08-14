"""In-memory state shared across requests within one running server.

Only safe for single-user local runs. If we ever multi-tenant, this
moves to Redis / DB.

Currently holds:
- `tailored_history[job_id]` — list of past Gemini-tailored runs for a
  job, newest last. Capped at MAX_TAILOR_HISTORY so we don't blow up
  memory over long sessions. Each entry:
      {"tailored": dict, "at": iso_string, "level": "conservative|balanced|aggressive"}
- `search_tasks[task_id]` — bookkeeping for background multi-search
  worker threads. Consumed by /jobs/loading/{task_id}/status poller.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


MAX_TAILOR_HISTORY = 5

tailored_history: dict[str, list[dict[str, Any]]] = {}

# Background search tasks — {task_id: {status, message, started_at, queries,
# result_url|None, error|None}}. Used by /jobs/run/multi to run
# 2+ scrapes off the request thread so the browser doesn't hang.
# Cleared when the server restarts, which is fine — active tasks can't
# survive a restart anyway (they'd lose their threads).
search_tasks: dict[str, dict[str, Any]] = {}


# Geocode typeahead cache — {"ottawa": {"html": "<option..>...", "expires": dt}}.
# Prevents hammering Photon on every keystroke. 24h TTL; cleared on server
# restart (harmless — Photon just repopulates on the next call).
geocode_cache: dict[str, dict[str, Any]] = {}


def record_tailor(job_id: str, tailored: dict[str, Any]) -> int:
    """Append a new tailor run for this job. Returns the index of the new run."""
    entry = {
        "tailored": tailored,
        "at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "level": tailored.get("tailoring_level", "?"),
    }
    hist = tailored_history.setdefault(job_id, [])
    hist.append(entry)
    # Cap history — drop oldest when over limit.
    if len(hist) > MAX_TAILOR_HISTORY:
        tailored_history[job_id] = hist[-MAX_TAILOR_HISTORY:]
    return len(tailored_history[job_id]) - 1


def get_tailored(job_id: str, run_index: int = -1) -> dict[str, Any] | None:
    """Return the tailored dict at index (default: latest). None if missing."""
    hist = tailored_history.get(job_id)
    if not hist:
        return None
    try:
        return hist[run_index]["tailored"]
    except IndexError:
        return None


def list_runs(job_id: str) -> list[dict[str, str]]:
    """Return {index, at, level} for each past run of this job (newest first)."""
    hist = tailored_history.get(job_id, [])
    return [
        {"index": i, "at": e["at"], "level": e["level"]}
        for i, e in enumerate(hist)
    ][::-1]
