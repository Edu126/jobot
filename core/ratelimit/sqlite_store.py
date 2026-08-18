"""SQLite-backed storage for SlowAPI (limits.Storage subclass).

Why not the default in-memory store: Fly `auto_stop_machines = 'stop'`
plus `min_machines_running = 0` means the app sleeps when idle. The
in-memory limit store resets on every wake-up, so an attacker pacing
requests to force machine sleep between bursts effectively defeats the
per-hour limits. Persisting counters to the same SQLite file the app
already uses fixes this without adding a new managed service (Redis).

Registered against the `sqlite` and `sqlite+jobot` URI schemes via the
metaclass on `limits.storage.Storage`. Instantiate by passing
`storage_uri="sqlite+jobot://"` to `slowapi.Limiter`; the URI content is
ignored (we always use `core.db.DB_PATH`).

Fixed-window strategy only. Moving-window support is not implemented —
SlowAPI's default `@limiter.limit("N/hour")` uses fixed windows, which
is what we want.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from limits.storage import Storage

from core import db


class SqliteStore(Storage):
    """Persist SlowAPI counters in the app's SQLite DB.

    Table `rate_limits(key TEXT PK, count INT, expiry INT)` is created by
    `db.init_db()` at app startup — this class never issues DDL.

    Concurrency: each method opens a short-lived transaction via
    `db.tx()`. SQLite serializes writers with a file lock; contention on
    the rate-limits table is negligible at our scale (fewer than a few
    ops/sec).
    """

    # Registers this class with the limits metaclass; SlowAPI can then
    # instantiate us via `storage_uri="sqlite+jobot://"`. Prefixed with
    # `+jobot` to avoid confusion if `limits` ever ships a generic
    # `sqlite` scheme upstream.
    STORAGE_SCHEME = ["sqlite+jobot"]

    def __init__(self, uri: str | None = None, wrap_exceptions: bool = False, **options: Any) -> None:
        super().__init__(uri=uri, wrap_exceptions=wrap_exceptions, **options)

    @property
    def base_exceptions(self) -> type[Exception] | tuple[type[Exception], ...]:
        return sqlite3.Error

    # ── SlowAPI/limits interface ──────────────────────────────────────

    def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        """Increment counter for `key`. If the row is missing or expired,
        create it with count=amount and expiry=now+`expiry`. Returns the
        new counter value.

        Fixed-window semantics: once a row exists, its expiry does NOT
        reset on subsequent increments (matches limits' MemoryStorage
        behavior for the fixed-window strategy)."""
        now = int(time.time())
        deadline = now + int(expiry)
        with db.tx() as conn:
            row = conn.execute(
                "SELECT count, expiry FROM rate_limits WHERE key = ?", (key,)
            ).fetchone()
            if row is None or row["expiry"] <= now:
                conn.execute(
                    "INSERT OR REPLACE INTO rate_limits (key, count, expiry) "
                    "VALUES (?, ?, ?)",
                    (key, int(amount), deadline),
                )
                return int(amount)
            new_count = int(row["count"]) + int(amount)
            conn.execute(
                "UPDATE rate_limits SET count = ? WHERE key = ?",
                (new_count, key),
            )
            return new_count

    def get(self, key: str) -> int:
        """Current counter for `key`, or 0 if missing/expired."""
        now = int(time.time())
        with db.connect() as conn:
            row = conn.execute(
                "SELECT count, expiry FROM rate_limits WHERE key = ?", (key,)
            ).fetchone()
        if row is None or row["expiry"] <= now:
            return 0
        return int(row["count"])

    def get_expiry(self, key: str) -> float:
        """Unix seconds when `key` expires; `now` if not present.

        limits treats a missing key as "expires right now" — matching
        MemoryStorage's behavior — so callers can compute reset-in
        without a separate exists check."""
        with db.connect() as conn:
            row = conn.execute(
                "SELECT expiry FROM rate_limits WHERE key = ?", (key,)
            ).fetchone()
        return float(row["expiry"]) if row else float(time.time())

    def check(self) -> bool:
        """Health check — return True if we can round-trip a query."""
        try:
            with db.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def reset(self) -> int | None:
        """Wipe all counters. Only used by tests."""
        with db.tx() as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM rate_limits").fetchone()["n"]
            conn.execute("DELETE FROM rate_limits")
        return int(n)

    def clear(self, key: str) -> None:
        """Drop a single counter."""
        with db.tx() as conn:
            conn.execute("DELETE FROM rate_limits WHERE key = ?", (key,))


def prune_expired() -> int:
    """Delete expired counter rows. Cheap; run opportunistically from
    somewhere that fires occasionally (e.g. task sweep) so the table
    doesn't accumulate stale rows forever. Not called by SlowAPI itself.
    Returns rows deleted."""
    now = int(time.time())
    with db.tx() as conn:
        cur = conn.execute("DELETE FROM rate_limits WHERE expiry <= ?", (now,))
        return int(cur.rowcount or 0)
