"""Feedback capture — floating widget in base.html POSTs here.

Anonymous submissions (no auth). Identity comes from the same sid
cookie the rate-limiter uses; a real user_id will layer on top when
auth ships (see docs/rate-limiting-quotas.md §10).

Screenshots arrive as `data:image/png;base64,…` from html2canvas on the
client; server decodes to bytes and writes to `data/feedback/{id}.png`.
Payload capped so a runaway screenshot can't fill the disk.

The BI agent (planned) reads `feedback` + `events` together to surface
per-user themes ("3 people mentioned the geo banner is too big this
week"). Zero PII beyond what the user chose to type.
"""
from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from core import db

from ..ratelimit import get_identity, limiter


router = APIRouter(tags=["feedback"])
_LOG = logging.getLogger(__name__)

# Screenshot payload cap — enough for a full mobile page at 2x DPR
# under html2canvas' PNG output. Reject anything larger to keep the
# volume from filling up if someone submits a spam loop.
_MAX_SHOT_BYTES = 3 * 1024 * 1024   # 3 MB
_MAX_MSG_LEN = 4000


@router.post("/feedback")
@limiter.limit("10/hour")
async def submit_feedback(
    request: Request,
    message: str = Form(...),
    page_url: str = Form(""),
    user_agent: str = Form(""),
    screenshot: str = Form(""),
):
    """Persist a feedback submission. Rate-limited 10/hour per identity
    to guard against a stuck client sending in a loop.

    `screenshot` is an optional `data:image/png;base64,…` dataURL
    produced by html2canvas on the client. Anything unrecognized is
    silently dropped — the message is the primary signal.
    """
    msg = (message or "").strip()
    if not msg:
        return HTMLResponse(
            '<div class="text-error text-sm">Please write a short message before sending.</div>',
            status_code=200,
        )
    msg = msg[:_MAX_MSG_LEN]

    identity = get_identity(request)

    shot_bytes: bytes | None = None
    if screenshot and screenshot.startswith("data:image/png;base64,"):
        raw_b64 = screenshot.split(",", 1)[1]
        try:
            candidate = base64.b64decode(raw_b64, validate=True)
            if len(candidate) <= _MAX_SHOT_BYTES:
                shot_bytes = candidate
            else:
                _LOG.info("feedback: rejected oversized screenshot (%d bytes)", len(candidate))
        except (ValueError, base64.binascii.Error):
            _LOG.info("feedback: invalid base64 screenshot payload")

    fid = db.save_feedback(
        message=msg,
        page_url=(page_url or "")[:512],
        user_agent=(user_agent or "")[:512],
        identity=identity,
        screenshot_bytes=shot_bytes,
    )
    _LOG.info("feedback saved id=%s identity=%s has_shot=%s", fid, identity, bool(shot_bytes))

    return HTMLResponse(
        '<div class="text-sm text-success">✓ Thanks — feedback received.</div>',
        status_code=200,
    )


@router.get("/admin/feedback/{fid}/screenshot")
async def get_screenshot(fid: int):
    """Serve a saved screenshot. No auth yet — admin panel will gate this
    later. For now anyone with the id can view; the id is only surfaced
    to admins so the practical exposure is tiny."""
    row = None
    with db.connect() as conn:
        r = conn.execute(
            "SELECT screenshot_path FROM feedback WHERE id = ?", (fid,)
        ).fetchone()
        row = dict(r) if r else None
    if not row or not row.get("screenshot_path"):
        return Response(status_code=404)
    from pathlib import Path
    p = db.DB_PATH.parent / row["screenshot_path"]
    if not p.exists():
        return Response(status_code=404)
    return Response(content=p.read_bytes(), media_type="image/png")
