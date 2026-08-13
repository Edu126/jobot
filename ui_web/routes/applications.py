"""Applications tab routes.

Route map:
    GET  /applications                       → grouped-by-status list
    POST /applications/{app_id}/status       → change status (HX-Refresh)
    POST /applications/{app_id}/notes        → inline save notes → tiny 'saved' fragment
    POST /applications/{app_id}/delete       → delete row → empty fragment (HTMX removes card)

Design notes:
- Status change triggers a full page refresh via the `HX-Refresh` response
  header. That's the cleanest way to move a card from one status section
  to another without hand-swapping DOM in two places.
- Re-tailor button on each card hits `/jobs/tailor/{job_id}` and opens the
  same drawer we built in Phase 3 — the drawer lives in base.html.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from core import db, events

from ..deps import templates


router = APIRouter(tags=["applications"])


# Order sections top-to-bottom (active funnel first, closed states after).
STATUS_ORDER = ["interested", "applied", "interviewing", "offer", "rejected", "withdrawn"]

# Icon = Phosphor thin icon name (no "ph-thin " prefix — template adds it).
# Pill class = semantic color from app.css (pill-neutral/info/celebration/danger).
STATUS_META = {
    "interested":   {"icon": "ph-bookmark-simple", "label": "Interested",   "pill": "pill-neutral"},
    "applied":      {"icon": "ph-paper-plane-tilt","label": "Applied",      "pill": "pill-neutral"},
    "interviewing": {"icon": "ph-chat-circle",     "label": "Interviewing", "pill": "pill-info"},
    "offer":        {"icon": "ph-sparkle",         "label": "Offer",        "pill": "pill-celebration"},
    "rejected":     {"icon": "ph-x-circle",        "label": "Rejected",     "pill": "pill-danger"},
    "withdrawn":    {"icon": "ph-sign-out",        "label": "Withdrawn",    "pill": "pill-neutral"},
}


@router.get("/applications", include_in_schema=False)
async def applications_redirect():
    """Applications merged into Journey (Option 1). Old bookmarks redirect
    to the anchored Apps section on Journey."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/journey#apps", status_code=307)


@router.get("/applications/full")
async def applications_page(request: Request):
    apps = db.list_applications()
    counts = db.application_status_counts()
    # Total excludes closed statuses so "10 active" doesn't count a
    # withdrawn/rejected job you're no longer chasing.
    total_all = sum(counts.values())
    total_active = sum(
        v for k, v in counts.items()
        if k not in ("rejected", "withdrawn")
    )

    by_status: dict[str, list[dict]] = {s: [] for s in STATUS_ORDER}
    for a in apps:
        by_status.setdefault(a["status"], []).append(a)

    return templates.TemplateResponse(
        request,
        "pages/applications.html",
        {
            "active_tab": "applications",
            "counts": counts,
            "total_active": total_active,
            "total_all": total_all,
            "total": total_active,   # backwards-compat for old {{ total }} refs
            "by_status": by_status,
            "status_order": STATUS_ORDER,
            "status_meta": STATUS_META,
        },
    )


@router.post("/applications/{app_id}/status")
async def applications_status(app_id: int, status: str = Form(...)):
    """Move an application to a new status. Refreshes the whole page so cards
    end up in the right section — simpler than swapping DOM in two places."""
    if status not in db.VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")

    existing = db.get_application(app_id)
    if not existing:
        raise HTTPException(status_code=404, detail="application not found")

    old_status = existing["status"]
    db.update_application(app_id, status=status)
    if old_status != status:
        events.track(
            events.APP_STATUS_CHANGED,
            job_id=existing["job_id"],
            application_id=app_id,
            from_status=old_status,
            to_status=status,
        )
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.post("/applications/{app_id}/notes")
async def applications_notes(app_id: int, notes: str = Form("")):
    """Inline notes save. Returns a small 'Saved.' indicator; the textarea
    stays visible so the user can keep editing."""
    existing = db.get_application(app_id)
    if not existing:
        raise HTTPException(status_code=404, detail="application not found")

    db.update_application(app_id, notes=notes)
    return HTMLResponse(
        '<span class="text-xs text-body-muted italic">Saved.</span>',
        status_code=200,
    )


@router.post("/applications/{app_id}/delete")
async def applications_delete(app_id: int):
    existing = db.get_application(app_id)
    if existing:
        db.delete_application(app_id)
    # Return empty body so hx-swap="outerHTML" removes the card from DOM.
    return HTMLResponse("", status_code=200)
