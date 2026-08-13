"""Journey tab — the "how am I doing?" view.

Full-page dashboard aggregating the local events log into visualizations
that make Mehran's job-hunt rhythm legible: hero metrics, funnel,
7×24 heatmap, activity timeline, auto-generated observations.

Route lives at the top level (not under /profile) because it deserves
first-class navigation next to Jobs / Applications / Profile.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from core import events

from ..deps import templates


router = APIRouter(tags=["journey"])


# Filter windows exposed in the header pill row. Kept small on purpose —
# more slices dilute the dashboard's punch.
_RANGES = {
    "7d":  7,
    "30d": 30,
    "all": 365 * 5,   # effectively "all" for a single-user local app
}


@router.get("/journey")
async def journey_page(
    request: Request,
    range: str = Query("30d", pattern="^(7d|30d|all)$", alias="range"),
):
    # Renamed to avoid shadowing Jinja's built-in `range()` inside the template.
    selected_range = range
    days = _RANGES[selected_range]
    total = events.total_events()

    # Aggregations — all cheap on a single-user SQLite
    counts = events.counts_by_type_last_week() if selected_range == "7d" else _counts_over(days)
    daily = events.daily_activity(days=min(days, 60))
    week_heatmap = events.week_hour_heatmap(days=days)
    funnel = events.funnel_last_month()
    active_days = events.days_with_activity(days=days)
    median_seconds = events.median_time_to_download_seconds(days=days)
    obs = events.observations(days=days)
    timeline = events.recent_activity(limit=30)

    # Pre-computed hero numbers for the metric grid
    key_metrics = {
        "sessions": counts.get(events.PAGE_VIEW, 0),
        "searches_broad": counts.get(events.SEARCH_BROAD, 0),
        "searches_url": counts.get(events.SEARCH_URL_IMPORT, 0),
        "jobs_viewed": counts.get(events.JOB_DETAIL_VIEWED, 0),
        "tailors_generated": counts.get(events.TAILOR_GENERATED, 0),
        "resumes_downloaded": counts.get(events.TAILOR_RESUME_DOWNLOAD, 0),
        "cover_letters_downloaded": counts.get(events.TAILOR_CL_DOWNLOAD, 0),
        "status_changes": counts.get(events.APP_STATUS_CHANGED, 0),
    }

    # Max cell of the heatmap for scaling. Guard against empty log.
    heatmap_max = max((max(row) for row in week_heatmap), default=1) or 1

    return templates.TemplateResponse(
        request,
        "pages/journey.html",
        {
            "active_tab": "journey",
            "selected_range": selected_range,
            "total_events": total,
            "active_days": active_days,
            "key_metrics": key_metrics,
            "daily": daily,
            "week_heatmap": week_heatmap,
            "heatmap_max": heatmap_max,
            "funnel": funnel,
            "median_seconds_to_download": median_seconds,
            "observations": obs,
            "timeline": timeline,
        },
    )


@router.post("/journey/clear")
async def journey_clear(request: Request):
    """Wipe the events log. Fired from the Journey page footer."""
    n = events.clear_all()
    return HTMLResponse(
        f'<div class="pill pill-success inline-flex items-center gap-1.5">'
        f'<i class="ph-thin ph-trash i-3"></i>Cleared {n} events</div>',
        status_code=200,
    )


# ── Internals ──

def _counts_over(days: int) -> dict[str, int]:
    """counts_by_type but over an arbitrary window (not just last week)."""
    from datetime import datetime, timedelta
    from core import db
    since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT type, COUNT(*) AS n FROM events WHERE ts_utc >= ? GROUP BY type",
            (since,),
        ).fetchall()
    return {r["type"]: int(r["n"]) for r in rows}
