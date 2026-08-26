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
# REQ-011 / ADR-010 instrumentation — TTFJ / TTFS / search completion.
# `submitted` fires at task creation; `discovery_done` when scrape+dedupe
# finish (payload carries `duration_ms` + `jobs_found` + `cache_key`);
# `score_batch_done` fires once per LLM batch return (payload carries
# `duration_ms`, `batch_size`, `remaining_after`). Aggregation lives in
# whatever query we write when we actually want to look — no dashboard
# code lands with the instrumentation itself.
SEARCH_SUBMITTED       = "search.submitted"
SEARCH_DISCOVERY_DONE  = "search.discovery_done"
SEARCH_SCORE_BATCH     = "search.score_batch_done"
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
# Scraper blocked / rate-limited by a specific job board (IP block, 429,
# Cloudflare challenge, etc). Instrumented so we notice patterns before
# they degrade the search UX — e.g. LinkedIn blocking us 3 days in a row
# means it's time to think about a proxy or headless approach.
SEARCH_BLOCKED         = "search.blocked"
# A URL-import extraction attempt failed at a specific step of the pipeline
# (adapter fetch, JSON-LD parse, or LLM extraction). Payload carries the
# adapter name so silent rot of an ATS adapter shows up in the log before a
# user reports garbage output.
EXTRACT_FAILED         = "extract.failed"


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


def week_hour_heatmap(days: int = 14) -> list[list[int]]:
    """7×24 grid of event counts. Row 0 = Monday, row 6 = Sunday.
    Col 0 = 00:00 UTC, col 23 = 23:00 UTC. Fills sparsely from the log.
    Used by the Journey page's proper calendar-style heatmap (vs the
    old single 24-bar version)."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT ts_utc FROM events WHERE ts_utc >= ?",
            (since,),
        ).fetchall()
    grid = [[0] * 24 for _ in range(7)]
    for r in rows:
        ts = _parse_ts(r["ts_utc"])
        if not ts:
            continue
        # Python weekday: Monday=0, Sunday=6 — matches what we want
        grid[ts.weekday()][ts.hour] += 1
    return grid


def recent_activity(limit: int = 25) -> list[dict]:
    """Latest events for the timeline widget on Journey. Returns richly-
    labeled rows so the template can render icon + text without cross-referencing."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT ts_utc, type, payload_json FROM events ORDER BY ts_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        payload = _safe_json(r["payload_json"])
        out.append({
            "ts_utc": r["ts_utc"],
            "type": r["type"],
            "payload": payload,
            "label": _humanize_event(r["type"], payload),
            "icon": _icon_for(r["type"]),
        })
    return out


def _humanize_event(type_: str, payload: dict) -> str:
    """Convert (event_type, payload) into a one-line human sentence for the
    activity timeline. Keeps the timeline scannable — no raw event codes."""
    if type_ == SEARCH_BROAD:
        queries = payload.get("queries") or []
        n = payload.get("result_count", 0)
        if queries:
            return f"Ran search: {', '.join(queries[:2])}{'…' if len(queries) > 2 else ''} — {n} results"
        return f"Ran a broad search — {n} results"
    if type_ == SEARCH_URL_IMPORT:
        src = payload.get("source", "link")
        manual = " (pasted)" if payload.get("used_manual") else ""
        return f"Imported a job from {src}{manual}"
    if type_ == JOB_DETAIL_VIEWED:
        v = payload.get("verdict") or "no-score"
        s = payload.get("score")
        return f"Viewed a job — {v}{f' · {s}' if s else ''}"
    if type_ == JOB_SAVED:
        return f"Saved a job as {payload.get('status', 'interested')}"
    if type_ == JOB_UNSAVED:
        return "Removed a saved job"
    if type_ == TAILOR_GENERATED:
        level = payload.get("level", "tailored")
        delta = payload.get("delta")
        if delta is not None:
            sign = "+" if delta >= 0 else ""
            return f"Generated a {level} tailor — score {sign}{delta}"
        return f"Generated a {level} tailor"
    if type_ == TAILOR_RESUME_DOWNLOAD:
        return "Downloaded tailored resume"
    if type_ == TAILOR_CL_DOWNLOAD:
        return "Downloaded cover letter"
    if type_ == APP_STATUS_CHANGED:
        fr = payload.get("from_status", "?")
        to = payload.get("to_status", "?")
        return f"Moved an application: {fr} → {to}"
    if type_ == RESUME_UPLOADED:
        return f"Uploaded a resume: {payload.get('filename', 'resume')}"
    if type_ == PAGE_VIEW:
        return f"Opened {payload.get('path', 'a page')}"
    return type_.replace(".", " · ").replace("_", " ")


def _icon_for(type_: str) -> str:
    """Phosphor icon name (no ph-thin prefix) for the timeline row."""
    return {
        SEARCH_BROAD: "ph-magnifying-glass",
        SEARCH_URL_IMPORT: "ph-link",
        JOB_DETAIL_VIEWED: "ph-eye",
        JOB_SAVED: "ph-heart",
        JOB_UNSAVED: "ph-heart-break",
        TAILOR_GENERATED: "ph-sparkle",
        TAILOR_RESUME_DOWNLOAD: "ph-download-simple",
        TAILOR_CL_DOWNLOAD: "ph-download-simple",
        APP_STATUS_CHANGED: "ph-arrow-right",
        RESUME_UPLOADED: "ph-upload-simple",
        PAGE_VIEW: "ph-browser",
    }.get(type_, "ph-circle")


def observations(days: int = 30) -> list[dict]:
    """Auto-generated one-line observations from the log. Non-judgmental,
    factual. Returns [] when there isn't enough data to say anything useful.
    Each observation has {tone, text} — tone maps to a color on the UI."""
    if total_events() < 5:
        return []

    obs: list[dict] = []
    counts = counts_by_type_last_week()

    # Most active day-of-week over the window
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        dow_rows = conn.execute(
            "SELECT ts_utc FROM events WHERE ts_utc >= ?",
            (since,),
        ).fetchall()
    if dow_rows:
        dow_buckets = [0] * 7
        for r in dow_rows:
            ts = _parse_ts(r["ts_utc"])
            if ts:
                dow_buckets[ts.weekday()] += 1
        if max(dow_buckets) > 0 and sum(dow_buckets) >= 10:
            best_dow = dow_buckets.index(max(dow_buckets))
            day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][best_dow]
            obs.append({"tone": "info", "text": f"You're most active on {day_name}s."})

    # Tailoring cadence
    tailors_wk = counts.get(TAILOR_GENERATED, 0)
    if tailors_wk >= 5:
        obs.append({"tone": "success", "text": f"Solid week — {tailors_wk} resumes tailored."})
    elif tailors_wk == 0 and counts.get(JOB_DETAIL_VIEWED, 0) > 0:
        obs.append({"tone": "warn", "text": "You've been browsing but haven't tailored anything yet — try one this week."})

    # Streak: how many days-in-a-row ending today
    streak = _current_streak_days()
    if streak >= 3:
        obs.append({"tone": "success", "text": f"{streak}-day streak. Keep the momentum."})

    # Median time-to-download context
    m = median_time_to_download_seconds(days=days)
    if m is not None:
        if m < 300:
            obs.append({"tone": "success", "text": "You're fast — typically under 5 minutes from opening a job to a tailored resume."})
        elif m > 1800:
            obs.append({"tone": "info", "text": "You take time on each application — median 30+ min from open to download."})

    # Funnel drop-off
    f = funnel_last_month()
    if f["saved"] > 10 and f["applied"] < f["saved"] * 0.3:
        obs.append({"tone": "warn", "text": f"You've saved {f['saved']} jobs but only applied to {f['applied']}. Anything blocking?"})

    return obs


def this_week_hero_stats() -> dict:
    """The 3 numbers + 1 context line that anchor the Journey hero.

    Returns:
        {
          "jobs_viewed": int,
          "tailored":    int,     # distinct tailor generations
          "applied":     int,     # status transitions to applied this week
          "streak_days": int,     # consecutive days ending today with events
          "most_active_dow": str, # day name over the last 30d ("" if not enough data)
          "period_label": "This week",
        }
    """
    counts = counts_by_type_last_week()

    # "applied" for the week from event log — status-changed events to `applied`
    since = (datetime.utcnow() - timedelta(days=7)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        applied_row = conn.execute(
            """SELECT COUNT(*) AS n FROM events
               WHERE ts_utc >= ? AND type = ?
                 AND json_extract(payload_json, '$.to_status') = 'applied'""",
            (since, APP_STATUS_CHANGED),
        ).fetchone()

        # Day-of-week popularity over the last 30d — enough sample to be meaningful
        since_30 = (datetime.utcnow() - timedelta(days=30)).isoformat(timespec="seconds") + "Z"
        dow_rows = conn.execute(
            "SELECT ts_utc FROM events WHERE ts_utc >= ?",
            (since_30,),
        ).fetchall()

    dow_buckets = [0] * 7
    for r in dow_rows:
        ts = _parse_ts(r["ts_utc"])
        if ts:
            dow_buckets[ts.weekday()] += 1

    most_active = ""
    if sum(dow_buckets) >= 10:
        best = dow_buckets.index(max(dow_buckets))
        most_active = ["Monday", "Tuesday", "Wednesday", "Thursday",
                       "Friday", "Saturday", "Sunday"][best]

    return {
        "jobs_viewed": counts.get(JOB_DETAIL_VIEWED, 0),
        "tailored": counts.get(TAILOR_GENERATED, 0),
        "applied": int(applied_row["n"]) if applied_row else 0,
        "streak_days": _current_streak_days(),
        "most_active_dow": most_active,
        "period_label": "This week",
    }


def monthly_calendar(year: int, month: int) -> dict:
    """GitHub-contributions-style grid for a specific calendar month (UTC).

    Returns:
        {
          "year": int,
          "month": int,               # 1-12
          "month_name": "August",
          "weeks": [[cell, ...], ...],  # 5-6 weeks, 7 cells each (Mon-Sun)
          "max_count": int,           # for intensity scaling
          "total": int,               # events that month
          "prev": {"year": Y, "month": M},
          "next": {"year": Y, "month": M},
        }
    Each cell is either None (day belongs to prev/next month, blank) or
    { "day": int, "count": int, "iso": "YYYY-MM-DD" }.
    """
    import calendar
    if not (1 <= month <= 12):
        month = datetime.utcnow().month
        year = datetime.utcnow().year

    # Month boundaries
    from datetime import date as _date
    first_day = _date(year, month, 1)
    _, last_day_num = calendar.monthrange(year, month)
    last_day = _date(year, month, last_day_num)

    # Fetch this month's events
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT substr(ts_utc, 1, 10) AS day, COUNT(*) AS n "
            "FROM events WHERE substr(ts_utc, 1, 10) BETWEEN ? AND ? "
            "GROUP BY day",
            (first_day.isoformat(), last_day.isoformat()),
        ).fetchall()
    per_day = {r["day"]: int(r["n"]) for r in rows}

    # Build the week grid — Monday-first calendar layout (matches Wealthsimple
    # / Notion convention). Leading + trailing blank cells for days that spill
    # into adjacent months.
    cal = calendar.Calendar(firstweekday=0)   # Monday = 0
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        row = []
        for d in week:
            if d.month != month:
                row.append(None)
            else:
                iso = d.isoformat()
                row.append({
                    "day": d.day,
                    "count": per_day.get(iso, 0),
                    "iso": iso,
                })
        weeks.append(row)

    max_count = max((c["count"] for w in weeks for c in w if c), default=0)
    total = sum(per_day.values())

    # Prev/next month for the nav arrows
    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year
    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year

    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "weeks": weeks,
        "max_count": max_count,
        "total": total,
        "prev": {"year": prev_year, "month": prev_month},
        "next": {"year": next_year, "month": next_month},
    }


def _current_streak_days() -> int:
    """Consecutive days ending today (UTC) with at least one event."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT substr(ts_utc, 1, 10) AS day FROM events ORDER BY day DESC LIMIT 60"
        ).fetchall()
    if not rows:
        return 0
    from datetime import date as _date
    today = _date.today()
    streak = 0
    for i, r in enumerate(rows):
        expected = today - timedelta(days=i)
        try:
            actual = _date.fromisoformat(r["day"])
        except ValueError:
            break
        if actual == expected:
            streak += 1
        else:
            break
    return streak


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
