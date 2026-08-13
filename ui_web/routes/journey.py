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

from core import db, events
from ..routes.applications import STATUS_META, STATUS_ORDER

from ..deps import templates


router = APIRouter(tags=["journey"])


# Kanban shows the active pipeline. Terminal statuses (rejected/withdrawn)
# stay accessible but collapsed at the bottom so they don't dominate the
# board. "Interested" is our schema's name for "Saved" in the funnel.
KANBAN_ACTIVE = ["interested", "applied", "interviewing", "offer"]
KANBAN_CLOSED = ["rejected", "withdrawn"]


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

    # Applications data for the kanban mode of the funnel section.
    # Grouped by status so the template can iterate columns.
    apps = db.list_applications()
    by_status: dict[str, list[dict]] = {s: [] for s in STATUS_ORDER}
    for a in apps:
        by_status.setdefault(a["status"], []).append(a)
    closed_count = sum(len(by_status.get(s, [])) for s in KANBAN_CLOSED)

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
            # Kanban context
            "kanban_active": KANBAN_ACTIVE,
            "kanban_closed": KANBAN_CLOSED,
            "by_status": by_status,
            "status_meta": STATUS_META,
            "closed_count": closed_count,
            "apps_total": len(apps),
        },
    )


@router.get("/journey/calendar")
async def journey_calendar_partial(
    request: Request,
    year: int = Query(0),
    month: int = Query(0, ge=0, le=12),
):
    """HTMX partial for the monthly calendar block. Swapped in-place when the
    user clicks the ← / → month nav so the rest of the Journey page doesn't
    re-render (was doing a full page reload — instant vs a beat)."""
    now = datetime.utcnow()
    if not year or not (1 <= month <= 12):
        year, month = now.year, now.month
    return templates.TemplateResponse(
        request,
        "partials/journey_calendar.html",
        {"calendar": events.monthly_calendar(year, month)},
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
