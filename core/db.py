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

SCHEMA_VERSION = 6

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
    score         INTEGER NOT NULL,
    verdict       TEXT NOT NULL,
    reasoning     TEXT NOT NULL,
    matched_json  TEXT NOT NULL,
    gaps_json     TEXT NOT NULL,
    model         TEXT NOT NULL,
    scored_at     TEXT NOT NULL,
    PRIMARY KEY (resume_id, job_id)
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


# ---------- job scores (semantic matching cache) ----------

def get_cached_scores(
    resume_id: int,
    job_ids: Iterable[str],
    path: Path = DB_PATH,
) -> dict[str, dict]:
    """Return {job_id: score_row_dict} for any job in job_ids that already
    has a score for this resume. Missing jobs are simply omitted."""
    job_ids = list(job_ids)
    if not job_ids:
        return {}
    with connect(path) as conn:
        placeholders = ",".join("?" * len(job_ids))
        rows = conn.execute(
            f"""SELECT job_id, score, verdict, reasoning,
                       matched_json, gaps_json, model, scored_at
                FROM job_scores
                WHERE resume_id = ? AND job_id IN ({placeholders})""",
            (resume_id, *job_ids),
        ).fetchall()
        return {r["job_id"]: dict(r) for r in rows}


def save_scores(
    resume_id: int,
    scores: Iterable[dict],
    path: Path = DB_PATH,
) -> int:
    """Upsert a batch of scores for one resume. Each score dict must have:
    job_id, score, verdict, reasoning, matched (list), gaps (list), model.

    Returns count written. Jobs referenced by job_id must already exist in
    the jobs table (FK enforced)."""
    now = _now()
    n = 0
    with tx(path) as conn:
        for s in scores:
            conn.execute(
                """INSERT INTO job_scores (
                    resume_id, job_id, score, verdict, reasoning,
                    matched_json, gaps_json, model, scored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resume_id, job_id) DO UPDATE SET
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
