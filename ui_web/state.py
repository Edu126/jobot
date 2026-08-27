"""In-memory state shared across requests within one running server.

Only safe for single-user local runs. If we ever multi-tenant, this
moves to Redis / DB.

Currently holds:
- `tailored_history[job_id]` — list of past Gemini-tailored runs for a
  job, newest last. Capped at MAX_TAILOR_HISTORY so we don't blow up
  memory over long sessions. Each entry:
      {"tailored": dict, "at": iso_string,
       "level": "conservative|balanced|aggressive",
       "language": "en|es"}
  Write-through to SQLite (`tailor_runs` table) so runs survive Fly
  `auto_stop_machines` cycling. RAM is the hot cache; DB is the fallback.
- `geocode_cache[query]` — 24h Photon typeahead cache.

**Removed in PR 2:** `search_tasks`. Background multi-search + Expand
task state now lives in the SQLite `search_tasks` table via
`core.jobs.tasks` — durable across Fly `auto_stop_machines` cycling.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core import db


MAX_TAILOR_HISTORY = 5

tailored_history: dict[str, list[dict[str, Any]]] = {}


# Geocode typeahead cache — {"ottawa": {"html": "<option..>...", "expires": dt}}.
# Prevents hammering Photon on every keystroke. 24h TTL; cleared on server
# restart (harmless — Photon just repopulates on the next call).
geocode_cache: dict[str, dict[str, Any]] = {}


def record_tailor(job_id: str, tailored: dict[str, Any]) -> int:
    """Append a new tailor run for this job. Returns the index of the new run.

    Language is captured from user settings at the time of the call — a
    user who tailors twice with different Output-language settings gets
    two coexisting versions in history (one EN, one ES), both visible
    in the tailor drawer's past-runs list with a language chip.

    Write-through: also persists to the `tailor_runs` SQLite table so
    the run survives machine sleep/restart.
    """
    from core.settings import get_output_language
    level = tailored.get("tailoring_level", "?")
    language = get_output_language()
    entry = {
        "tailored": tailored,
        "at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "level": level,
        "language": language,
    }
    hist = tailored_history.setdefault(job_id, [])
    hist.append(entry)
    # Cap RAM history — drop oldest when over limit.
    if len(hist) > MAX_TAILOR_HISTORY:
        tailored_history[job_id] = hist[-MAX_TAILOR_HISTORY:]
    db.save_tailor_run(job_id, level, language, tailored)
    return len(tailored_history[job_id]) - 1


def get_tailored(job_id: str, run_index: int = -1) -> dict[str, Any] | None:
    """Return the tailored dict at index (default: latest). None if missing.

    Falls back to SQLite when RAM cache is empty (e.g. after machine restart).
    """
    hist = tailored_history.get(job_id)
    if hist:
        try:
            return hist[run_index]["tailored"]
        except IndexError:
            return None
    return db.get_tailor_run(job_id, run_index)


def get_tailored_language(job_id: str, run_index: int = -1) -> str:
    """Language the specified run was generated in ('en' | 'es' | '').

    Falls back to SQLite when RAM cache is empty.
    """
    hist = tailored_history.get(job_id)
    if hist:
        try:
            return hist[run_index].get("language", "") or ""
        except IndexError:
            return ""
    runs = db.list_tailor_runs(job_id)
    if not runs:
        return ""
    try:
        return runs[run_index].get("language", "") or ""
    except IndexError:
        return ""


def list_runs(job_id: str) -> list[dict[str, str]]:
    """Return {index, at, level, language} for each past run of this
    job (newest first). Language surfaces the (EN)/(ES) tag in the
    tailor drawer's past-runs list.

    Falls back to SQLite when RAM cache is empty.
    """
    hist = tailored_history.get(job_id, [])
    if hist:
        return [
            {
                "index": i,
                "at": e["at"],
                "level": e["level"],
                "language": e.get("language", ""),
            }
            for i, e in enumerate(hist)
        ][::-1]
    # RAM empty — read from DB. Index is the reverse position (0 = latest).
    db_runs = db.list_tailor_runs(job_id)
    return [
        {
            "index": i,
            "at": r["created_at"],
            "level": r["level"],
            "language": r.get("language", ""),
        }
        for i, r in enumerate(db_runs)
    ]
