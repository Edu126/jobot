"""Fixture test for core.bi.pulse.collect_signals AND REQ-031 leading signals.

Runs without pytest — invoke directly:
    .venv/bin/python tests/test_pulse_signals.py

Seeds a temp SQLite DB with rows landing IN, BEFORE, and AFTER the
7-day window, then asserts:
  - Only in-window rows are counted.
  - Every top-level section key is present with the expected shape.
  - Bounded lists (feedback message truncation, high-score dismissal
    detection, stuck-state cutoffs) behave.

REQ-031 additions:
  - core.events.PROFILE_GAP_VIEWED constant is defined.
  - core.bi.kpis._bucket returns the new leading-signal keys.
  - fleet_pulse._matrix() handles buckets missing the new keys (back-compat).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Make the repo root importable when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core import events as ev  # noqa: E402
from core.bi import pulse, kpis  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _seed(path: Path) -> dict:
    """Populate the DB with a mix of in-window and out-of-window rows."""
    db.init_db(path)

    now = datetime.utcnow()
    # Pin timestamps well inside / outside the 7-day window so any
    # slight drift between _seed() and collect_signals() can't flip a row.
    in_win = now - timedelta(days=2)
    older  = now - timedelta(days=10)      # before the window
    newer  = now + timedelta(days=1)       # future (shouldn't happen but excluded)
    stale_running = now - timedelta(hours=6)
    stalled_app = now - timedelta(days=14)

    with db.tx(path) as conn:
        # Events: 3 in-window, 1 in prev window, 1 in the future.
        for ts, typ, payload in [
            (in_win,              "page_view",       {"path": "/jobs"}),
            (in_win,              "job.detail_viewed", {"job_id": "j1", "score": 88}),
            (in_win,              "error",           {"where": "search", "msg": "boom"}),
            (older,               "page_view",       {"path": "/profile"}),
            (newer,               "page_view",       {"path": "/future"}),
        ]:
            conn.execute(
                "INSERT INTO events (ts_utc, type, payload_json) VALUES (?, ?, ?)",
                (_iso(ts), typ, json.dumps(payload)),
            )

        # Jobs: one first-seen in-window (surfaced), one older (not counted).
        for jid, first_seen in [("j1", in_win), ("j_old", older), ("j2", in_win)]:
            conn.execute(
                """INSERT INTO jobs (id, title, company, location, site, date_posted,
                                     job_url, description, is_remote, first_seen, last_seen)
                   VALUES (?, ?, ?, '', '', '', '', '', 0, ?, ?)""",
                (jid, f"Title {jid}", f"Co {jid}", _iso(first_seen), _iso(first_seen)),
            )

        # viewed_jobs: one in-window, one before.
        conn.execute("INSERT INTO viewed_jobs (job_id, viewed_at) VALUES (?, ?)",
                     ("j1", _iso(in_win)))
        conn.execute("INSERT INTO viewed_jobs (job_id, viewed_at) VALUES (?, ?)",
                     ("j_old", _iso(older)))

        # dismissed_jobs: dismiss a high-scoring job (j1) — should show up
        # in high_score_dismissed. Dismiss timing is unrestricted.
        conn.execute("INSERT INTO dismissed_jobs (job_id, dismissed_at) VALUES (?, ?)",
                     ("j1", _iso(in_win)))

        # applications:
        #   app1 — created in-window, applied in-window
        #   app2 — created older, applied older (excluded)
        #   app3 — created older, still "interested" (stalled candidate)
        conn.execute(
            """INSERT INTO applications
               (job_id, resume_id, status, applied_at, created_at, last_updated, notes)
               VALUES (?, NULL, 'applied', ?, ?, ?, '')""",
            ("j1", _iso(in_win), _iso(in_win), _iso(in_win)),
        )
        conn.execute(
            """INSERT INTO applications
               (job_id, resume_id, status, applied_at, created_at, last_updated, notes)
               VALUES (?, NULL, 'applied', ?, ?, ?, '')""",
            ("j_old", _iso(older), _iso(older), _iso(older)),
        )
        conn.execute(
            """INSERT INTO applications
               (job_id, resume_id, status, applied_at, created_at, last_updated, notes)
               VALUES (?, NULL, 'interested', NULL, ?, ?, '')""",
            ("j2", _iso(older), _iso(stalled_app)),
        )

        # resumes: two uploaded. Only r1 gets a job_scores row.
        conn.execute(
            """INSERT INTO resumes (filename, uploaded_at, source_format, parsed_json,
                                    raw_bytes, is_current)
               VALUES ('r1.pdf', ?, 'pdf', '{}', X'00', 1)""",
            (_iso(in_win),),
        )
        conn.execute(
            """INSERT INTO resumes (filename, uploaded_at, source_format, parsed_json,
                                    raw_bytes, is_current)
               VALUES ('r2.pdf', ?, 'pdf', '{}', X'00', 0)""",
            (_iso(in_win),),
        )

        # job_scores for r1 only — j1 (85, in-window), j_old (75, older),
        # j2 (60, in-window). r2 gets no scores → appears in unscored list.
        for resume_id, job_id, score, verdict, scored_at in [
            (1, "j1",    85, "strong",   in_win),
            (1, "j_old", 75, "possible", older),
            (1, "j2",    60, "possible", in_win),
        ]:
            conn.execute(
                """INSERT INTO job_scores
                   (resume_id, job_id, score, verdict, reasoning,
                    matched_json, gaps_json, model, scored_at)
                   VALUES (?, ?, ?, ?, '', '[]', '[]', 'test-model', ?)""",
                (resume_id, job_id, score, verdict, _iso(scored_at)),
            )

        # search_tasks: one stale-running (>1h old), one fresh-running (excluded).
        conn.execute(
            """INSERT INTO search_tasks
               (id, kind, status, message, started_at, updated_at, payload_json)
               VALUES ('stale', 'multi', 'running', 'stuck', ?, ?, '{}')""",
            (_iso(stale_running), _iso(stale_running)),
        )
        conn.execute(
            """INSERT INTO search_tasks
               (id, kind, status, message, started_at, updated_at, payload_json)
               VALUES ('fresh', 'multi', 'running', 'ok', ?, ?, '{}')""",
            (_iso(now), _iso(now)),
        )

        # gemini_usage: one row in-window.
        today = now.date().isoformat()
        conn.execute(
            """INSERT INTO gemini_usage
               (identity, model, day, calls, tokens_in, tokens_out)
               VALUES ('ip:1.2.3.4', 'gemini-2.0-flash', ?, 5, 1000, 2000)""",
            (today,),
        )

        # feedback: one in-window with a long message (tests truncation),
        # one before.
        long_msg = "x" * 500
        conn.execute(
            """INSERT INTO feedback (message, page_url, user_agent, identity, submitted_at)
               VALUES (?, '/jobs', 'ua', 'sid:abc', ?)""",
            (long_msg, _iso(in_win)),
        )
        conn.execute(
            """INSERT INTO feedback (message, page_url, user_agent, identity, submitted_at)
               VALUES ('old feedback', '/', 'ua', 'sid:xyz', ?)""",
            (_iso(older),),
        )

        # prior admin_report — period_end 8 days ago so it's *before* the
        # current 7-day window starts.
        prior_end = _iso(now - timedelta(days=8))
        prior_start = _iso(now - timedelta(days=15))
        conn.execute(
            """INSERT INTO admin_reports
               (generated_at, period_start, period_end, model, markdown,
                tokens_in, tokens_out)
               VALUES (?, ?, ?, 'gemini-2.0-flash', '# prior', 10, 20)""",
            (prior_end, prior_start, prior_end),
        )

    return {"now": now}


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pulse.db"
        _seed(path)
        sig = pulse.collect_signals(days=7, path=path)

    # Top-level shape
    for key in ("window", "engagement", "funnel", "match_quality",
                "stuck_states", "errors", "feedback", "prior_report"):
        _assert(key in sig, f"missing top-level key: {key}")

    # Window
    _assert(sig["window"]["days"] == 7, "window.days should be 7")
    _assert(sig["window"]["start"].endswith("Z"), "window.start should be ISO-Z")

    # Engagement: 3 in-window events, prev-window = 1
    eng = sig["engagement"]
    _assert(eng["total_events"] == 3,
            f"engagement.total_events expected 3, got {eng['total_events']}")
    _assert(eng["prev_window"]["total_events"] == 1,
            f"prev_window.total_events expected 1, got {eng['prev_window']['total_events']}")
    _assert(set(eng["events_by_type"]).issubset({"page_view", "job.detail_viewed", "error"}),
            f"unexpected event types: {list(eng['events_by_type'])}")
    _assert(eng["active_days"] >= 1, "should have >=1 active day")

    # Funnel — j1 & j2 surfaced in-window (j_old older); j1 viewed;
    # 2 apps created in-window (j1 applied, j2 stalled/interested);
    # 1 applied in-window; 1 dismissed in-window.
    fun = sig["funnel"]
    _assert(fun["jobs_surfaced"] == 2, f"funnel.jobs_surfaced expected 2, got {fun['jobs_surfaced']}")
    _assert(fun["jobs_viewed"] == 1, f"funnel.jobs_viewed expected 1, got {fun['jobs_viewed']}")
    _assert(fun["jobs_saved"] == 1,
            f"funnel.jobs_saved expected 1 (only app1 created in-window), got {fun['jobs_saved']}")
    _assert(fun["jobs_applied"] == 1,
            f"funnel.jobs_applied expected 1, got {fun['jobs_applied']}")
    _assert(fun["jobs_dismissed"] == 1,
            f"funnel.jobs_dismissed expected 1, got {fun['jobs_dismissed']}")

    # Match quality — 2 in-window scores (j1=85, j2=60); j1 is high-score AND dismissed.
    mq = sig["match_quality"]
    _assert(mq["total_scored"] == 2, f"match_quality.total_scored expected 2, got {mq['total_scored']}")
    _assert(mq["score_buckets"]["85-100"] == 1, f"85-100 bucket expected 1, got {mq['score_buckets']}")
    _assert(mq["score_buckets"]["50-69"] == 1, f"50-69 bucket expected 1, got {mq['score_buckets']}")
    _assert(mq["high_score_count"] == 1, f"high_score_count expected 1, got {mq['high_score_count']}")
    _assert(len(mq["high_score_dismissed"]) == 1,
            f"high_score_dismissed expected 1, got {mq['high_score_dismissed']}")
    _assert(mq["high_score_dismissed"][0]["job_id"] == "j1",
            "expected j1 as the dismissed high-score job")
    _assert(mq["high_score_dismiss_rate"] == 1.0,
            f"dismiss_rate expected 1.0, got {mq['high_score_dismiss_rate']}")

    # Stuck states
    ss = sig["stuck_states"]
    stuck_ids = [r["id"] for r in ss["search_tasks_stuck_running"]]
    _assert(stuck_ids == ["stale"], f"stuck tasks expected ['stale'], got {stuck_ids}")
    # Both j2 (interested, 14d) and j_old (applied, 10d) are >7d stale.
    # Ordered by last_updated ascending → oldest first.
    stalled_job_ids = [r["job_id"] for r in ss["applications_stalled_gt7d"]]
    _assert(stalled_job_ids == ["j2", "j_old"],
            f"stalled apps expected ['j2', 'j_old'], got {stalled_job_ids}")
    unscored = [r["filename"] for r in ss["resumes_never_scored"]]
    _assert(unscored == ["r2.pdf"], f"unscored resumes expected ['r2.pdf'], got {unscored}")

    # Errors
    err = sig["errors"]
    _assert(len(err["error_events"]) == 1, f"error_events expected 1, got {len(err['error_events'])}")
    _assert(err["error_events"][0]["payload"]["where"] == "search",
            "error payload should round-trip through json")
    _assert(isinstance(err["llm_disabled_now"], bool), "llm_disabled_now must be bool")
    _assert(len(err["gemini_usage"]) == 1, f"gemini_usage expected 1 row, got {len(err['gemini_usage'])}")
    _assert(err["gemini_usage"][0]["calls"] == 5, "gemini calls should aggregate")

    # Feedback — 1 in-window, message truncated to 300 chars + ellipsis.
    fb = sig["feedback"]
    _assert(len(fb) == 1, f"feedback expected 1 row, got {len(fb)}")
    _assert(len(fb[0]["message"]) <= 301, f"feedback message not truncated: {len(fb[0]['message'])}")
    _assert(fb[0]["message"].endswith("…"), "long feedback should end with ellipsis")
    _assert(fb[0]["identity"] == "sid:abc", "feedback identity round-trips")

    # Prior report pointer
    pr = sig["prior_report"]
    _assert(pr is not None, "expected a prior report row")
    _assert(pr["model"] == "gemini-2.0-flash", f"unexpected prior model: {pr}")

    # JSON-serializability guard — the whole dict has to survive json.dumps
    # since it goes into the Gemini prompt as text.
    json.dumps(sig)

    # ── REQ-031: leading-signal additions ─────────────────────────────────

    # 1. PROFILE_GAP_VIEWED constant exists and has the correct string value.
    _assert(hasattr(ev, "PROFILE_GAP_VIEWED"), "ev.PROFILE_GAP_VIEWED is missing")
    _assert(ev.PROFILE_GAP_VIEWED == "profile.gap_viewed",
            f"PROFILE_GAP_VIEWED value unexpected: {ev.PROFILE_GAP_VIEWED!r}")

    # 2. LEADING_STEPS constant is present and ordered correctly.
    _assert(hasattr(kpis, "LEADING_STEPS"), "kpis.LEADING_STEPS is missing")
    _assert(list(kpis.LEADING_STEPS[:5]) == ["search", "save", "tailor", "gap_viewed", "prep"],
            f"LEADING_STEPS order wrong: {kpis.LEADING_STEPS}")

    # 3. _bucket returns all leading-signal keys (with a real DB).
    with tempfile.TemporaryDirectory() as d2:
        path2 = Path(d2) / "leading.db"
        db.init_db(path2)
        now2 = datetime.utcnow()
        b_start = now2 - timedelta(days=7)
        # Seed gap_viewed + prep events inside the window.
        with db.tx(path2) as conn2:
            for ts, typ in [
                (now2 - timedelta(days=1), ev.PROFILE_GAP_VIEWED),
                (now2 - timedelta(days=2), ev.SEARCH_BROAD),
                (now2 - timedelta(days=2), "prep_session_created"),
            ]:
                conn2.execute(
                    "INSERT INTO events (ts_utc, type, payload_json) VALUES (?,?,?)",
                    ((ts.replace(microsecond=0).isoformat() + "Z"), typ, "{}"),
                )
        with db.connect(path2) as conn2:
            bucket = kpis._bucket(conn2, b_start, now2, "week")
        for key in ("search", "save", "tailor", "gap_viewed", "prep"):
            _assert(key in bucket, f"_bucket missing leading key: {key!r}")
        _assert(bucket["gap_viewed"] == 1,
                f"gap_viewed expected 1, got {bucket['gap_viewed']}")
        _assert(bucket["search"] == 1,
                f"search expected 1 (one SEARCH_BROAD), got {bucket['search']}")
        _assert(bucket["prep"] == 1,
                f"prep expected 1, got {bucket['prep']}")
        # REQ-031/ADR-039: intention (distinct active days) sits alongside
        # intensity (raw counts); distinct-days is never greater than raw.
        for key in ("search", "save", "tailor", "gap_viewed", "prep"):
            dkey = f"{key}_days"
            _assert(dkey in bucket, f"_bucket missing intention key: {dkey!r}")
            _assert(bucket[dkey] <= bucket[key],
                    f"{dkey} ({bucket[dkey]}) must be <= {key} ({bucket[key]})")
        _assert(bucket["search_days"] == 1,
                f"search_days expected 1 active day, got {bucket['search_days']}")

    # 4. fleet_pulse._matrix() tolerates buckets missing leading keys (old apps).
    import importlib.util, importlib
    _fp_path = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "fleet-pulse" / "fleet_pulse.py"
    spec = importlib.util.spec_from_file_location("fleet_pulse", _fp_path)
    fp_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fp_mod)

    # Old-app bucket: only legacy keys, no leading-signal keys.
    old_series = [{"label": "wk 01-01", "viewed": 5, "saved": 3, "applied": 1,
                   "tailored": 2, "heard_back": 0}]
    html_old = fp_mod._matrix(old_series)
    _assert("<table" in html_old, "matrix should return table HTML for old-app series")
    _assert("0" in html_old, "old-app bucket should render 0s for missing leading keys")

    # New-app bucket: all leading-signal keys present.
    new_series = [{"label": "wk 09-01", "search": 4, "save": 3, "tailor": 2,
                   "gap_viewed": 1, "prep": 0, "applied": 1, "heard_back": 0,
                   "viewed": 10, "saved": 3, "tailored": 2}]
    html_new = fp_mod._matrix(new_series)
    _assert("<table" in html_new, "matrix should return table HTML for new-app series")
    _assert("4" in html_new, "search count should appear in matrix HTML")

    # 5. Toggle (ADR-039): leading cells carry BOTH intention (data-days,
    #    shown by default) and intensity (data-raw).
    tog_series = [{"label": "wk 09-08", "search": 6, "search_days": 2,
                   "save": 0, "tailor": 0, "gap_viewed": 0, "prep": 0,
                   "applied": 0, "heard_back": 0}]
    html_tog = fp_mod._matrix(tog_series)
    _assert('class="lead" data-days="2" data-raw="6">2<' in html_tog,
            "leading cell must carry both values and display intention (days) by default")

    print("OK — all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
