"""Fixture test for core.bi.kpis.compute_phase0_kpis (REQ-026 / ADR-034).

Runs without pytest — invoke directly:
    .venv/bin/python tests/test_phase0_kpis.py

Seeds a temp SQLite DB with a deterministic story: activity anchored 30 days
back, returns in week 1 and week 4, two tailors (one downloaded), three
applications (two this week, one last week; two heard back, one positive), and
four scored jobs. Then asserts every KPI lands on its computed value.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core import events as ev  # noqa: E402
from core.bi import kpis  # noqa: E402
from core.matching import semantic_score as ss  # noqa: E402


NOW = datetime.utcnow().replace(microsecond=0)
ANCHOR = NOW - timedelta(days=30)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _seed(path: Path) -> None:
    db.init_db(path)
    rid = db.save_resume("r.docx", {"raw_text": "x"}, b"x", set_current=True, path=path)
    for jid in ("j1", "j2", "j3", "j4"):
        db.upsert_job({"id": jid, "title": jid, "company": "Co", "description": "d"}, path=path)

    db.save_scores(rid, [
        {"job_id": "j1", "score": 85, "verdict": "strong", "reasoning": "r", "matched": [], "gaps": [], "model": "t"},
        {"job_id": "j2", "score": 60, "verdict": "stretch", "reasoning": "r", "matched": [], "gaps": [], "model": "t"},
        {"job_id": "j3", "score": 90, "verdict": "strong", "reasoning": "r", "matched": [], "gaps": [], "model": "t"},
        {"job_id": "j4", "score": 40, "verdict": "weak", "reasoning": "r", "matched": [], "gaps": [], "model": "t"},
    ], "en", ss.PROMPT_VERSION, ss.SCORING_VERSION, path=path)

    def _e(conn, dt, type_, **payload):
        conn.execute("INSERT INTO events (ts_utc, type, payload_json) VALUES (?,?,?)",
                     (_iso(dt), type_, json.dumps(payload)))

    def _app(conn, job_id, status, applied_at):
        conn.execute(
            "INSERT INTO applications (job_id, resume_id, status, applied_at, created_at, last_updated) "
            "VALUES (?,?,?,?,?,?)",
            (job_id, rid, status, _iso(applied_at), _iso(applied_at), _iso(applied_at)))

    with db.tx(path) as conn:
        day9 = ANCHOR.replace(hour=9, minute=0, second=0, microsecond=0)
        _e(conn, day9,                          ev.PAGE_VIEW, path="/profile")
        _e(conn, day9 + timedelta(minutes=30),  ev.TAILOR_GENERATED, job_id="j1")
        _e(conn, day9 + timedelta(minutes=35),  ev.TAILOR_GENERATED, job_id="j2")
        _e(conn, day9 + timedelta(hours=1),     ev.TAILOR_RESUME_DOWNLOAD, job_id="j1")
        _e(conn, NOW - timedelta(days=22), ev.PAGE_VIEW, path="/jobs")   # week 1
        _e(conn, NOW - timedelta(days=1),  ev.PAGE_VIEW, path="/jobs")   # week 4 + current
        _app(conn, "j1", "interviewing", NOW - timedelta(days=1))        # this week, positive
        _app(conn, "j3", "rejected",     NOW - timedelta(days=2))        # this week, heard back
        _app(conn, "j2", "applied",      NOW - timedelta(days=9))        # last week
        # a status transition event so the time-series heard_back has timing
        _e(conn, NOW - timedelta(days=1), ev.APP_STATUS_CHANGED,
           to_status="interviewing", job_id="j1")


def _approx(a, b, tol=0.05) -> bool:
    return a is not None and abs(a - b) <= tol


def main() -> int:
    fails: list[str] = []

    def check(name, cond, detail=""):
        if not cond:
            fails.append(f"{name}: {detail}")

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "t.db"
        _seed(path)
        k = kpis.compute_phase0_kpis(now=NOW, path=path)

    g1 = k["g1_retention"]
    check("g1.w1", g1["w1_retained"] is True, g1)
    check("g1.w4", g1["w4_retained"] is True, g1)
    check("g1.current", g1["current_week_active"] is True, g1)
    check("g1.weeks", g1["weeks_since_anchor"] == 4, g1)

    g2 = k["g2_applications"]
    check("g2.this_week", g2["this_week"] == 2, g2)
    check("g2.last_week", g2["last_week"] == 1, g2)
    check("g2.delta", g2["delta"] == 1, g2)

    s1 = k["s1_activation"]
    check("s1.activated", s1["activated"] is True, s1)
    check("s1.session1", s1["activated_first_session"] is True, s1)
    check("s1.hours", _approx(s1["hours_to_activate"], 0.5), s1)

    s2 = k["s2_acceptance"]
    check("s2.generated", s2["generated"] == 2, s2)
    check("s2.downloaded", s2["downloaded"] == 1, s2)
    check("s2.rate", _approx(s2["acceptance_rate"], 0.5), s2)

    s3 = k["s3_score_trust"]
    check("s3.applied_with_score", s3["applied_with_score"] == 3, s3)
    check("s3.mean_applied", _approx(s3["mean_applied_score"], 78.3, 0.1), s3)
    check("s3.pct_high", _approx(s3["pct_applied_high"], 0.667, 0.01), s3)
    check("s3.mean_all", _approx(s3["mean_all_scored"], 68.8, 0.1), s3)

    o = k["outcome"]
    check("o.applied", o["applied"] == 3, o)
    check("o.heard_back", o["heard_back"] == 2, o)
    check("o.positive", o["positive"] == 1, o)
    check("o.response_rate", _approx(o["response_rate"], 0.667, 0.01), o)

    # Time-series (REQ-028 / ADR-036).
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ts.db"
        _seed(path)
        wk = kpis.compute_kpi_timeseries("week", 8, now=NOW, path=path)
        day = kpis.compute_kpi_timeseries("day", 21, now=NOW, path=path)

    check("ts.week_len", len(wk) == 8, len(wk))
    nb = wk[-1]  # newest week
    check("ts.newest_applied", nb["applied"] == 2, nb)
    check("ts.newest_saved", nb["saved"] == 2, nb)
    check("ts.newest_heard", nb["heard_back"] == 1, nb)
    check("ts.newest_tailored", nb["tailored"] == 0, nb)
    check("ts.newest_active", nb["active_days"] >= 1, nb)
    check("ts.sum_applied", sum(b["applied"] for b in wk) == 3, [b["applied"] for b in wk])
    check("ts.sum_tailored", sum(b["tailored"] for b in wk) == 2, [b["tailored"] for b in wk])
    check("ts.day_len", len(day) == 21, len(day))
    check("ts.day_sum_applied", sum(b["applied"] for b in day) == 3, [b["applied"] for b in day])

    # Empty DB → honest None/0, no crash.
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "empty.db"
        db.init_db(path)
        e = kpis.compute_phase0_kpis(now=NOW, path=path)
    check("empty.g1", e["g1_retention"]["w4_retained"] is None, e["g1_retention"])
    check("empty.s1", e["s1_activation"]["activated"] is None, e["s1_activation"])
    check("empty.g2", e["g2_applications"]["this_week"] == 0, e["g2_applications"])

    if fails:
        print("FAILURES:\n  " + "\n  ".join(fails))
        return 1
    print("ALL PHASE-0 KPI CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
