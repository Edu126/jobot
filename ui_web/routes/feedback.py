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
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from core import db

from ..ratelimit import get_identity, limiter


router = APIRouter(tags=["feedback"])
_LOG = logging.getLogger(__name__)

# Image payload cap. Client also validates at 2 MB; this is server-side
# defense-in-depth against a hand-crafted request. Bumped from 3 → 2 MB
# to match the client cap after we switched to file-upload (2026-08-21).
_MAX_SHOT_BYTES = 2 * 1024 * 1024
_MAX_MSG_LEN = 4000

# `data:image/<subtype>;base64,` — any recognisable image mime is fine.
# Was PNG-only in the html2canvas era; widened when we swapped to
# native file upload (2026-08-21) so users can send jpg/webp/etc.
_DATA_URL_RE = re.compile(r"^data:image/([a-zA-Z0-9.+-]+);base64,(.+)$", re.DOTALL)
_ALLOWED_SUBTYPES = {"png", "jpeg", "jpg", "webp", "gif"}


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

    `screenshot` is an optional `data:image/<subtype>;base64,…` dataURL
    from a user-picked file. Anything unrecognized is silently dropped
    — the message is the primary signal.
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
    shot_ext: str = "png"
    if screenshot:
        m = _DATA_URL_RE.match(screenshot)
        if m:
            subtype = m.group(1).lower()
            if subtype in _ALLOWED_SUBTYPES:
                try:
                    candidate = base64.b64decode(m.group(2), validate=True)
                    if len(candidate) <= _MAX_SHOT_BYTES:
                        shot_bytes = candidate
                        shot_ext = "jpg" if subtype == "jpeg" else subtype
                    else:
                        _LOG.info(
                            "feedback: rejected oversized image (%d bytes)",
                            len(candidate),
                        )
                except (ValueError, base64.binascii.Error):
                    _LOG.info("feedback: invalid base64 image payload")

    fid = db.save_feedback(
        message=msg,
        page_url=(page_url or "")[:512],
        user_agent=(user_agent or "")[:512],
        identity=identity,
        screenshot_bytes=shot_bytes,
        screenshot_ext=shot_ext,
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
    # Derive mime from the stored path's suffix. Was PNG-hardcoded;
    # widened when we swapped to user file upload (2026-08-21).
    ext = p.suffix.lstrip(".").lower() or "png"
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp", "gif": "image/gif"}
    return Response(content=p.read_bytes(), media_type=mime_map.get(ext, "image/png"))
