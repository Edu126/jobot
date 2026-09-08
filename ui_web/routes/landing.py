"""Public landing / onboarding one-pager for the Phase 0 stranger cohort
(REQ-027). Presents + manuals + hands off into the app — it does NOT onboard
(activation happens in-app and is measured there).

Standalone shell (not the app nav): a stranger hasn't entered the app yet.
Voice: user is hero, jobot is guide (ADR-032). Web-first (ADR-033). LatAm
Spanish default (REQ-001); `?lang=en` serves the English parallel.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from core import events

from ..deps import templates


router = APIRouter(tags=["landing"])


def _resolve_lang(request: Request, lang_param: str | None) -> str:
    """Explicit ?lang wins (the toggle); otherwise detect from Accept-Language —
    Spanish speakers get ES, everyone else EN (REQ-027 correction 2026-09-08)."""
    if lang_param in ("es", "en"):
        return lang_param
    first = request.headers.get("accept-language", "").split(",")[0].strip().lower()
    return "es" if first.startswith("es") else "en"


@router.get("/welcome")
async def welcome(request: Request, lang: str | None = None):
    lang = _resolve_lang(request, lang)
    # Top-of-funnel signal (feeds S1 activation, REQ-026). Never breaks the page.
    events.track("landing.view", lang=lang)
    return templates.TemplateResponse(
        request,
        "pages/welcome.html",
        {"lang": lang, "active_tab": None},
    )
