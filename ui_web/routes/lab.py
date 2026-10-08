"""Voice playground — `/lab/voice` (REQ-046, ADR-068). -edu only.

Every route 404s unless `JOBOT_VOICE_LAB=1`, so the lab can ship in the image
without ever being reachable on a user's app. JSON in/out; the page is one
Alpine component.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from core import db
from core.prep import live as prep_live
from core.prep import voice_lab as lab

from ..deps import templates

router = APIRouter(tags=["lab"])


def _off():
    return HTMLResponse("", status_code=404)


@router.get("/lab/voice")
async def voice_lab_page(request: Request):
    if not lab.enabled():
        return _off()
    from .interviews import _current
    _resume, resume_hash, _rid, _txt = _current()
    interviews = db.list_interviews(resume_hash)[:8] if resume_hash else []
    rows = lab.takes()
    return templates.TemplateResponse(
        request, "pages/voice_lab.html",
        {"active_tab": "prep", "voices": lab.GEMINI_VOICES, "tones": list(lab.TONES),
         "default_line": lab.DEFAULT_LINE, "override": lab.live_override(),
         "interviews": interviews, "takes": rows, "summary": lab.voice_summary(rows),
         "silence_ms_default": prep_live.SILENCE_MS})


@router.get("/lab/avatar")
async def avatar_lab_page(request: Request):
    """Voice-only avatar playground (REQ-047) — same flag as /lab/voice. Pure
    front-end: no data, no model calls."""
    if not lab.enabled():
        return _off()
    return templates.TemplateResponse(request, "pages/avatar_lab.html", {"active_tab": "prep"})


def _state() -> dict:
    rows = lab.takes()
    return {"takes": rows, "summary": lab.voice_summary(rows)}


@router.post("/lab/voice/take")
async def voice_lab_take(request: Request):
    """One REAL Live generation for {cfg, text} → a recorded take (+ the list)."""
    if not lab.enabled():
        return _off()
    body = await request.json()
    take = await asyncio.to_thread(lab.record_take, body.get("cfg") or {}, str(body.get("text") or ""))
    if not take:
        return JSONResponse({"error": "live_failed"}, status_code=502)
    return JSONResponse({"take": take, **_state()})


@router.get("/lab/voice/take/{take_id}.wav")
async def voice_lab_take_wav(take_id: str, v: str = "stretch"):
    """?v=stretch (as heard in a session, default) or ?v=raw (Gemini as sent)."""
    if not lab.enabled():
        return _off()
    wav = lab.take_wav(take_id, v)
    if not wav:
        return _off()
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/lab/voice/take/{take_id}")
async def voice_lab_take_update(take_id: str, request: Request):
    """Rate (0–5), like/unlike, or note a take — only the fields sent."""
    if not lab.enabled():
        return _off()
    b = await request.json()
    if not lab.update_take(take_id, rating=b.get("rating"), liked=b.get("liked"), note=b.get("note")):
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(_state())


@router.post("/lab/voice/take/{take_id}/delete")
async def voice_lab_take_delete(take_id: str):
    if not lab.enabled():
        return _off()
    lab.delete_take(take_id)
    return JSONResponse(_state())


@router.post("/lab/voice/live")
async def voice_lab_live(request: Request):
    """Set (or clear, with {"clear": true}) the override applied to real
    practice sessions while the lab flag is on."""
    if not lab.enabled():
        return _off()
    b = await request.json()
    lab.set_live_override(None if b.get("clear") else (b.get("cfg") or {}))
    ov = lab.live_override()
    return JSONResponse({"override": ov, "delivery": lab.delivery_line(ov) if ov else ""})
