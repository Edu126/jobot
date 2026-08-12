"""Local-only event log — the Insights view on Profile reads from here.

Design notes:
- Data is never sent externally. This is a hard rule anchored to the
  local-first philosophy in the Notion North Star.
- Writes are synchronous but tiny (single INSERT). SQLite handles thousands
  of inserts per second on modern hardware, so a background queue is
  premature optimization for a single-user desktop app.
- Every event has a type string + JSON payload. Query helpers below shape
  the raw log into the aggregates the dashboard needs.
- Errors in track() are swallowed (logged only) — analytics must never
  break a user action. If the DB is locked or the payload is unserializable,
  we drop the event silently.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from core import db


_LOG = logging.getLogger(__name__)


# ── Event vocabulary — keep in sync with the Notion North Star ──
# Session / navigation
PAGE_VIEW              = "page_view"
PAGE_HIDDEN            = "page_hidden"          # tab lost focus (visibilitychange)
# Search
SEARCH_BROAD           = "search.broad"         # /jobs/run/multi
SEARCH_URL_IMPORT      = "search.url_import"    # /jobs/from-url
SEARCH_REFRESH         = "search.refresh"       # /jobs/refresh/{key}
# Job interactions
JOB_DETAIL_VIEWED      = "job.detail_viewed"
JOB_SAVED              = "job.saved"
JOB_UNSAVED            = "job.unsaved"
# Tailoring
TAILOR_GENERATED       = "tailor.generated"
TAILOR_RESUME_DOWNLOAD = "tailor.resume_downloaded"
TAILOR_CL_DOWNLOAD     = "tailor.cover_letter_downloaded"
# Applications
APP_STATUS_CHANGED     = "app.status_changed"
# Resume
RESUME_UPLOADED        = "resume.uploaded"
ATS_REPORT_VIEWED      = "ats.report_viewed"
# Errors / friction
ERROR                  = "error"


def track(event_type: str, **payload: Any) -> None:
    """Log one event. Never raises."""
    try:
        with db.tx() as conn:
            conn.execute(
                "INSERT INTO events (ts_utc, type, payload_json) VALUES (?, ?, ?)",
                (
                    datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    event_type,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )
    except Exception as exc:  # noqa: BLE001 — analytics must never break UX
        _LOG.debug("event.track failed: %s (%s)", exc, event_type)


# ── Query helpers used by /profile/insights ─────────────────────────

def total_events() -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
        return int(row["n"])


def events_since(days: int) -> list[dict]:
    """Return every event of the last `days` days, newest first. Cap at
    5000 rows so the dashboard render never blows up if the log grows."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, ts_utc, type, payload_json FROM events "
            "WHERE ts_utc >= ? ORDER BY ts_utc DESC LIMIT 5000",
            (since,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "ts_utc": r["ts_utc"],
            "type": r["type"],
            "payload": _safe_json(r["payload_json"]),
        }
        for r in rows
    ]


def counts_by_type_last_week() -> dict[str, int]:
    since = (datetime.utcnow() - timedelta(days=7)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT type, COUNT(*) AS n FROM events WHERE ts_utc >= ? GROUP BY type",
            (since,),
        ).fetchall()
    return {r["type"]: int(r["n"]) for r in rows}


def daily_activity(days: int = 14) -> list[dict]:
    """Rows of {day: 'YYYY-MM-DD', count: N} for the last `days` days,
    oldest first. Useful for a spark-bar visualization."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT substr(ts_utc, 1, 10) AS day, COUNT(*) AS n "
            "FROM events WHERE ts_utc >= ? GROUP BY day ORDER BY day",
            (since,),
        ).fetchall()
    return [{"day": r["day"], "count": int(r["n"])} for r in rows]


def hour_of_day_histogram(days: int = 14) -> list[int]:
    """List of 24 ints — count of events by hour of the day (UTC) over the
    last `days` days. Index 0 = 00:00-01:00 UTC, index 23 = 23:00-00:00."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT CAST(substr(ts_utc, 12, 2) AS INTEGER) AS hour, COUNT(*) AS n "
            "FROM events WHERE ts_utc >= ? GROUP BY hour",
            (since,),
        ).fetchall()
    buckets = [0] * 24
    for r in rows:
        h = int(r["hour"])
        if 0 <= h < 24:
            buckets[h] = int(r["n"])
    return buckets


def funnel_last_month() -> dict[str, int]:
    """Count distinct jobs the user touched at each funnel step in the last
    30 days. viewed = detail opened; saved = save event; applied+ = status
    change events. Distinct-by-job so opening one job twice counts once."""
    since = (datetime.utcnow() - timedelta(days=30)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT type,
                   COUNT(DISTINCT json_extract(payload_json, '$.job_id')) AS n
            FROM events
            WHERE ts_utc >= ?
              AND type IN (?, ?, ?)
            GROUP BY type
            """,
            (since, JOB_DETAIL_VIEWED, JOB_SAVED, APP_STATUS_CHANGED),
        ).fetchall()

        # applications-table counts as ground truth for reached-status counts
        # (an app might have been saved without an event, e.g. before we
        # started instrumenting). Trust the durable state for these steps.
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM applications GROUP BY status"
        ).fetchall()

    by_type = {r["type"]: int(r["n"]) for r in rows}
    status_counts = {r["status"]: int(r["n"]) for r in status_rows}
    return {
        "viewed": by_type.get(JOB_DETAIL_VIEWED, 0),
        "saved": (
            status_counts.get("interested", 0)
            + status_counts.get("applied", 0)
            + status_counts.get("interviewing", 0)
            + status_counts.get("offer", 0)
            + status_counts.get("rejected", 0)
            + status_counts.get("withdrawn", 0)
        ),
        "applied": (
            status_counts.get("applied", 0)
            + status_counts.get("interviewing", 0)
            + status_counts.get("offer", 0)
            + status_counts.get("rejected", 0)
        ),
        "interviewing": (
            status_counts.get("interviewing", 0) + status_counts.get("offer", 0)
        ),
        "offer": status_counts.get("offer", 0),
    }


def days_with_activity(days: int = 14) -> int:
    """Distinct calendar days (UTC) with at least one event in the last
    `days` days."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT substr(ts_utc, 1, 10)) AS n "
            "FROM events WHERE ts_utc >= ?",
            (since,),
        ).fetchone()
    return int(row["n"])


def median_time_to_download_seconds(days: int = 30) -> Optional[float]:
    """Median seconds between job.detail_viewed and tailor.resume_downloaded
    for the same job_id in the last N days. Returns None if there's not enough
    data yet."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT
                json_extract(payload_json, '$.job_id') AS job_id,
                type,
                ts_utc
            FROM events
            WHERE ts_utc >= ?
              AND type IN (?, ?)
              AND json_extract(payload_json, '$.job_id') IS NOT NULL
            ORDER BY ts_utc
            """,
            (since, JOB_DETAIL_VIEWED, TAILOR_RESUME_DOWNLOAD),
        ).fetchall()

    # Pair each download with the last preceding view of the same job
    last_view: dict[str, datetime] = {}
    deltas_s: list[float] = []
    for r in rows:
        job_id = r["job_id"]
        ts = _parse_ts(r["ts_utc"])
        if not job_id or not ts:
            continue
        if r["type"] == JOB_DETAIL_VIEWED:
            last_view[job_id] = ts
        elif r["type"] == TAILOR_RESUME_DOWNLOAD and job_id in last_view:
            deltas_s.append((ts - last_view[job_id]).total_seconds())
            del last_view[job_id]   # only pair once

    if not deltas_s:
        return None
    deltas_s.sort()
    n = len(deltas_s)
    mid = n // 2
    return deltas_s[mid] if n % 2 else (deltas_s[mid - 1] + deltas_s[mid]) / 2


def clear_all() -> int:
    """Wipe the events table. Returns rows deleted. Used by the 'Clear all
    events' button on Insights."""
    with db.tx() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
        conn.execute("DELETE FROM events")
    return int(row["n"])


# ── Internals ──

def _safe_json(raw: Any) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _parse_ts(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s.rstrip("Z"))
    except (TypeError, ValueError):
        return None
