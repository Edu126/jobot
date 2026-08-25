"""SQLite persistence for resumes, jobs, and applications.

Single-user, local. Stdlib sqlite3 only — no SQLAlchemy.

Schema is created lazily by init_db() at app startup. Foreign keys are
enforced per-connection.

Conventions:
- Datetimes stored as ISO-8601 UTC strings (sqlite has no native datetime).
- Booleans stored as INTEGER 0/1.
- All write operations are wrapped in transactions via the `tx()`
  context manager.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobot.db"


# ---------- schema ----------

SCHEMA_VERSION = 13

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resumes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    filename     TEXT NOT NULL,
    uploaded_at  TEXT NOT NULL,
    source_format TEXT,
    parsed_json  TEXT NOT NULL,
    raw_bytes    BLOB,
    is_current   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_resumes_current ON resumes(is_current);

CREATE TABLE IF NOT EXISTS jobs (
    id                 TEXT PRIMARY KEY,
    title              TEXT NOT NULL,
    company            TEXT NOT NULL,
    location           TEXT,
    site               TEXT,
    date_posted        TEXT,
    job_url            TEXT,
    job_url_direct     TEXT,          -- v6: direct company career URL (skips the board)
    description        TEXT,
    is_remote          INTEGER NOT NULL DEFAULT 0,
    min_salary         REAL,
    max_salary         REAL,
    detected_language  TEXT,
    french_required    INTEGER NOT NULL DEFAULT 0,
    first_seen         TEXT NOT NULL,
    last_seen          TEXT NOT NULL
);
-- v6: add job_url_direct if the column doesn't exist (idempotent for existing DBs)
-- SQLite doesn't support IF NOT EXISTS on ADD COLUMN, so init_db() handles this
-- separately after CREATE TABLE runs.

CREATE TABLE IF NOT EXISTS applications (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id                   TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id                INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    status                   TEXT NOT NULL,
    applied_at               TEXT,
    created_at               TEXT NOT NULL,
    last_updated             TEXT NOT NULL,
    notes                    TEXT,
    tailoring_level          TEXT,
    tailored_resume_json     TEXT,
    tailored_cover_letter    TEXT,
    UNIQUE(job_id)
);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);

CREATE TABLE IF NOT EXISTS job_scores (
    resume_id     INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    job_id        TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    lang          TEXT NOT NULL DEFAULT '',
    score         INTEGER NOT NULL,
    verdict       TEXT NOT NULL,
    reasoning     TEXT NOT NULL,
    matched_json  TEXT NOT NULL,
    gaps_json     TEXT NOT NULL,
    model         TEXT NOT NULL,
    scored_at     TEXT NOT NULL,
    PRIMARY KEY (resume_id, job_id, lang)
);
CREATE INDEX IF NOT EXISTS idx_job_scores_resume ON job_scores(resume_id);

CREATE TABLE IF NOT EXISTS saved_searches (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    query          TEXT NOT NULL,
    location       TEXT NOT NULL,
    hours_old      INTEGER NOT NULL DEFAULT 168,
    results_wanted INTEGER NOT NULL DEFAULT 30,
    distance       INTEGER NOT NULL DEFAULT 50,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_searches_order ON saved_searches(sort_order);

CREATE TABLE IF NOT EXISTS suggested_queries (
    resume_id     INTEGER PRIMARY KEY REFERENCES resumes(id) ON DELETE CASCADE,
    queries_json  TEXT NOT NULL,
    generated_at  TEXT NOT NULL
);

-- One-shot LLM read of a resume, generated on upload/switch and cached
-- (keyed by resume_id, no expiry — a new upload gets a new id, so the
-- cache is naturally invalidated on content change). Bundles 3 things
-- from a single call since they all need the same resume-text context:
--   role_label          — 2-5 word field/role guess ("AEC / BIM Coordination")
--   first_impression    — one-sentence honest gut-check, complements the
--                          deterministic ATS score with a qualitative read
--   suggestions_json    — [{"section": "languages", "reason": "..."}], only
--                          for STANDARD sections the candidate doesn't have
--                          (see core.resume.anomalies.missing_sections) that
--                          are judged actually worth adding for their field/
--                          market — not a generic "you're missing X" checklist
-- NOT named "profile_insights" — that name is taken by the local activity-
-- analytics feature (events table, /profile/insights route). This is a
-- distinct, LLM-generated, per-resume artifact.
CREATE TABLE IF NOT EXISTS resume_ai_summary (
    resume_id         INTEGER PRIMARY KEY REFERENCES resumes(id) ON DELETE CASCADE,
    role_label        TEXT,
    first_impression  TEXT,
    suggestions_json  TEXT NOT NULL DEFAULT '[]',
    generated_at      TEXT NOT NULL
);

-- Analytics — append-only event log. Never leaves this SQLite file.
-- Used by the Insights view on Profile to visualize activity.
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc       TEXT NOT NULL,
    type         TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events(ts_utc);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);

-- v7: durable state for background multi-search + Expand workers. Replaces
-- the in-memory `state.search_tasks` dict so tasks survive Fly's auto-stop
-- machine cycling and process restarts.
--
--   status : queued | running | done | failed
--   payload_json : {queries: [...], location: "..."} for the initial request
--   result_url   : /jobs/results/{cache_key} when done; NULL otherwise
--   message      : last-known human status line for the polling UI
--   error        : populated only on status=failed
CREATE TABLE IF NOT EXISTS search_tasks (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL DEFAULT 'multi',   -- 'multi' | 'expand'
    status       TEXT NOT NULL,
    message      TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    result_url   TEXT,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_search_tasks_updated ON search_tasks(updated_at);

-- v8: per-identity daily accounting for Gemini calls. Enforces a per-user
-- (per-IP today, per user_id post-auth) cap on LLM spend so a cost-bomb
-- attacker can't run us dry in an afternoon. Also feeds the admin UI
-- (planned) with usage stats.
--
--   identity : IP address today; user_id string post-auth
--   day      : YYYY-MM-DD UTC — rolls over at UTC midnight
--   calls    : number of successful generate_json calls
--   tokens_* : cumulative token counters if the SDK reports them; else 0
--
-- Primary key on (identity, model, day) so accounting is a single UPSERT.
CREATE TABLE IF NOT EXISTS gemini_usage (
    identity   TEXT NOT NULL,
    model      TEXT NOT NULL,
    day        TEXT NOT NULL,
    calls      INTEGER NOT NULL DEFAULT 0,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (identity, model, day)
);
CREATE INDEX IF NOT EXISTS idx_gemini_usage_day ON gemini_usage(day);

-- v8: SlowAPI SQLite-backed storage — persists rate-limit counters across
-- Fly `auto_stop_machines` cycling. Without persistence, an attacker
-- pacing requests to force machine sleep resets the in-memory limit
-- store on every wake-up.
--
--   key    : the SlowAPI-computed key (usually "{identity}/{limit}/{window}")
--   expiry : Unix seconds when this counter should be considered zero
CREATE TABLE IF NOT EXISTS rate_limits (
    key    TEXT PRIMARY KEY,
    count  INTEGER NOT NULL DEFAULT 0,
    expiry INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_limits_expiry ON rate_limits(expiry);

-- v9: per-job "viewed" state. A card is marked viewed when the user has
-- kept the detail pane open for >3 seconds (see the client-side timer in
-- pages/jobs_results.html) — the "I've actually read this" signal, not
-- "I accidentally clicked it once." Persists globally per job_id so a
-- job that appears in multiple searches shows viewed everywhere.
--
-- No user_id yet; when auth ships this becomes viewed_jobs(user_id, job_id).
CREATE TABLE IF NOT EXISTS viewed_jobs (
    job_id     TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    viewed_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_viewed_jobs_at ON viewed_jobs(viewed_at);

-- v10: per-job "dismissed" state — the user's "not interested; don't
-- surface this again" signal. Wired to the swipe-left gesture on mobile
-- and (later) an explicit dismiss button in the desktop detail pane.
-- Distinct from "not saved" (the neutral state) — dismissal is active
-- disinterest; the fresh view and default filters hide these.
--
-- Undo is a delete: POST /jobs/undismiss/{id} removes the row.
CREATE TABLE IF NOT EXISTS dismissed_jobs (
    job_id        TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    dismissed_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dismissed_jobs_at ON dismissed_jobs(dismissed_at);

-- v11: user feedback captured via the floating widget in base.html.
-- Every submission carries the free-text message, optional screenshot
-- of the page at the moment of feedback, the page URL / UA for
-- context, and the rate-limit identity (sid: cookie or IP) so the
-- BI agent can attribute themes per user.
--
-- Screenshots persist as PNGs under data/feedback/{id}.png; the DB
-- keeps only the path pointer to keep the table small.
CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message         TEXT NOT NULL,
    screenshot_path TEXT,
    page_url        TEXT,
    user_agent      TEXT,
    identity        TEXT,
    submitted_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_submitted ON feedback(submitted_at);

-- v12: generated BI pulse reports. One row per Gemini-authored weekly
-- markdown summary; rendered by /admin/pulse. Kept small — markdown
-- only, no source data (that lives in the signal tables and can be
-- re-queried). period_start/period_end bound the analysis window so
-- the "Δ from last week" comparison can find the prior report cleanly.
CREATE TABLE IF NOT EXISTS admin_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at  TEXT NOT NULL,
    period_start  TEXT NOT NULL,
    period_end    TEXT NOT NULL,
    model         TEXT NOT NULL,
    markdown      TEXT NOT NULL,
    tokens_in     INTEGER NOT NULL DEFAULT 0,
    tokens_out    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_admin_reports_generated ON admin_reports(generated_at);
"""


# Seeded on first init if the table is empty. User can edit/delete/add from Profile.
_DEFAULT_SAVED_SEARCHES = [
    {"name": "BIM Coordinator / Modeler",
     "query": "BIM coordinator",
     "location": "Ottawa, Ontario, Canada",
     "hours_old": 168, "results_wanted": 30, "distance": 50},
    {"name": "Construction Estimator",
     "query": "construction estimator",
     "location": "Ottawa, Ontario, Canada",
     "hours_old": 168, "results_wanted": 30, "distance": 50},
    {"name": "Junior Project Coordinator",
     "query": "junior project coordinator construction",
     "location": "Ottawa, Ontario, Canada",
     "hours_old": 168, "results_wanted": 30, "distance": 50},
]


VALID_STATUSES = (
    "interested",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
)


# ---------- connection ----------

def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path = DB_PATH) -> None:
    with connect(path) as conn:
        conn.executescript(_SCHEMA_SQL)
        # v6 migration: add job_url_direct if missing on an existing DB.
        # SQLite lacks `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, so we
        # sniff pragma first.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "job_url_direct" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN job_url_direct TEXT")

        # v13 migration: `lang` joins the job_scores PK so cached gaps
        # /reasoning don't leak across UI-language changes. Old rows keep
        # lang='' — they simply age out as fresh runs write current-lang
        # rows next to them. Cheap (a handful of KB of zombie rows) and
        # non-destructive vs. wiping; also lets a user who flips back to
        # a prior language re-hit their old cache.
        scores_cols = {r["name"] for r in conn.execute("PRAGMA table_info(job_scores)").fetchall()}
        if scores_cols and "lang" not in scores_cols:
            conn.executescript("""
                CREATE TABLE job_scores_new (
                    resume_id    INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
                    job_id       TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    lang         TEXT NOT NULL DEFAULT '',
                    score        INTEGER NOT NULL,
                    verdict      TEXT NOT NULL,
                    reasoning    TEXT NOT NULL,
                    matched_json TEXT NOT NULL,
                    gaps_json    TEXT NOT NULL,
                    model        TEXT NOT NULL,
                    scored_at    TEXT NOT NULL,
                    PRIMARY KEY (resume_id, job_id, lang)
                );
                INSERT INTO job_scores_new
                    (resume_id, job_id, lang, score, verdict, reasoning,
                     matched_json, gaps_json, model, scored_at)
                SELECT resume_id, job_id, '', score, verdict, reasoning,
                       matched_json, gaps_json, model, scored_at
                FROM job_scores;
                DROP TABLE job_scores;
                ALTER TABLE job_scores_new RENAME TO job_scores;
                CREATE INDEX IF NOT EXISTS idx_job_scores_resume ON job_scores(resume_id);
            """)

        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    _seed_saved_searches_if_empty(path)


def _seed_saved_searches_if_empty(path: Path) -> None:
    """No-op as of v0.5. Kept as a hook for legacy paths.

    Previously seeded 3 AEC defaults for a single-user AEC assumption.
    That noise pollutes multi-user deploys (Melissa in sales gets Mehran's
    BIM queries as chips). Users now start with an empty saved list; chips
    on Jobs are AI-generated from their resume via /jobs/quick-fill on first
    visit. Their saved_searches table fills up organically as they save
    searches they liked."""
    return
    # Legacy code below — unreachable, preserved so a future re-seed can
    # cherry-pick from the pattern if needed.
    with tx(path) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM saved_searches").fetchone()
        if int(count["n"]) > 0:
            return
        now = _now()
        for i, s in enumerate(_DEFAULT_SAVED_SEARCHES):
            conn.execute(
                """INSERT INTO saved_searches
                   (name, query, location, hours_old, results_wanted, distance, sort_order, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (s["name"], s["query"], s["location"], s["hours_old"],
                 s["results_wanted"], s["distance"], i, now),
            )


@contextmanager
def tx(path: Path = DB_PATH):
    """Transactional connection — commits on success, rolls back on error."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ---------- resumes ----------

def save_resume(
    filename: str,
    parsed: dict,
    raw_bytes: bytes,
    *,
    set_current: bool = True,
    path: Path = DB_PATH,
) -> int:
    """Insert a resume and (optionally) mark it as the current one."""
    with tx(path) as conn:
        cur = conn.execute(
            """INSERT INTO resumes
               (filename, uploaded_at, source_format, parsed_json, raw_bytes, is_current)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (
                filename,
                _now(),
                parsed.get("source_format", ""),
                json.dumps(parsed, ensure_ascii=False),
                raw_bytes,
            ),
        )
        new_id = int(cur.lastrowid)
        if set_current:
            conn.execute("UPDATE resumes SET is_current = 0")
            conn.execute("UPDATE resumes SET is_current = 1 WHERE id = ?", (new_id,))
        return new_id


def list_resumes(path: Path = DB_PATH) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute(
            """SELECT id, filename, uploaded_at, source_format, is_current
               FROM resumes ORDER BY uploaded_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_resume(resume_id: int, path: Path = DB_PATH) -> Optional[dict]:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE id = ?", (resume_id,)
        ).fetchone()
        return _resume_row_to_dict(row) if row else None


def get_current_resume(path: Path = DB_PATH) -> Optional[dict]:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE is_current = 1 ORDER BY uploaded_at DESC LIMIT 1"
        ).fetchone()
        return _resume_row_to_dict(row) if row else None


def set_current_resume(resume_id: int, path: Path = DB_PATH) -> None:
    with tx(path) as conn:
        conn.execute("UPDATE resumes SET is_current = 0")
        conn.execute("UPDATE resumes SET is_current = 1 WHERE id = ?", (resume_id,))


def delete_resume(resume_id: int, path: Path = DB_PATH) -> None:
    with tx(path) as conn:
        conn.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))


def update_resume_contact(resume_id: int, contact: dict, path: Path = DB_PATH) -> None:
    """Merge user-confirmed contact fields into parsed_json.contact. Only
    keys present in `contact` are overwritten — callers pass the full form
    (including blanks) so this is a full replace of the contact sub-dict,
    not a sparse patch."""
    with tx(path) as conn:
        row = conn.execute(
            "SELECT parsed_json FROM resumes WHERE id = ?", (resume_id,)
        ).fetchone()
        if not row:
            return
        parsed = json.loads(row["parsed_json"])
        parsed["contact"] = contact
        conn.execute(
            "UPDATE resumes SET parsed_json = ? WHERE id = ?",
            (json.dumps(parsed, ensure_ascii=False), resume_id),
        )


def update_resume_parsed(resume_id: int, parsed: dict, path: Path = DB_PATH) -> None:
    """Replace the full parsed_json for a resume. Used by the LLM regeneration
    pass — caller has already produced a validated, complete parsed dict."""
    with tx(path) as conn:
        conn.execute(
            "UPDATE resumes SET parsed_json = ? WHERE id = ?",
            (json.dumps(parsed, ensure_ascii=False), resume_id),
        )


def _resume_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["parsed"] = json.loads(d.pop("parsed_json"))
    d["is_current"] = bool(d["is_current"])
    return d


# ---------- jobs ----------

def upsert_job(job: dict, path: Path = DB_PATH) -> None:
    """Insert if new, update last_seen if existing."""
    now = _now()
    with tx(path) as conn:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE id = ?", (job["id"],)
        ).fetchone()
        if existing:
            # Update job_url_direct too — if the second scrape finally
            # revealed it (jobspy sometimes returns it on retry).
            conn.execute(
                """UPDATE jobs SET title=?, company=?, location=?, description=?,
                   detected_language=?, french_required=?, job_url_direct=?, last_seen=?
                   WHERE id=?""",
                (
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("description", ""),
                    job.get("detected_language", ""),
                    1 if job.get("french_required") else 0,
                    job.get("job_url_direct") or None,
                    now,
                    job["id"],
                ),
            )
        else:
            conn.execute(
                """INSERT INTO jobs (
                    id, title, company, location, site, date_posted, job_url,
                    job_url_direct, description, is_remote, min_salary, max_salary,
                    detected_language, french_required, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job["id"],
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("site", ""),
                    job.get("date_posted", ""),
                    job.get("job_url", ""),
                    job.get("job_url_direct") or None,
                    job.get("description", ""),
                    1 if job.get("is_remote") else 0,
                    job.get("min_salary"),
                    job.get("max_salary"),
                    job.get("detected_language", ""),
                    1 if job.get("french_required") else 0,
                    now,
                    now,
                ),
            )


def upsert_jobs(jobs: Iterable[dict], path: Path = DB_PATH) -> int:
    """Bulk upsert. Returns count written."""
    n = 0
    for job in jobs:
        upsert_job(job, path)
        n += 1
    return n


def get_job(job_id: str, path: Path = DB_PATH) -> Optional[dict]:
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def mark_viewed(job_id: str, path: Path = DB_PATH) -> None:
    """Mark a job as viewed. Idempotent — updates viewed_at on repeat calls
    so the most recent view timestamp wins (useful for "recently viewed"
    lists we might add later)."""
    with tx(path) as conn:
        conn.execute(
            "INSERT INTO viewed_jobs (job_id, viewed_at) VALUES (?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET viewed_at = excluded.viewed_at",
            (job_id, _now()),
        )


def get_viewed_ids(job_ids: Iterable[str], path: Path = DB_PATH) -> set[str]:
    """Return the subset of `job_ids` the user has viewed. Batch query so
    the results page can render viewed chips in one SQL round-trip."""
    ids = list(job_ids)
    if not ids:
        return set()
    with connect(path) as conn:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT job_id FROM viewed_jobs WHERE job_id IN ({placeholders})",
            ids,
        ).fetchall()
    return {r["job_id"] for r in rows}


def mark_dismissed(job_id: str, path: Path = DB_PATH) -> None:
    """Mark a job as dismissed ("not interested"). Idempotent."""
    with tx(path) as conn:
        conn.execute(
            "INSERT INTO dismissed_jobs (job_id, dismissed_at) VALUES (?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET dismissed_at = excluded.dismissed_at",
            (job_id, _now()),
        )


def unmark_dismissed(job_id: str, path: Path = DB_PATH) -> None:
    """Undo dismissal. Used by the toast Undo button after a swipe-left."""
    with tx(path) as conn:
        conn.execute("DELETE FROM dismissed_jobs WHERE job_id = ?", (job_id,))


def save_feedback(
    *,
    message: str,
    page_url: str = "",
    user_agent: str = "",
    identity: str = "",
    screenshot_bytes: Optional[bytes] = None,
    screenshot_ext: str = "png",
    path: Path = DB_PATH,
) -> int:
    """Persist a feedback submission. Screenshot bytes are written to a
    file next to the DB; only the relative path is stored on the row.

    `screenshot_ext` is the file extension without the dot ("png",
    "jpg", "webp"). Widened 2026-08-21 from PNG-only when we swapped
    html2canvas for a native file picker — the user's file could be
    any image type.

    Returns the new feedback id.

    Both the INSERT and the screenshot_path UPDATE run inside ONE
    transaction (was two, /simplify pass 2026-08-21). Bonus: if the
    file write raises after the INSERT, the whole tx rolls back — no
    orphan row pointing at a non-existent file.
    """
    with tx(path) as conn:
        cur = conn.execute(
            "INSERT INTO feedback (message, page_url, user_agent, identity, submitted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (message.strip(), page_url, user_agent, identity, _now()),
        )
        new_id = int(cur.lastrowid)

        if screenshot_bytes:
            shot_dir = path.parent / "feedback"
            shot_dir.mkdir(parents=True, exist_ok=True)
            ext = (screenshot_ext or "png").lstrip(".").lower() or "png"
            rel_path = f"feedback/{new_id}.{ext}"
            (shot_dir / f"{new_id}.{ext}").write_bytes(screenshot_bytes)
            conn.execute(
                "UPDATE feedback SET screenshot_path = ? WHERE id = ?",
                (rel_path, new_id),
            )
    return new_id


def list_feedback(limit: int = 50, path: Path = DB_PATH) -> list[dict]:
    """Most recent feedback first. For the BI agent + a future admin
    review view."""
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT id, message, screenshot_path, page_url, user_agent, "
            "identity, submitted_at FROM feedback "
            "ORDER BY submitted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_dismissed_ids(job_ids: Iterable[str], path: Path = DB_PATH) -> set[str]:
    """Batch lookup of dismissed status for a set of job_ids."""
    ids = list(job_ids)
    if not ids:
        return set()
    with connect(path) as conn:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT job_id FROM dismissed_jobs WHERE job_id IN ({placeholders})",
            ids,
        ).fetchall()
    return {r["job_id"] for r in rows}


def get_applied_job_ids(job_ids: Iterable[str], path: Path = DB_PATH) -> set[str]:
    """Batch lookup — which of the given job_ids has a corresponding
    application row in status='applied' or beyond (interviewing / offer).

    Added 2026-08-21 for the "Applied" badge on job cards. Same pattern
    as get_viewed_ids / get_dismissed_ids so state stays cheap when the
    same job re-surfaces in a later scrape (application row survives
    scrape cycles — the `applications` table has UNIQUE(job_id))."""
    ids = list(job_ids)
    if not ids:
        return set()
    with connect(path) as conn:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT job_id FROM applications "
            f"WHERE job_id IN ({placeholders}) "
            f"  AND status IN ('applied', 'interviewing', 'offer')",
            ids,
        ).fetchall()
    return {r["job_id"] for r in rows}


def get_jobs(job_ids: Iterable[str], path: Path = DB_PATH) -> list[dict]:
    """Batch-load full job rows for a set of ids. Order matches `job_ids`
    (rows missing from the DB are silently skipped — treat as a stale cache
    pointer referencing a job that got pruned).

    Used by cache.load() to resolve pointer files into full Job dicts."""
    ids = list(job_ids)
    if not ids:
        return []
    with connect(path) as conn:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def get_first_seen_batch(job_ids: Iterable[str], path: Path = DB_PATH) -> dict[str, str]:
    """Batch lookup of first_seen timestamps for a set of job_ids. Used by
    the enrichment pass on top-matches / results — one query beats N."""
    job_ids = list(job_ids)
    if not job_ids:
        return {}
    with connect(path) as conn:
        placeholders = ",".join("?" * len(job_ids))
        rows = conn.execute(
            f"SELECT id, first_seen FROM jobs WHERE id IN ({placeholders})",
            job_ids,
        ).fetchall()
        return {r["id"]: r["first_seen"] for r in rows}


# ---------- applications ----------

def create_or_get_application(
    job_id: str,
    status: str = "interested",
    resume_id: Optional[int] = None,
    path: Path = DB_PATH,
) -> int:
    """Create an application row for this job, or return the existing one's id."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    now = _now()
    with tx(path) as conn:
        existing = conn.execute(
            "SELECT id FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            """INSERT INTO applications
               (job_id, resume_id, status, applied_at, created_at, last_updated, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                resume_id,
                status,
                now if status == "applied" else None,
                now,
                now,
                "",
            ),
        )
        return int(cur.lastrowid)


def mark_job_applied(
    job_id: str,
    resume_id: Optional[int] = None,
    path: Path = DB_PATH,
) -> int:
    """One-shot "user says they applied to this job."

    Two cases handled inside one tx:
      1. No application row yet → INSERT with status='applied'.
      2. Application row exists in 'interested' → UPDATE to 'applied'.
      3. Row already in 'applied' / 'interviewing' / 'offer' → no-op
         (don't downgrade — e.g. don't clobber interview stage).

    Returns the application id. Application rows survive scrape cycles
    (UNIQUE on job_id) so this state persists even if the same job
    re-surfaces in a later search — the "Applied" badge shows next time.

    Added 2026-08-21 for the "Mark as Applied" button, prompted by
    Mehran feedback: 0 apps recorded because the flow made him navigate
    to Journey → change status. Now: one click on the detail pane.
    """
    now = _now()
    with tx(path) as conn:
        existing = conn.execute(
            "SELECT id, status FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        if existing:
            app_id = int(existing["id"])
            if existing["status"] == "interested":
                conn.execute(
                    "UPDATE applications SET status = 'applied', "
                    "  applied_at = COALESCE(applied_at, ?), "
                    "  last_updated = ? "
                    "WHERE id = ?",
                    (now, now, app_id),
                )
            # Any status past 'interested' is preserved as-is.
            return app_id
        cur = conn.execute(
            """INSERT INTO applications
               (job_id, resume_id, status, applied_at, created_at, last_updated, notes)
               VALUES (?, ?, 'applied', ?, ?, ?, '')""",
            (job_id, resume_id, now, now, now),
        )
        return int(cur.lastrowid)


def unmark_job_applied(job_id: str, path: Path = DB_PATH) -> bool:
    """Reverse of `mark_job_applied` — the "click Applied again to
    undo" toggle case. Only fires when status is EXACTLY 'applied'
    (raw mark, no interview progress); statuses past that
    (interviewing / offer) are preserved so an accidental toggle
    can't blow away real interview stage.

    Returns True if a row was removed, False if the toggle no-op'd
    (nothing to remove, or the app has progressed past 'applied').

    Deletes the row rather than downgrading to 'interested' because:
      - Users click Mark as Applied when they applied, period. If
        they undo it, they mean "I didn't apply" — not "I'm
        interested."
      - Same pattern as jobs_unsave (which deletes when status ==
        'interested'). Consistent toggle semantics across the app.
    """
    with tx(path) as conn:
        row = conn.execute(
            "SELECT id, status FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not row or row["status"] != "applied":
            return False
        conn.execute("DELETE FROM applications WHERE id = ?", (int(row["id"]),))
        return True


def update_application(
    app_id: int,
    *,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    resume_id: Optional[int] = None,
    tailoring_level: Optional[str] = None,
    tailored_resume_json: Optional[str] = None,
    tailored_cover_letter: Optional[str] = None,
    path: Path = DB_PATH,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status}")
        fields.append("status = ?")
        values.append(status)
        if status == "applied":
            fields.append("applied_at = COALESCE(applied_at, ?)")
            values.append(_now())
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes)
    if resume_id is not None:
        fields.append("resume_id = ?")
        values.append(resume_id)
    if tailoring_level is not None:
        fields.append("tailoring_level = ?")
        values.append(tailoring_level)
    if tailored_resume_json is not None:
        fields.append("tailored_resume_json = ?")
        values.append(tailored_resume_json)
    if tailored_cover_letter is not None:
        fields.append("tailored_cover_letter = ?")
        values.append(tailored_cover_letter)

    if not fields:
        return
    fields.append("last_updated = ?")
    values.append(_now())
    values.append(app_id)
    with tx(path) as conn:
        conn.execute(
            f"UPDATE applications SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )


def get_application(app_id: int, path: Path = DB_PATH) -> Optional[dict]:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
        return dict(row) if row else None


def get_application_by_job(job_id: str, path: Path = DB_PATH) -> Optional[dict]:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None


def list_applications(
    *,
    statuses: Optional[Iterable[str]] = None,
    path: Path = DB_PATH,
) -> list[dict]:
    """Return apps joined with their job. Newest activity first."""
    where = ""
    params: tuple = ()
    if statuses:
        statuses = tuple(statuses)
        where = f"WHERE a.status IN ({','.join('?' * len(statuses))})"
        params = statuses
    sql = f"""
        SELECT a.*, j.title AS job_title, j.company AS job_company,
               j.location AS job_location, j.job_url AS job_url,
               j.job_url_direct AS job_url_direct,
               j.site AS job_site, j.description AS job_description
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        {where}
        ORDER BY a.last_updated DESC
    """
    with connect(path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def delete_application(app_id: int, path: Path = DB_PATH) -> None:
    with tx(path) as conn:
        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))


def application_status_counts(path: Path = DB_PATH) -> dict[str, int]:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM applications GROUP BY status"
        ).fetchall()
        return {r["status"]: int(r["n"]) for r in rows}


# ---------- saved searches (user-editable templates) ----------

def list_saved_searches(path: Path = DB_PATH) -> list[dict]:
    """Return all saved searches ordered by sort_order then id."""
    with connect(path) as conn:
        rows = conn.execute(
            """SELECT id, name, query, location, hours_old, results_wanted,
                      distance, sort_order, created_at
               FROM saved_searches
               ORDER BY sort_order, id"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_saved_search(sid: int, path: Path = DB_PATH) -> Optional[dict]:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM saved_searches WHERE id = ?", (sid,)
        ).fetchone()
        return dict(row) if row else None


def add_saved_search(
    name: str,
    query: str,
    location: str = "Ottawa, Ontario, Canada",
    hours_old: int = 168,
    results_wanted: int = 30,
    distance: int = 50,
    path: Path = DB_PATH,
) -> int:
    now = _now()
    with tx(path) as conn:
        # Put new items at the end
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS m FROM saved_searches"
        ).fetchone()
        new_order = int(max_order["m"]) + 1
        cur = conn.execute(
            """INSERT INTO saved_searches
               (name, query, location, hours_old, results_wanted, distance, sort_order, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name.strip(), query.strip(), location.strip(),
             hours_old, results_wanted, distance, new_order, now),
        )
        return int(cur.lastrowid)


def update_saved_search(
    sid: int,
    *,
    name: Optional[str] = None,
    query: Optional[str] = None,
    location: Optional[str] = None,
    hours_old: Optional[int] = None,
    results_wanted: Optional[int] = None,
    distance: Optional[int] = None,
    path: Path = DB_PATH,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    if name is not None:
        fields.append("name = ?"); values.append(name.strip())
    if query is not None:
        fields.append("query = ?"); values.append(query.strip())
    if location is not None:
        fields.append("location = ?"); values.append(location.strip())
    if hours_old is not None:
        fields.append("hours_old = ?"); values.append(int(hours_old))
    if results_wanted is not None:
        fields.append("results_wanted = ?"); values.append(int(results_wanted))
    if distance is not None:
        fields.append("distance = ?"); values.append(int(distance))
    if not fields:
        return
    values.append(sid)
    with tx(path) as conn:
        conn.execute(
            f"UPDATE saved_searches SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )


def delete_saved_search(sid: int, path: Path = DB_PATH) -> None:
    with tx(path) as conn:
        conn.execute("DELETE FROM saved_searches WHERE id = ?", (sid,))


# ---------- suggested queries (cached per-resume LLM output) ----------

def get_cached_suggestions(
    resume_id: int,
    max_age_days: int = 7,
    path: Path = DB_PATH,
) -> Optional[dict]:
    """Return {'queries': list, 'generated_at': iso, 'age_days': int} if a cached
    entry exists AND is fresher than max_age_days. None otherwise."""
    with connect(path) as conn:
        row = conn.execute(
            "SELECT queries_json, generated_at FROM suggested_queries WHERE resume_id = ?",
            (resume_id,),
        ).fetchone()
    if not row:
        return None
    try:
        queries = json.loads(row["queries_json"])
        gen_dt = datetime.fromisoformat(row["generated_at"].rstrip("Z"))
        age_days = (datetime.utcnow() - gen_dt).total_seconds() / 86400
        if age_days > max_age_days:
            return None
        return {
            "queries": queries,
            "generated_at": row["generated_at"],
            "age_days": int(age_days),
        }
    except Exception:
        return None


def save_suggestions(
    resume_id: int,
    queries: list[str],
    path: Path = DB_PATH,
) -> None:
    """Upsert cached suggestions for a resume."""
    with tx(path) as conn:
        conn.execute(
            """INSERT INTO suggested_queries (resume_id, queries_json, generated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(resume_id) DO UPDATE SET
                 queries_json = excluded.queries_json,
                 generated_at = excluded.generated_at""",
            (resume_id, json.dumps(queries, ensure_ascii=False), _now()),
        )


def get_resume_ai_summary(resume_id: int, path: Path = DB_PATH) -> Optional[dict]:
    """Return the cached one-shot AI read of a resume:
    {'role_label': str, 'first_impression': str, 'suggestions': [...]}
    or None if never generated. No max-age check — a new resume upload
    gets a fresh row via its own resume_id."""
    with connect(path) as conn:
        row = conn.execute(
            """SELECT role_label, first_impression, suggestions_json
               FROM resume_ai_summary WHERE resume_id = ?""",
            (resume_id,),
        ).fetchone()
    if not row:
        return None
    try:
        suggestions = json.loads(row["suggestions_json"])
    except Exception:
        suggestions = []
    return {
        "role_label": row["role_label"] or "",
        "first_impression": row["first_impression"] or "",
        "suggestions": suggestions,
    }


def save_resume_ai_summary(
    resume_id: int,
    *,
    role_label: str,
    first_impression: str,
    suggestions: list[dict],
    path: Path = DB_PATH,
) -> None:
    """Upsert the cached AI summary for a resume."""
    with tx(path) as conn:
        conn.execute(
            """INSERT INTO resume_ai_summary
               (resume_id, role_label, first_impression, suggestions_json, generated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(resume_id) DO UPDATE SET
                 role_label = excluded.role_label,
                 first_impression = excluded.first_impression,
                 suggestions_json = excluded.suggestions_json,
                 generated_at = excluded.generated_at""",
            (
                resume_id, role_label, first_impression,
                json.dumps(suggestions, ensure_ascii=False), _now(),
            ),
        )


# ---------- job scores (semantic matching cache) ----------

def get_cached_scores(
    resume_id: int,
    job_ids: Iterable[str],
    lang: str,
    path: Path = DB_PATH,
) -> dict[str, dict]:
    """Return {job_id: score_row_dict} for any job in job_ids that already
    has a score for this resume AT THIS UI LANGUAGE. Missing jobs are
    simply omitted; rows scored under a different `lang` are treated as
    misses so callers regenerate in the current language."""
    job_ids = list(job_ids)
    if not job_ids:
        return {}
    with connect(path) as conn:
        placeholders = ",".join("?" * len(job_ids))
        rows = conn.execute(
            f"""SELECT job_id, score, verdict, reasoning,
                       matched_json, gaps_json, model, scored_at
                FROM job_scores
                WHERE resume_id = ? AND lang = ? AND job_id IN ({placeholders})""",
            (resume_id, lang, *job_ids),
        ).fetchall()
        return {r["job_id"]: dict(r) for r in rows}


def save_scores(
    resume_id: int,
    scores: Iterable[dict],
    lang: str,
    path: Path = DB_PATH,
) -> int:
    """Upsert a batch of scores for one resume + language. Each score dict
    must have: job_id, score, verdict, reasoning, matched (list),
    gaps (list), model.

    `lang` is the UI language the reasoning/matched/gaps were generated in
    (see get_reasoning_language). It joins the PK so a Spanish score and
    an English score for the same (resume, job) coexist — no wiping when
    the user flips language.

    Returns count written. Jobs referenced by job_id must already exist in
    the jobs table (FK enforced)."""
    now = _now()
    n = 0
    with tx(path) as conn:
        for s in scores:
            conn.execute(
                """INSERT INTO job_scores (
                    resume_id, job_id, lang, score, verdict, reasoning,
                    matched_json, gaps_json, model, scored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resume_id, job_id, lang) DO UPDATE SET
                    score = excluded.score,
                    verdict = excluded.verdict,
                    reasoning = excluded.reasoning,
                    matched_json = excluded.matched_json,
                    gaps_json = excluded.gaps_json,
                    model = excluded.model,
                    scored_at = excluded.scored_at""",
                (
                    resume_id,
                    s["job_id"],
                    lang,
                    int(s["score"]),
                    str(s["verdict"]),
                    str(s.get("reasoning", "")),
                    json.dumps(s.get("matched") or [], ensure_ascii=False),
                    json.dumps(s.get("gaps") or [], ensure_ascii=False),
                    str(s.get("model", "")),
                    now,
                ),
            )
            n += 1
    return n


# ---------- admin pulse reports (BI agent) ----------

def save_pulse_report(
    *,
    period_start: str,
    period_end: str,
    model: str,
    markdown: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    path: Path = DB_PATH,
) -> int:
    """Persist a generated BI pulse report. Returns the new row id."""
    with tx(path) as conn:
        cur = conn.execute(
            """INSERT INTO admin_reports
               (generated_at, period_start, period_end, model, markdown, tokens_in, tokens_out)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_now(), period_start, period_end, model, markdown,
             int(tokens_in), int(tokens_out)),
        )
        return int(cur.lastrowid)


def latest_pulse_report(path: Path = DB_PATH) -> Optional[dict]:
    """Most recent report, or None if the table is empty."""
    with connect(path) as conn:
        row = conn.execute(
            """SELECT id, generated_at, period_start, period_end, model,
                      markdown, tokens_in, tokens_out
               FROM admin_reports
               ORDER BY generated_at DESC LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None


def list_pulse_reports(limit: int = 20, path: Path = DB_PATH) -> list[dict]:
    """Newest first. Metadata only (no markdown body) — for the date-picker
    list on /admin/pulse. Fetch the full body via get_pulse_report(id)."""
    with connect(path) as conn:
        rows = conn.execute(
            """SELECT id, generated_at, period_start, period_end, model,
                      tokens_in, tokens_out
               FROM admin_reports
               ORDER BY generated_at DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def get_pulse_report(report_id: int, path: Path = DB_PATH) -> Optional[dict]:
    with connect(path) as conn:
        row = conn.execute(
            """SELECT id, generated_at, period_start, period_end, model,
                      markdown, tokens_in, tokens_out
               FROM admin_reports WHERE id = ?""",
            (report_id,),
        ).fetchone()
    return dict(row) if row else None
