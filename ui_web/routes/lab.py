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
    rows = lab.trials()
    return templates.TemplateResponse(
        request, "pages/voice_lab.html",
        {"active_tab": "prep", "voices": lab.GEMINI_VOICES, "speeds": list(lab.SPEEDS),
         "tones": list(lab.TONES), "energies": list(lab.ENERGIES),
         "default_line": lab.DEFAULT_LINE, "override": lab.live_override(),
         "interviews": interviews, "trials": rows, "board": lab.leaderboard(rows)})


@router.post("/lab/voice/line")
async def voice_lab_line(request: Request):
    """TTS one line with a config → WAV (cached by config+text)."""
    if not lab.enabled():
        return _off()
    body = await request.json()
    cfg = lab.clean_config(body.get("cfg") or {})
    wav = await asyncio.to_thread(lab.line_wav, cfg, str(body.get("text") or ""))
    if not wav:
        return JSONResponse({"error": "tts_failed"}, status_code=502)
    return Response(content=wav, media_type="audio/wav",
                    headers={"X-Delivery": lab.delivery_line(cfg).encode("ascii", "ignore").decode()})


@router.post("/lab/voice/trial")
async def voice_lab_trial(request: Request):
    """Log one A/B verdict; returns the refreshed log + leaderboard."""
    if not lab.enabled():
        return _off()
    b = await request.json()
    lab.log_trial(b.get("a") or {}, b.get("b") or {}, winner=str(b.get("winner") or ""),
                  tags=b.get("tags") or [], note=str(b.get("note") or ""),
                  text=str(b.get("text") or ""), blind=bool(b.get("blind")))
    rows = lab.trials()
    return JSONResponse({"trials": rows, "board": lab.leaderboard(rows)})


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
