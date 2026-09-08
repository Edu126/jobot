"""Phase 0 KPIs — the 2 Gold + 3 support metrics, computed DETERMINISTICALLY
from the existing signal tables (REQ-026 / ADR-034).

These are the numbers that decide whether jobot is a business, so they are
never LLM-narrated — `/admin/pulse` renders this block live, above the Gemini
report. Pure reads: events, applications, job_scores. No writes, no network.

Definitions (from docs/product/milestones.md):
  G1  Weekly returning users — per-app weekly-active (single-tenant), with
      W1/W4 retention booleans anchored on first-ever activity.
  G2  Applications completed / week — applied_at in the window, vs prior window.
  S1  Activation — reached the first tailored artifact; whether in session 1
      (proxied as the same UTC day as first activity).
  S2  Artifact acceptance — of tailored jobs, how many were downloaded ("used").
  S3  Score trust — do applied jobs score higher than the average job seen?
Outcome (moat seed) — applications that got a response (moved past `applied`).

Every metric degrades honestly: not-enough-data returns None, not a fake 0.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core import db
from core import events as ev


# Reached-a-response statuses: the candidate heard back (rejected counts — it's
# still a response). interviewing/offer are the *positive* subset.
_HEARD_BACK = ("interviewing", "offer", "rejected")
_POSITIVE_OUTCOME = ("interviewing", "offer")
_HIGH_SCORE = 70            # the "high fit" threshold for S3 (verdict band edge)
_MAX_RETENTION_WEEKS = 12   # bound the weekly-active sparkline


def compute_phase0_kpis(now: Optional[datetime] = None, path: Path = db.DB_PATH) -> dict:
    """Return the Phase 0 KPI block. Shape-stable; values are numbers or None
    (None = not enough data yet — render an honest empty state, never a fake 0)."""
    now = now or datetime.utcnow()
    with db.connect(path) as conn:
        return {
            "computed_at": _iso(now),
            "g1_retention": _g1_retention(conn, now),
            "g2_applications": _g2_applications(conn, now),
            "s1_activation": _s1_activation(conn),
            "s2_acceptance": _s2_acceptance(conn),
            "s3_score_trust": _s3_score_trust(conn),
            "outcome": _outcome(conn),
        }


# ---------- G1 — weekly returning (retention) ----------

def _g1_retention(conn: sqlite3.Connection, now: datetime) -> dict:
    first = conn.execute("SELECT MIN(ts_utc) AS t FROM events").fetchone()["t"]
    if not first:
        return {"anchor_date": None, "weeks_since_anchor": None, "w1_retained": None,
                "w4_retained": None, "current_week_active": None, "weekly_active": []}

    anchor = _parse(first)
    weeks_since = max(0, (now - anchor).days // 7)

    def active_between(a: datetime, b: datetime) -> int:
        return conn.execute(
            "SELECT COUNT(DISTINCT substr(ts_utc,1,10)) AS n FROM events "
            "WHERE ts_utc >= ? AND ts_utc < ?",
            (_iso(a), _iso(b)),
        ).fetchone()["n"]

    def week_window(i: int) -> tuple[datetime, datetime]:
        return anchor + timedelta(days=7 * i), anchor + timedelta(days=7 * (i + 1))

    # W1 / W4 retention: any active day in that week AFTER the anchor week.
    # Only meaningful once that week has actually elapsed (else None).
    def retained(i: int) -> Optional[bool]:
        if weeks_since < i:
            return None
        a, b = week_window(i)
        return active_between(a, b) > 0

    weekly = []
    for i in range(min(weeks_since, _MAX_RETENTION_WEEKS) + 1):
        a, b = week_window(i)
        weekly.append({"week": i, "active_days": active_between(a, b)})

    return {
        "anchor_date": anchor.strftime("%Y-%m-%d"),
        "weeks_since_anchor": weeks_since,
        "w1_retained": retained(1),
        "w4_retained": retained(4),
        "current_week_active": active_between(now - timedelta(days=7), now) > 0,
        "weekly_active": weekly,
    }


# ---------- G2 — applications completed / week ----------

def _g2_applications(conn: sqlite3.Connection, now: datetime) -> dict:
    start = now - timedelta(days=7)
    prev = start - timedelta(days=7)

    def applied_between(a: datetime, b: datetime) -> int:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM applications "
            "WHERE applied_at IS NOT NULL AND applied_at >= ? AND applied_at < ?",
            (_iso(a), _iso(b)),
        ).fetchone()["n"]

    this_week = applied_between(start, now)
    last_week = applied_between(prev, start)
    return {"this_week": this_week, "last_week": last_week,
            "delta": this_week - last_week}


# ---------- S1 — activation ----------

def _s1_activation(conn: sqlite3.Connection) -> dict:
    first_ev = conn.execute("SELECT MIN(ts_utc) AS t FROM events").fetchone()["t"]
    first_tailor = conn.execute(
        "SELECT MIN(ts_utc) AS t FROM events WHERE type = ?", (ev.TAILOR_GENERATED,),
    ).fetchone()["t"]

    if not first_ev:
        return {"activated": None, "hours_to_activate": None,
                "activated_first_session": None}
    if not first_tailor:
        return {"activated": False, "hours_to_activate": None,
                "activated_first_session": False}

    fe, ft = _parse(first_ev), _parse(first_tailor)
    hours = round((ft - fe).total_seconds() / 3600, 1)
    return {
        "activated": True,
        "hours_to_activate": hours,
        # Session 1 proxy: first tailor on the same UTC calendar day as first touch.
        "activated_first_session": first_ev[:10] == first_tailor[:10],
    }


# ---------- S2 — artifact acceptance (used with minimal edits, proxied) ----------

def _s2_acceptance(conn: sqlite3.Connection) -> dict:
    generated = _distinct_jobs(conn, (ev.TAILOR_GENERATED,))
    downloaded = _distinct_jobs(conn, (ev.TAILOR_RESUME_DOWNLOAD, ev.TAILOR_CL_DOWNLOAD))
    if not generated:
        return {"generated": 0, "downloaded": 0, "acceptance_rate": None}
    used = len(generated & downloaded)
    return {"generated": len(generated), "downloaded": used,
            "acceptance_rate": round(used / len(generated), 3)}


def _distinct_jobs(conn: sqlite3.Connection, types: tuple[str, ...]) -> set[str]:
    placeholders = _qmarks(types)
    rows = conn.execute(
        f"SELECT DISTINCT json_extract(payload_json,'$.job_id') AS job_id "
        f"FROM events WHERE type IN ({placeholders}) "
        f"AND json_extract(payload_json,'$.job_id') IS NOT NULL",
        types,
    ).fetchall()
    return {r["job_id"] for r in rows}


# ---------- S3 — score trust ----------

def _s3_score_trust(conn: sqlite3.Connection) -> dict:
    # Latest score per job (a job may be re-scored across résumés/versions).
    applied_scores = [r["score"] for r in conn.execute(
        """SELECT js.score AS score
           FROM applications a
           JOIN (SELECT job_id, MAX(scored_at) AS mx FROM job_scores GROUP BY job_id) last
                ON last.job_id = a.job_id
           JOIN job_scores js ON js.job_id = last.job_id AND js.scored_at = last.mx
           WHERE a.applied_at IS NOT NULL""",
    ).fetchall()]
    baseline = conn.execute("SELECT AVG(score) AS a FROM job_scores").fetchone()["a"]

    if not applied_scores:
        return {"applied_with_score": 0, "mean_applied_score": None,
                "pct_applied_high": None, "mean_all_scored": _round(baseline)}
    n = len(applied_scores)
    return {
        "applied_with_score": n,
        "mean_applied_score": round(sum(applied_scores) / n, 1),
        "pct_applied_high": round(sum(1 for s in applied_scores if s >= _HIGH_SCORE) / n, 3),
        "mean_all_scored": _round(baseline),
    }


# ---------- Outcome (moat seed) ----------

def _outcome(conn: sqlite3.Connection) -> dict:
    applied = conn.execute(
        "SELECT COUNT(*) AS n FROM applications WHERE applied_at IS NOT NULL"
    ).fetchone()["n"]
    heard = _count_status(conn, _HEARD_BACK)
    positive = _count_status(conn, _POSITIVE_OUTCOME)
    return {
        "applied": applied,
        "heard_back": heard,
        "positive": positive,
        "response_rate": round(heard / applied, 3) if applied else None,
    }


def _count_status(conn: sqlite3.Connection, statuses: tuple[str, ...]) -> int:
    placeholders = _qmarks(statuses)
    return conn.execute(
        f"SELECT COUNT(*) AS n FROM applications WHERE status IN ({placeholders})",
        statuses,
    ).fetchone()["n"]


# ---------- utils ----------

def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _qmarks(xs) -> str:
    """SQL placeholder string for a WHERE ... IN (...) over `xs`."""
    return ",".join("?" * len(xs))


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s.rstrip("Z"))


def _round(v) -> Optional[float]:
    return round(v, 1) if v is not None else None


# ---------- time-series (REQ-028 / ADR-036) ----------

# The funnel columns of the per-user evolution matrix, in order.
FUNNEL_STEPS = ("viewed", "saved", "applied", "tailored", "heard_back")


def compute_kpi_timeseries(
    granularity: str = "week",
    n: int = 8,
    now: Optional[datetime] = None,
    path: Path = db.DB_PATH,
) -> list[dict]:
    """Per-bucket funnel counts, oldest bucket first (REQ-028). `granularity`
    is 'week' (7-day buckets) or 'day'. Each bucket:
      {start, label, active_days, viewed, saved, applied, tailored, heard_back}
    Computed on demand from raw tables (ADR-036) — exact and retroactive."""
    now = now or datetime.utcnow()
    span = timedelta(days=1 if granularity == "day" else 7)
    with db.connect(path) as conn:
        series = []
        for i in range(n):
            b_end = now - span * i
            b_start = b_end - span
            series.append(_bucket(conn, b_start, b_end, granularity))
    series.reverse()   # oldest first
    return series


def _bucket(conn: sqlite3.Connection, a: datetime, b: datetime, gran: str) -> dict:
    ai, bi = _iso(a), _iso(b)

    def one(sql: str, *params) -> int:
        return conn.execute(sql, params).fetchone()["n"]

    label = a.strftime("%m-%d") if gran == "day" else f"wk {a.strftime('%m-%d')}"
    return {
        "start": a.strftime("%Y-%m-%d"),
        "label": label,
        "active_days": one(
            "SELECT COUNT(DISTINCT substr(ts_utc,1,10)) n FROM events "
            "WHERE ts_utc>=? AND ts_utc<?", ai, bi),
        "viewed": one(
            "SELECT COUNT(*) n FROM viewed_jobs WHERE viewed_at>=? AND viewed_at<?", ai, bi),
        "saved": one(
            "SELECT COUNT(*) n FROM applications WHERE created_at>=? AND created_at<?", ai, bi),
        "applied": one(
            "SELECT COUNT(*) n FROM applications "
            "WHERE applied_at IS NOT NULL AND applied_at>=? AND applied_at<?", ai, bi),
        "tailored": one(
            "SELECT COUNT(DISTINCT json_extract(payload_json,'$.job_id')) n FROM events "
            "WHERE type=? AND ts_utc>=? AND ts_utc<?", ev.TAILOR_GENERATED, ai, bi),
        "heard_back": one(
            "SELECT COUNT(*) n FROM events WHERE type=? AND ts_utc>=? AND ts_utc<? "
            f"AND json_extract(payload_json,'$.to_status') IN ({_qmarks(_HEARD_BACK)})",
            ev.APP_STATUS_CHANGED, ai, bi, *_HEARD_BACK),
    }


# ---------- CLI ----------

def main(argv: Optional[list[str]] = None) -> int:
    """Print the Phase 0 KPIs as one JSON line — the `fleet-pulse` skill runs
    this over `fly ssh` per app (ADR-035). With `--series`, emit
    {kpis, series_week, series_day} so the fleet view gets snapshot + trends in
    one round-trip (ADR-036). One line so SSH stdout parses cleanly."""
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="python -m core.bi.kpis")
    ap.add_argument("--series", action="store_true",
                    help="Also emit weekly + daily time-series (REQ-028).")
    args = ap.parse_args(argv)

    if args.series:
        out = {
            "kpis": compute_phase0_kpis(),
            "series_week": compute_kpi_timeseries("week", 8),
            "series_day": compute_kpi_timeseries("day", 21),
        }
    else:
        out = compute_phase0_kpis()
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
