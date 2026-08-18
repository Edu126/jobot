"""SlowAPI configuration for jobot-app.

Owns the `limiter` singleton, the `get_identity` helper (client IP today;
user_id once auth ships), and the `configure(app)` wire-up.

Routes import `limiter` from here and decorate handlers:

    from ..ratelimit import limiter

    @router.post("/jobs/from-url")
    @limiter.limit("20/hour")
    async def jobs_from_url(request: Request, ...):
        ...

Endpoints decorated with `@limiter.limit(...)` MUST take a `request: Request`
kwarg — SlowAPI reads the identity off it.

Storage is our own SQLite adapter (`core.ratelimit.sqlite_store.SqliteStore`)
because Fly `auto_stop_machines = 'stop'` would reset the in-memory store
on every wake-up, letting a patient attacker defeat per-hour limits.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Import (not just reference) the SqliteStore so its metaclass registers
# the `sqlite+jobot` URI scheme with the `limits` library before we
# construct the Limiter below.
from core.ratelimit.sqlite_store import SqliteStore  # noqa: F401


_LOG = logging.getLogger(__name__)


SID_COOKIE_NAME = "jobot_sid"


def get_identity(request: Request) -> str:
    """The rate-limit key identity for this request.

    Priority:
      1. `jobot_sid` cookie (opaque UUID minted by IdentityMiddleware).
         Survives across requests + across restarts. Critical for mobile
         users on CGNAT carriers — without it, everyone on Rogers/Bell
         mobile shares one rate-limit bucket.
      2. `Fly-Client-IP` header (Fly's edge-inserted real client IP).
      3. `X-Forwarded-For` header (first entry — origin client).
      4. Socket peer (dev / non-Fly deploys).

    Post-auth (see docs/rate-limiting-quotas.md §10) this becomes:
      1. `user:{id}` when authenticated
      2. else this cookie fallback
    """
    sid = request.cookies.get(SID_COOKIE_NAME)
    if sid:
        return f"sid:{sid}"

    for header in ("fly-client-ip", "x-forwarded-for"):
        value = request.headers.get(header)
        if value:
            return value.split(",", 1)[0].strip()
    client = request.client
    return client.host if client and client.host else "unknown"


# One Limiter for the whole app. `storage_uri="sqlite+jobot://"` resolves
# via the metaclass registration in `core.ratelimit.sqlite_store`.
# `default_limits` intentionally empty — every protected endpoint declares
# its own `@limiter.limit(...)`; we don't want a silent global that
# affects healthchecks or static assets.
limiter: Limiter = Limiter(
    key_func=get_identity,
    storage_uri="sqlite+jobot://",
    default_limits=[],
    strategy="fixed-window",
)


def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """Custom 429 handler.

    HTMX requests get an HTML fragment so the existing inline error
    slots render it inline. Non-HTMX requests get JSON. Both include
    a Retry-After header so clients back off.

    `exc` is typed as Exception (not RateLimitExceeded) because FastAPI's
    exception-handler signature contract requires the broader type."""
    if not isinstance(exc, RateLimitExceeded):
        raise exc

    # SlowAPI attaches the rate spec (e.g. "20 per 1 hour") to the exception
    # via .detail; retry-after seconds via .description on some versions,
    # otherwise compute conservatively.
    limit_desc = str(getattr(exc, "detail", None) or "rate limit")
    retry_after = str(int(getattr(exc, "retry_after", 60) or 60))

    hx_request = request.headers.get("hx-request", "").lower() == "true"
    body_msg = (
        f"You're going too fast — rate limit hit ({limit_desc}). "
        f"Try again in {retry_after}s."
    )
    headers = {"Retry-After": retry_after}
    if hx_request:
        return HTMLResponse(
            f'<div class="text-error text-sm p-3">{body_msg}</div>',
            status_code=429,
            headers=headers,
        )
    return JSONResponse({"error": "rate_limited", "detail": body_msg}, status_code=429, headers=headers)


def configure(app: FastAPI) -> None:
    """Attach the limiter + middleware + 429 handler to a FastAPI app.
    Call once from main.py after `app = FastAPI(...)`."""
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    _LOG.info("SlowAPI configured with SqliteStore (sqlite+jobot://)")
