"""Journey tab — the "how am I doing?" view.

v3 layout (feedback-driven, plain-English mode):
  - No top-level time filter — each section has its own natural time frame
    baked into its title. Hero = this week, Funnel = this month, Calendar =
    a specific month (nav arrows).
  - Aggregations stay cheap (single-user SQLite reads); no caching layer
    needed for the ranges the app actually uses.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from core import events

from ..deps import templates


router = APIRouter(tags=["journey"])


@router.get("/journey")
async def journey_page(
    request: Request,
    year: int = Query(0),
    month: int = Query(0, ge=0, le=12),
):
    # Default calendar month = current month (UTC). Users navigate with the
    # ← / → arrows which pass ?year=YYYY&month=MM.
    now = datetime.utcnow()
    if not year or not (1 <= month <= 12):
        year, month = now.year, now.month

    total = events.total_events()
    hero = events.this_week_hero_stats()
    funnel = events.funnel_last_month()
    median_seconds = events.median_time_to_download_seconds(days=30)
    obs = events.observations(days=30)
    calendar_grid = events.monthly_calendar(year, month)

    return templates.TemplateResponse(
        request,
        "pages/journey.html",
        {
            "active_tab": "journey",
            "total_events": total,
            "hero": hero,
            "funnel": funnel,
            "median_seconds_to_download": median_seconds,
            "observations": obs,
            "calendar": calendar_grid,
        },
    )


@router.post("/journey/clear")
async def journey_clear(request: Request):
    """Wipe the events log. Fired from the Journey page footer."""
    n = events.clear_all()
    return HTMLResponse(
        f'<div class="pill pill-success inline-flex items-center gap-1.5">'
        f'<i class="ph-thin ph-trash i-3"></i>Cleared {n} things</div>',
        status_code=200,
    )
