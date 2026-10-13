"""Per-identity daily Gemini call cap + kill-switch check.

Sits between the FastAPI request and the Gemini client. Two responsibilities:

1. **Kill switch.** `LLM_DISABLED=1` in the environment → refuse the call
   before we spend a token.
2. **Per-identity daily cap.** Each identity (client IP today; user_id
   post-auth) gets `MAX_LLM_CALLS_PER_DAY` successful generate_json calls
   per UTC day, tracked in the SQLite `gemini_usage` table. When over
   cap, raise `QuotaExhaustedError` — the same exception the caller
   already handles for Google's own quota response.

Identity propagation uses a `ContextVar` set by
`ui_web.middleware.IdentityMiddleware` on each request, read by
`check_and_charge()` when the GeminiClient runs. Background threads
(e.g. `_run_expand_background`) inherit the calling request's context
because we spawn them from within the request handler after the ctx
is bound — Python 3.7+ contextvars propagate into `Thread`.

If no identity is bound (CLI scripts, background workers spawned outside
a request), the cap is skipped — the kill switch still fires. That
matches the "protect the multi-user surface" scope without breaking
solo dev / cron scripts.
"""
from __future__ import annotations

import os
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from core import db, feature_flags


# Daily cap per identity (IP today, user_id post-auth). Doubled from the
# initial 300/day plan on user request. See docs/rate-limiting-quotas.md
# and docs/working-plan.md for context. Admin panel (post-auth) will
# allow per-user overrides.
MAX_LLM_CALLS_PER_DAY = 600


# App-wide budgets for the expensive or shared calls (REQ-059). One Fly app is
# one tester (ADR-082), so these count the whole app, not an identity — a
# tester switching networks doesn't get a fresh allowance. Stored as rows in
# `gemini_usage` (identity "app", model "budget:<kind>"), so /admin/pulse
# already lists them. Override per app without a deploy:
# `fly secrets set JOBOT_CAP_VOICE_MONTH=40 -a <app>`.
#   voice  : Gemini Live practice sessions (~$0.15-0.60 each, max 15 min).
#   tavily : company searches. The free plan's 1,000 credits/month are shared
#            by every app on one key, so each app gets a slice.
BUDGETS: dict[str, dict[str, int]] = {
    "voice": {"day": 3, "month": 20},
    "tavily": {"day": 10, "month": 100},
}
BUDGET_IDENTITY = "app"


class LlmDisabledError(RuntimeError):
    """LLM_DISABLED=1 is in effect. Caller should surface a clean 503."""


# Set by request middleware; read by check_and_charge. `None` outside a
# request context — cap is skipped, kill switch still applies.
_current_identity: ContextVar[Optional[str]] = ContextVar("current_identity", default=None)


def set_identity(identity: Optional[str]) -> object:
    """Bind identity for the current context. Returns a Token you can
    pass to `reset_identity` — but usually middleware just sets it and
    lets the request end reset the context automatically."""
    return _current_identity.set(identity)


def reset_identity(token: object) -> None:
    _current_identity.reset(token)  # type: ignore[arg-type]


def current_identity() -> Optional[str]:
    return _current_identity.get()


def check_and_charge(model: str = "any") -> None:
    """Called at the top of every generate_json path.

    Raises:
        LlmDisabledError    — kill switch is on. Caller shows a clean 503.
        QuotaExhaustedError — identity is at or over the daily cap. The
                              existing exhausted-quota UI path handles it.

    On success: reserves one call for this identity (UPSERT + increment).
    Charging happens BEFORE the call rather than after so a concurrent
    burst can't race past the cap between check and commit.

    No identity in context → kill switch still runs, cap is skipped.
    """
    if feature_flags.is_llm_disabled():
        raise LlmDisabledError(feature_flags.llm_disabled_message())

    identity = current_identity()
    if not identity:
        return

    # Import lazily to avoid a circular import (gemini imports usage,
    # usage would otherwise import gemini's QuotaExhaustedError at module
    # top).
    from core.llm.gemini import QuotaExhaustedError

    day = datetime.utcnow().strftime("%Y-%m-%d")
    with db.tx() as conn:
        row = conn.execute(
            "SELECT calls FROM gemini_usage "
            "WHERE identity = ? AND model = ? AND day = ?",
            (identity, model, day),
        ).fetchone()
        current = int(row["calls"]) if row else 0
        if current >= MAX_LLM_CALLS_PER_DAY:
            raise QuotaExhaustedError(
                f"Daily LLM cap reached ({MAX_LLM_CALLS_PER_DAY} calls/day). "
                "Resets at UTC midnight."
            )
        # Reserve immediately — increment count, tokens updated later.
        conn.execute(
            "INSERT INTO gemini_usage (identity, model, day, calls, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, 1, 0, 0) "
            "ON CONFLICT(identity, model, day) DO UPDATE SET calls = calls + 1",
            (identity, model, day),
        )


def record_tokens(model: str, tokens_in: int, tokens_out: int) -> None:
    """After a successful call, add the token counts to the identity's
    per-model row for the day. Best-effort — silent if no identity in
    context.

    Note the split with `check_and_charge`: charging writes into a
    `(identity, "any", day)` bucket (the cap is aggregate across the
    fallback chain), but tokens land in a `(identity, <model>, day)`
    row so per-model detail survives. `get_usage_today` sums both
    without double-counting since calls only live on "any" and tokens
    only live on the specific-model rows.

    Uses UPSERT because the per-model row won't exist yet on the first
    successful call — check_and_charge only touched the "any" row.
    """
    identity = current_identity()
    if not identity or (tokens_in <= 0 and tokens_out <= 0):
        return
    day = datetime.utcnow().strftime("%Y-%m-%d")
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO gemini_usage (identity, model, day, calls, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, 0, ?, ?) "
            "ON CONFLICT(identity, model, day) DO UPDATE SET "
            "  tokens_in = tokens_in + excluded.tokens_in, "
            "  tokens_out = tokens_out + excluded.tokens_out",
            (identity, model, day, int(tokens_in), int(tokens_out)),
        )


def get_usage_today(identity: str) -> dict[str, int]:
    """For a future admin panel + `/admin/health` view: aggregate today's
    usage for one identity across all models. Not called by the runtime
    path; safe to keep here so we don't need a second module."""
    day = datetime.utcnow().strftime("%Y-%m-%d")
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(calls),0) AS calls, "
            "COALESCE(SUM(tokens_in),0) AS tokens_in, "
            "COALESCE(SUM(tokens_out),0) AS tokens_out "
            "FROM gemini_usage WHERE identity = ? AND day = ?",
            (identity, day),
        ).fetchone()
    return {
        "calls": int(row["calls"]),
        "tokens_in": int(row["tokens_in"]),
        "tokens_out": int(row["tokens_out"]),
        "cap": MAX_LLM_CALLS_PER_DAY,
    }


def budget_limits(kind: str) -> dict[str, int]:
    """The day/month limits for `kind`, with `JOBOT_CAP_<KIND>_<DAY|MONTH>`
    env overrides read at call time (a `fly secrets set` applies on restart)."""
    limits = dict(BUDGETS[kind])
    for period in ("day", "month"):
        raw = (os.getenv(f"JOBOT_CAP_{kind.upper()}_{period.upper()}") or "").strip()
        if raw.isdigit():
            limits[period] = int(raw)
    return limits


def budget_used(kind: str) -> dict[str, int]:
    """Units of `kind` used today and this month (UTC)."""
    now = datetime.utcnow()
    day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN day = ? THEN calls END),0) AS d, "
            "COALESCE(SUM(calls),0) AS m FROM gemini_usage "
            "WHERE identity = ? AND model = ? AND day LIKE ?",
            (day, BUDGET_IDENTITY, f"budget:{kind}", month + "-%"),
        ).fetchone()
    return {"day": int(row["d"]), "month": int(row["m"])}


def try_charge_budget(kind: str) -> Optional[str]:
    """Reserve one unit of an app-wide budget. Returns None when reserved, or
    "day" / "month" naming the limit that's already reached (nothing charged).
    The kill switch counts as reached ("disabled")."""
    if feature_flags.is_llm_disabled():
        return "disabled"
    limits = budget_limits(kind)
    now = datetime.utcnow()
    day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    model = f"budget:{kind}"
    with db.tx() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN day = ? THEN calls END),0) AS d, "
            "COALESCE(SUM(calls),0) AS m FROM gemini_usage "
            "WHERE identity = ? AND model = ? AND day LIKE ?",
            (day, BUDGET_IDENTITY, model, month + "-%"),
        ).fetchone()
        if int(row["m"]) >= limits["month"]:
            return "month"
        if int(row["d"]) >= limits["day"]:
            return "day"
        conn.execute(
            "INSERT INTO gemini_usage (identity, model, day, calls, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, 1, 0, 0) "
            "ON CONFLICT(identity, model, day) DO UPDATE SET calls = calls + 1",
            (BUDGET_IDENTITY, model, day),
        )
    return None


def budgets_snapshot() -> list[dict]:
    """Every budget with its limits and use, for the admin page."""
    return [{"kind": k, "limits": budget_limits(k), "used": budget_used(k)} for k in BUDGETS]
