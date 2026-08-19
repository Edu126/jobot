"""BI pulse — weekly Gemini-authored markdown reports.

`collect_signals(days)` reads the 6 signal tables (events, jobs,
applications, viewed_jobs, dismissed_jobs, feedback) plus the
supporting tables (job_scores, search_tasks, gemini_usage,
resumes, admin_reports) for a rolling window and returns a compact
JSON-serializable dict. The dict is deliberately shape-stable —
downstream code hands it to Gemini as prompt context, so a stable
schema keeps prompt engineering cheap.

The dict is bounded (top-N truncation everywhere, hard caps on lists)
so a busy week can't blow the prompt-token budget.

`build_prompt(signals)` wraps the dict into a self-contained prompt.
`generate_report(days)` runs the full pipeline: collect → prompt →
Gemini (via `generate_json`, unwrapping `{"markdown": "..."}`) →
persist to `admin_reports`. `main()` is the CLI entrypoint the weekly
GH Actions cron drives via `fly ssh console`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core import db


_LOG = logging.getLogger(__name__)


# Bounds so a chatty week can't balloon the report prompt.
_MAX_TOP_EVENT_TYPES = 20
_MAX_STALLED_APPS = 25
_MAX_UNSCORED_RESUMES = 10
_MAX_RUNNING_TASKS = 15
_MAX_ERROR_EVENTS = 25
_MAX_FEEDBACK_ROWS = 40
_FEEDBACK_MSG_CHARS = 300
_MAX_TOP_DISMISSED = 15
_STALE_RUNNING_TASK_HOURS = 1
_STALLED_APP_DAYS = 7


def collect_signals(days: int = 7, path: Path = db.DB_PATH) -> dict:
    """Read the signal tables for the last `days` days into a bounded dict.

    Shape is stable across calls; downstream prompt construction depends
    on the top-level keys. Numeric values are ints/floats; timestamps
    are ISO-8601 UTC strings; lists are pre-sorted where a sensible
    order exists (most recent / highest score first)."""
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)

    start_iso = _iso(start)
    end_iso = _iso(now)
    prev_start_iso = _iso(prev_start)

    with db.connect(path) as conn:
        return {
            "window": {
                "days": int(days),
                "start": start_iso,
                "end": end_iso,
            },
            "engagement": _engagement(conn, start_iso, end_iso, prev_start_iso),
            "funnel": _funnel(conn, start_iso, end_iso),
            "match_quality": _match_quality(conn, start_iso, end_iso),
            "stuck_states": _stuck_states(conn, now),
            "errors": _errors(conn, start_iso, end_iso),
            "feedback": _feedback(conn, start_iso, end_iso),
            "prior_report": _prior_report(conn, start_iso),
        }


# ---------- section builders ----------

def _engagement(
    conn: sqlite3.Connection,
    start_iso: str,
    end_iso: str,
    prev_start_iso: str,
) -> dict:
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE ts_utc >= ? AND ts_utc < ?",
        (start_iso, end_iso),
    ).fetchone()["n"]

    by_type_rows = conn.execute(
        """SELECT type, COUNT(*) AS n FROM events
           WHERE ts_utc >= ? AND ts_utc < ?
           GROUP BY type ORDER BY n DESC LIMIT ?""",
        (start_iso, end_iso, _MAX_TOP_EVENT_TYPES),
    ).fetchall()
    by_type = {r["type"]: int(r["n"]) for r in by_type_rows}

    by_day_rows = conn.execute(
        """SELECT substr(ts_utc, 1, 10) AS day, COUNT(*) AS n FROM events
           WHERE ts_utc >= ? AND ts_utc < ?
           GROUP BY day ORDER BY day""",
        (start_iso, end_iso),
    ).fetchall()
    by_day = [{"day": r["day"], "count": int(r["n"])} for r in by_day_rows]

    active_days = conn.execute(
        """SELECT COUNT(DISTINCT substr(ts_utc, 1, 10)) AS n FROM events
           WHERE ts_utc >= ? AND ts_utc < ?""",
        (start_iso, end_iso),
    ).fetchone()["n"]

    prev_total = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE ts_utc >= ? AND ts_utc < ?",
        (prev_start_iso, start_iso),
    ).fetchone()["n"]

    return {
        "total_events": int(total),
        "active_days": int(active_days),
        "events_by_type": by_type,
        "events_by_day": by_day,
        "prev_window": {"total_events": int(prev_total)},
    }


def _funnel(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> dict:
    surfaced = conn.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE first_seen >= ? AND first_seen < ?",
        (start_iso, end_iso),
    ).fetchone()["n"]

    viewed = conn.execute(
        "SELECT COUNT(*) AS n FROM viewed_jobs WHERE viewed_at >= ? AND viewed_at < ?",
        (start_iso, end_iso),
    ).fetchone()["n"]

    dismissed = conn.execute(
        "SELECT COUNT(*) AS n FROM dismissed_jobs WHERE dismissed_at >= ? AND dismissed_at < ?",
        (start_iso, end_iso),
    ).fetchone()["n"]

    # Saved = any application row created in the window (initial status
    # `interested` counts as saved; a same-window promote to `applied`
    # still originated as a save).
    saved = conn.execute(
        "SELECT COUNT(*) AS n FROM applications WHERE created_at >= ? AND created_at < ?",
        (start_iso, end_iso),
    ).fetchone()["n"]

    applied = conn.execute(
        """SELECT COUNT(*) AS n FROM applications
           WHERE applied_at IS NOT NULL AND applied_at >= ? AND applied_at < ?""",
        (start_iso, end_iso),
    ).fetchone()["n"]

    return {
        "jobs_surfaced": int(surfaced),
        "jobs_viewed": int(viewed),
        "jobs_saved": int(saved),
        "jobs_applied": int(applied),
        "jobs_dismissed": int(dismissed),
    }


def _match_quality(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> dict:
    rows = conn.execute(
        """SELECT js.job_id, js.score, js.verdict, js.scored_at,
                  j.title, j.company
           FROM job_scores js JOIN jobs j ON j.id = js.job_id
           WHERE js.scored_at >= ? AND js.scored_at < ?""",
        (start_iso, end_iso),
    ).fetchall()

    buckets = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}
    verdicts: dict[str, int] = {}
    high_scores: list[dict] = []   # score >= 80 in this window
    for r in rows:
        s = int(r["score"])
        if s < 50:
            buckets["0-49"] += 1
        elif s < 70:
            buckets["50-69"] += 1
        elif s < 85:
            buckets["70-84"] += 1
        else:
            buckets["85-100"] += 1
        v = r["verdict"] or "unknown"
        verdicts[v] = verdicts.get(v, 0) + 1
        if s >= 80:
            high_scores.append({
                "job_id": r["job_id"],
                "title": r["title"],
                "company": r["company"],
                "score": s,
            })

    # High-score dismissal rate — any dismissed_jobs row for a job that
    # scored >= 80 in the window. Dismissal timestamp isn't restricted:
    # the score being in-window is what matters (we're measuring the
    # quality of *this window's* recommendations).
    high_dismissed = []
    if high_scores:
        placeholders = ",".join("?" * len(high_scores))
        ids = [h["job_id"] for h in high_scores]
        dismissed_rows = conn.execute(
            f"SELECT job_id FROM dismissed_jobs WHERE job_id IN ({placeholders})",
            ids,
        ).fetchall()
        dismissed_ids = {r["job_id"] for r in dismissed_rows}
        for h in high_scores:
            if h["job_id"] in dismissed_ids:
                high_dismissed.append(h)

    dismiss_rate = (
        round(len(high_dismissed) / len(high_scores), 3)
        if high_scores else 0.0
    )

    high_dismissed_sorted = sorted(
        high_dismissed, key=lambda x: x["score"], reverse=True
    )[:_MAX_TOP_DISMISSED]

    return {
        "total_scored": len(rows),
        "score_buckets": buckets,
        "verdict_counts": verdicts,
        "high_score_count": len(high_scores),
        "high_score_dismissed": high_dismissed_sorted,
        "high_score_dismiss_rate": dismiss_rate,
    }


def _stuck_states(conn: sqlite3.Connection, now: datetime) -> dict:
    running_cutoff = _iso(now - timedelta(hours=_STALE_RUNNING_TASK_HOURS))
    stalled_cutoff = _iso(now - timedelta(days=_STALLED_APP_DAYS))

    running = conn.execute(
        """SELECT id, kind, status, message, started_at, updated_at
           FROM search_tasks
           WHERE status = 'running' AND updated_at < ?
           ORDER BY updated_at LIMIT ?""",
        (running_cutoff, _MAX_RUNNING_TASKS),
    ).fetchall()

    stalled = conn.execute(
        """SELECT a.id, a.job_id, a.status, a.last_updated,
                  j.title, j.company
           FROM applications a JOIN jobs j ON j.id = a.job_id
           WHERE a.status IN ('interested', 'applied', 'interviewing')
             AND a.last_updated < ?
           ORDER BY a.last_updated LIMIT ?""",
        (stalled_cutoff, _MAX_STALLED_APPS),
    ).fetchall()

    # Uploaded resumes with zero job_scores rows. Small table (dozens of
    # rows at most), so a left-join scan is fine.
    unscored = conn.execute(
        """SELECT r.id, r.filename, r.uploaded_at, r.is_current
           FROM resumes r
           LEFT JOIN job_scores js ON js.resume_id = r.id
           WHERE js.resume_id IS NULL
           ORDER BY r.uploaded_at DESC LIMIT ?""",
        (_MAX_UNSCORED_RESUMES,),
    ).fetchall()

    return {
        "search_tasks_stuck_running": [dict(r) for r in running],
        "applications_stalled_gt7d": [dict(r) for r in stalled],
        "resumes_never_scored": [dict(r) for r in unscored],
    }


def _errors(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> dict:
    def _sample(event_type: str) -> list[dict]:
        rows = conn.execute(
            """SELECT ts_utc, type, payload_json FROM events
               WHERE ts_utc >= ? AND ts_utc < ? AND type = ?
               ORDER BY ts_utc DESC LIMIT ?""",
            (start_iso, end_iso, event_type, _MAX_ERROR_EVENTS),
        ).fetchall()
        return [
            {
                "ts_utc": r["ts_utc"],
                "type": r["type"],
                "payload": _safe_json(r["payload_json"]),
            }
            for r in rows
        ]

    errors = _sample("error")
    search_blocked = _sample("search.blocked")
    extract_failed = _sample("extract.failed")

    gemini_rows = conn.execute(
        """SELECT day, model, SUM(calls) AS calls,
                  SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out
           FROM gemini_usage
           WHERE day >= ? AND day <= ?
           GROUP BY day, model ORDER BY day, model""",
        (start_iso[:10], end_iso[:10]),
    ).fetchall()

    return {
        "error_events": errors,
        "search_blocked": search_blocked,
        "extract_failed": extract_failed,
        "llm_disabled_now": _read_llm_disabled(),
        "gemini_usage": [
            {
                "day": r["day"],
                "model": r["model"],
                "calls": int(r["calls"] or 0),
                "tokens_in": int(r["tokens_in"] or 0),
                "tokens_out": int(r["tokens_out"] or 0),
            }
            for r in gemini_rows
        ],
    }


def _feedback(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> list[dict]:
    rows = conn.execute(
        """SELECT id, message, screenshot_path, page_url, user_agent,
                  identity, submitted_at
           FROM feedback
           WHERE submitted_at >= ? AND submitted_at < ?
           ORDER BY submitted_at DESC LIMIT ?""",
        (start_iso, end_iso, _MAX_FEEDBACK_ROWS),
    ).fetchall()
    out = []
    for r in rows:
        msg = (r["message"] or "").strip()
        if len(msg) > _FEEDBACK_MSG_CHARS:
            msg = msg[:_FEEDBACK_MSG_CHARS].rstrip() + "…"
        out.append({
            "id": int(r["id"]),
            "message": msg,
            "identity": r["identity"] or "",
            "page_url": r["page_url"] or "",
            "submitted_at": r["submitted_at"],
            "has_screenshot": bool(r["screenshot_path"]),
        })
    return out


def _prior_report(conn: sqlite3.Connection, current_start_iso: str) -> Optional[dict]:
    """Metadata for the most recent report whose period_end is at or before
    the current window's start — the "last week" pointer used for the
    Δ comparison. Body is intentionally omitted (the prompt gets only
    what's needed to say 'we last reported through X')."""
    row = conn.execute(
        """SELECT id, generated_at, period_start, period_end, model
           FROM admin_reports
           WHERE period_end <= ?
           ORDER BY period_end DESC LIMIT 1""",
        (current_start_iso,),
    ).fetchone()
    return dict(row) if row else None


# ---------- utils ----------

def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _safe_json(raw: Any) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _read_llm_disabled() -> bool:
    """Snapshot of the LLM_DISABLED env var at call time. Mirrors
    `core.feature_flags.is_llm_disabled` semantics without importing
    (keeps this module dependency-light for the CLI entrypoint)."""
    return (os.environ.get("LLM_DISABLED") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


# ---------- prompt construction ----------

# The 6 fixed headings the report must contain, in order. Spec-locked —
# the /admin/pulse view and the "Δ from last week" comparison both
# assume this structure.
REPORT_HEADINGS = [
    "1. Engagement",
    "2. Funnel",
    "3. Match quality",
    "4. Stuck states",
    "5. Errors + kill-switches",
    "6. Feedback themes",
]


def build_prompt(signals: dict) -> str:
    """Assemble the full Gemini prompt for a pulse report.

    Response contract: JSON `{"markdown": "..."}` — we ask for JSON so
    the same `generate_json` fallback chain (retry, quota-aware model
    hopping) works; the caller unwraps to plain markdown before persist.

    Language: the markdown body honors the user's output-language
    setting via `language_instruction`. JSON field names stay English.
    """
    # Import here so this module stays importable in test / no-app
    # contexts (tests/test_pulse_signals.py doesn't need settings).
    from core.settings import get_output_language, language_instruction

    lang_line = language_instruction(get_output_language())
    signals_json = json.dumps(signals, ensure_ascii=False, indent=2, default=str)

    delta_line = (
        "- End with a **Δ from last week** section calling out what "
        "shifted vs the prior report window (`prior_report` in the "
        "signals). Focus on directional changes (engagement up/down, "
        "new stuck states, new feedback themes) — not exhaustive diffs."
        if signals.get("prior_report")
        else "- Omit the **Δ from last week** section: no prior report exists yet."
    )

    return f"""{lang_line}

You are the BI analyst for a personal job-search app used by a handful of real users. You have one week of raw signals (below, as JSON) and must produce a concise weekly pulse report as markdown.

RESPONSE FORMAT — respond with valid JSON:
{{"markdown": "<the full report as a markdown string>"}}

The markdown MUST use these six H2 headings, in this order, exactly:
## {REPORT_HEADINGS[0]}
## {REPORT_HEADINGS[1]}
## {REPORT_HEADINGS[2]}
## {REPORT_HEADINGS[3]}
## {REPORT_HEADINGS[4]}
## {REPORT_HEADINGS[5]}

Per-section guidance:
- **Engagement**: use `engagement.total_events`, `events_by_type`, `events_by_day`, `active_days`. Compare to `prev_window.total_events` for week-over-week. Call out which pages/actions dominate and whether activity is trending up or down.
- **Funnel**: walk `funnel` as surfaced → viewed → saved → applied. Identify the biggest drop as a percentage. Mention dismissals if meaningful.
- **Match quality**: use `match_quality.score_buckets`, `verdict_counts`, and `high_score_dismiss_rate`. If high-score jobs are being dismissed, list a few from `high_score_dismissed` — that's a bad signal worth flagging.
- **Stuck states**: enumerate anything in `stuck_states` — running search tasks that never finished, applications frozen >7d, resumes uploaded but never scored. If all three are empty, say so in one line; don't invent problems.
- **Errors + kill-switches**: summarize `errors.error_events`, `search_blocked`, `extract_failed`. Note `llm_disabled_now` if true. Include `gemini_usage` totals (calls, tokens).
- **Feedback themes**: group `feedback` rows by topic. Include 1-2 direct quotes per theme (truncate each quote to 120 chars) and note the identity (e.g. `sid:abc` or `ip:1.2.3.4`) so we can follow up per-user. If `feedback` is empty, say "No feedback this window." — do not invent themes.

{delta_line}

Style: terse, factual, no filler. Numbers over adjectives. Use bullet lists inside sections. Do NOT wrap the markdown in code fences. Do NOT include any commentary outside the JSON object.

SIGNALS:
```json
{signals_json}
```
"""


# ---------- report generation ----------

def generate_report(
    days: int = 7,
    *,
    api_key: Optional[str] = None,
    path: Path = db.DB_PATH,
) -> dict:
    """Full pipeline: collect signals → prompt Gemini → persist to
    `admin_reports`. Returns the saved row dict (via `get_pulse_report`).

    Raises `GeminiError` / `QuotaExhaustedError` from `generate_json`
    when the LLM path fails — the CLI catches and exits non-zero so
    GH Actions surfaces a red run.
    """
    from core.llm.gemini import GeminiClient, GeminiError, resolve_api_key
    from core.llm import usage as llm_usage

    signals = collect_signals(days=days, path=path)
    prompt = build_prompt(signals)

    key = resolve_api_key(api_key)
    if not key:
        raise GeminiError(
            "No Gemini API key — set GOOGLE_API_KEY or pass --api-key."
        )

    # Bind a synthetic identity so per-identity accounting works from
    # the cron. Without it, `check_and_charge` skips the daily cap
    # (see core/llm/usage.py:83) — accounting is still nice to have.
    token = llm_usage.set_identity("cron:pulse")
    try:
        client = GeminiClient(api_key=key)
        raw = client.generate_json(prompt)
    finally:
        llm_usage.reset_identity(token)

    markdown = _unwrap_markdown(raw)
    model = client.last_model_used or "unknown"
    tokens_in, tokens_out = _last_call_tokens(client, model)

    report_id = db.save_pulse_report(
        period_start=signals["window"]["start"],
        period_end=signals["window"]["end"],
        model=model,
        markdown=markdown,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        path=path,
    )
    return db.get_pulse_report(report_id, path=path) or {}


def _unwrap_markdown(raw: Any) -> str:
    """Pull the markdown string out of the model's JSON envelope.
    Tolerates a bare string (some models return plain text even when
    asked for JSON) and a couple of common alternative key names."""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("markdown", "report", "content"):
            v = raw.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    # Last-ditch: serialize whatever we got so we don't lose the run.
    return json.dumps(raw, ensure_ascii=False, indent=2)


def _last_call_tokens(client, model: str) -> tuple[int, int]:
    """Best-effort token read for the last successful call. The client
    doesn't expose usage_metadata directly; usage.record_tokens has
    already persisted them to `gemini_usage`. Read them back from the
    cron identity's row for today."""
    day = datetime.utcnow().strftime("%Y-%m-%d")
    with db.connect() as conn:
        row = conn.execute(
            """SELECT tokens_in, tokens_out FROM gemini_usage
               WHERE identity = 'cron:pulse' AND model = ? AND day = ?""",
            (model, day),
        ).fetchone()
    if not row:
        return 0, 0
    return int(row["tokens_in"] or 0), int(row["tokens_out"] or 0)


# ---------- CLI ----------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m core.bi.pulse",
        description="Generate a BI pulse report from local signal tables.",
    )
    parser.add_argument("--days", type=int, default=7,
                        help="Rolling window in days (default: 7).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Collect signals and print the prompt; skip Gemini + DB write.")
    parser.add_argument("--api-key", default=None,
                        help="Override the Gemini API key (else GOOGLE_API_KEY).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    signals = collect_signals(days=args.days)

    if args.dry_run:
        print("=== SIGNALS ===")
        print(json.dumps(signals, ensure_ascii=False, indent=2, default=str))
        print()
        print("=== PROMPT ===")
        print(build_prompt(signals))
        return 0

    try:
        row = generate_report(days=args.days, api_key=args.api_key)
    except Exception as exc:   # noqa: BLE001 — CLI needs a clean exit path
        _LOG.error("pulse generation failed: %s", exc)
        return 1

    print(f"Saved report id={row.get('id')} "
          f"model={row.get('model')} "
          f"tokens_in={row.get('tokens_in')} "
          f"tokens_out={row.get('tokens_out')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
