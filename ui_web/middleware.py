"""Cross-cutting request middleware — identity propagation + kill-switch
handling.

Identity middleware: sets the `core.llm.usage.current_identity` ContextVar
so downstream Gemini calls (deep in the stack) can enforce the per-IP
daily cap without every call site having to pass the request through.

LlmDisabledError handler: catches the specific 503 raised when
`LLM_DISABLED=1` is set, returns a clean response (HTMX-friendly HTML
when the request is an HTMX call; JSON otherwise).

Registered from `ui_web.main` via `configure(app)`.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core import feature_flags
from core.llm import usage as llm_usage

from .ratelimit import SID_COOKIE_NAME, get_identity


# Session cookie lifetime. 180 days = "long enough that a job seeker doesn't
# lose their rate-limit bucket over a month-off period." Rotated only when
# it expires or the user clears cookies.
_SID_COOKIE_MAX_AGE = 180 * 24 * 3600


_LOG = logging.getLogger(__name__)


class IdentityMiddleware(BaseHTTPMiddleware):
    """Bind the client's identity to a ContextVar for the request's
    lifetime AND mint a session cookie for stable identity across
    requests. Downstream code (Gemini client, quota accounting) reads
    the ContextVar — no need to thread the request through internal APIs.

    Session cookie behavior:
    - If `jobot_sid` cookie is missing, mint a fresh UUID and set it on
      the outgoing response. Subsequent requests get the same identity
      regardless of source IP.
    - Critical for mobile users on CGNAT — without a cookie, all
      Rogers/Bell subscribers in a metro share one rate-limit bucket
      via their shared carrier NAT.
    - No PII in the cookie; it's just a random token. Auth (planned)
      will layer a signed user_id on top; this cookie remains as the
      fallback for anonymous browsing.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Read identity (prefers cookie; falls back to IP) BEFORE the
        # response is built so downstream Gemini calls see the right one.
        token = llm_usage.set_identity(get_identity(request))
        needs_new_sid = SID_COOKIE_NAME not in request.cookies
        try:
            response = await call_next(request)
        finally:
            llm_usage.reset_identity(token)

        if needs_new_sid:
            # Mint a stable identity so this client stops sharing rate
            # limits with the rest of the CGNAT pool on the next request.
            response.set_cookie(
                SID_COOKIE_NAME,
                value=secrets.token_urlsafe(16),
                max_age=_SID_COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https",
            )
        return response


async def _llm_disabled_handler(request: Request, exc: Exception) -> Response:
    """Return a clean 503 when LLM_DISABLED tripped.

    HTMX request → HTML fragment (renders inline in the existing
    error slots). Anything else → JSON."""
    message = str(exc) or feature_flags.llm_disabled_message()
    hx = request.headers.get("hx-request", "").lower() == "true"
    if hx:
        return HTMLResponse(
            f'<div class="alert alert-warning text-sm">{message}</div>',
            status_code=feature_flags.KILL_SWITCH_STATUS,
        )
    return JSONResponse(
        {"error": "llm_disabled", "detail": message},
        status_code=feature_flags.KILL_SWITCH_STATUS,
    )


def configure(app: FastAPI) -> None:
    """Wire the identity middleware + LlmDisabledError handler onto the
    app. Call once from main.py after `app = FastAPI(...)`."""
    app.add_middleware(IdentityMiddleware)
    app.add_exception_handler(llm_usage.LlmDisabledError, _llm_disabled_handler)
    _LOG.info("Identity middleware + LLM kill-switch handler configured")
