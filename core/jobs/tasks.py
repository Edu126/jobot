"""Durable background-task state for search workers.

Replaces the in-memory `ui_web.state.search_tasks` dict. Task state now
survives Fly `auto_stop_machines = 'stop'` cycling and process restarts
— important because a user can start a multi-search or Expand, close
their tab, and expect the loading page to still resolve when they come
back seconds/minutes later.

The worker thread itself doesn't survive process death, though — if the
machine stops mid-scrape, the task will sit in `status='running'` until
a wake-up sweep marks stale rows as failed. That's `mark_stale_failed()`,
called opportunistically from `create()`.

Callers:
    create(task_id, kind, payload)           — insert a queued row
    get(task_id) -> dict|None                — read current state
    update(task_id, **fields)                — patch status/message/etc.
    mark_done(task_id, result_url, message)  — convenience
    mark_failed(task_id, error)              — convenience
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from core import db


# A running task older than this is assumed dead (its worker was killed
# by a machine restart). `mark_stale_failed()` sets it to failed on the
# next `create()` — the polling UI then surfaces a clean error.
_STALE_RUNNING_HOURS = 2

# Rows older than this get purged. Users don't need a task history; the
# durable output is the cache entry, not the task row.
_PURGE_AFTER_HOURS = 24


def create(task_id: str, kind: str = "multi", payload: Optional[dict] = None) -> None:
    """Insert a queued task row. Purges stale + old rows opportunistically."""
    _sweep()
    now = _now()
    with db.tx() as conn:
        conn.execute(
            """INSERT INTO search_tasks
               (id, kind, status, message, started_at, updated_at, payload_json, result_url, error)
               VALUES (?, ?, 'queued', '', ?, ?, ?, NULL, NULL)""",
            (task_id, kind, now, now, json.dumps(payload or {}, ensure_ascii=False)),
        )


def get(task_id: str) -> Optional[dict]:
    """Return the task as a plain dict, or None if not found.

    Shape matches the pre-PR-2 in-memory dict so existing callers can be
    migrated with minimal churn:
        {status, message, started_at, queries, location, result_url,
         error, kind, updated_at}"""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM search_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    payload = _safe_json(d.pop("payload_json", "{}"))
    # Merge payload keys (queries, location, etc.) up to the top level for
    # backward-compat with the previous in-memory shape.
    for k, v in payload.items():
        d.setdefault(k, v)
    return d


def update(task_id: str, **fields: Any) -> None:
    """Patch selected fields on a task row. Unknown keys are folded into
    `payload_json` (so worker-specific extras don't need schema changes).

    `updated_at` is always refreshed."""
    known = {"status", "message", "result_url", "error"}
    top: dict[str, Any] = {}
    payload_patch: dict[str, Any] = {}
    for k, v in fields.items():
        if k in known:
            top[k] = v
        else:
            payload_patch[k] = v

    with db.tx() as conn:
        row = conn.execute(
            "SELECT payload_json FROM search_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return
        payload = _safe_json(row["payload_json"])
        if payload_patch:
            payload.update(payload_patch)

        set_clauses = [f"{k} = ?" for k in top]
        values: list[Any] = list(top.values())
        set_clauses.append("payload_json = ?")
        values.append(json.dumps(payload, ensure_ascii=False))
        set_clauses.append("updated_at = ?")
        values.append(_now())
        values.append(task_id)

        conn.execute(
            f"UPDATE search_tasks SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )


def mark_done(task_id: str, result_url: str, message: str = "") -> None:
    update(task_id, status="done", result_url=result_url, message=message or "Done")


def mark_failed(task_id: str, error: str) -> None:
    update(task_id, status="failed", error=error, message=error[:180])


def get_running_by_cache_key(cache_key: str) -> Optional[dict]:
    """Return the newest running/queued task whose payload references
    this cache_key, or None. Used by the results page (ADR-011) to
    detect "discovery still in progress for this cache" without needing
    a task_id URL query param.

    Legacy rows (created before Slice 5a) don't have `cache_key` in
    their payload and are silently skipped — those searches just get
    the pre-Slice-5 behavior (no auto-append banner) on refresh.

    The `LIKE` on payload_json is a pragmatic shortcut: cache_key
    values are 16 hex chars (see JobSearchParams.cache_key) so
    collisions against unrelated JSON fragments are astronomically
    unlikely. If concurrent-task volume ever grows, promote
    cache_key to its own indexed column (schema v15) — flagged as
    tech debt in project_sprint_state."""
    needle = f'%"cache_key": "{cache_key}"%'
    with db.connect() as conn:
        row = conn.execute(
            """SELECT id FROM search_tasks
               WHERE status IN ('running', 'queued')
                 AND payload_json LIKE ?
               ORDER BY updated_at DESC
               LIMIT 1""",
            (needle,),
        ).fetchone()
    return get(row["id"]) if row else None


# ── internals ──────────────────────────────────────────────────────────

def _sweep() -> None:
    """Prune old rows and fail stale-running ones. Cheap; called on every
    create() so the table stays tiny (dozens of rows max)."""
    now = datetime.utcnow()
    stale = (now - timedelta(hours=_STALE_RUNNING_HOURS)).isoformat(timespec="seconds") + "Z"
    purge = (now - timedelta(hours=_PURGE_AFTER_HOURS)).isoformat(timespec="seconds") + "Z"
    now_str = _now()
    with db.tx() as conn:
        # Mark stuck-running as failed with a specific message so the UI
        # can show something meaningful when the user returns after a nap.
        conn.execute(
            """UPDATE search_tasks
               SET status='failed', error='Task interrupted (server restarted)',
                   message='Task interrupted', updated_at=?
               WHERE status IN ('running','queued') AND updated_at < ?""",
            (now_str, stale),
        )
        conn.execute("DELETE FROM search_tasks WHERE updated_at < ?", (purge,))


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _safe_json(raw: Any) -> dict:
    if not raw:
        return {}
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}
