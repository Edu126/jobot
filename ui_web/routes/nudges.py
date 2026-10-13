"""Nudge events (REQ-058): the banner and the feedback intro report what the
user did with them. Logged as `nudge.<action>` events; core/nudges.py reads
them back to stop showing a dismissed nudge and to count for /admin/controls."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from core import events, nudges

from ..ratelimit import limiter

router = APIRouter(tags=["nudges"])


@router.post("/nudges/{nudge_id}/{action}")
@limiter.limit("120/hour")
async def nudge_event(request: Request, nudge_id: str, action: str):
    if nudge_id not in nudges.BY_ID or action not in nudges.ACTIONS:
        return Response(status_code=404)
    events.track(f"nudge.{action}", id=nudge_id)
    return Response(status_code=204)
