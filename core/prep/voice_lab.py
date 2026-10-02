"""Voice playground (REQ-046, ADR-068) — tune the coach's voice by ear, -edu only.

Gemini has no pitch/rate/SSML knob on native audio. What really moves the
sound is: the voice (30 prebuilt), a natural-language DELIVERY line ("speak
slowly, calm…"), the personality, and — in Live only — the experimental
toggles (affective dialog, proactive audio) and turn-taking (VAD). This module
exposes exactly those knobs:

  - Line test: TTS one sentence with (voice, delivery) → WAV, cached on disk.
  - A/B trials: two configs, blind, Eduardo picks + tags; appended to a JSONL
    log on the volume (no DB table — the lab never touches users' schemas).
  - Live override: a config saved here is applied to the REAL practice session
    (`live._config`) while the lab flag is on, so a full mini-interview can be
    heard with it. Off the flag → ignored.

Everything is gated by `JOBOT_VOICE_LAB=1` (set only on -edu). Winners are
promoted to `live.VOICES` / the P7 prompt by a normal code change + ADR — the
lab never changes what users get.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

from core import settings as app_settings

# The 30 Gemini prebuilt voices with Google's one-word character description.
# (Perceived gender is ours, for the picker only — Google doesn't label it.)
GEMINI_VOICES: dict[str, tuple[str, str]] = {
    "Achernar": ("Soft", "f"), "Achird": ("Friendly", "m"), "Algenib": ("Gravelly", "m"),
    "Algieba": ("Smooth", "m"), "Alnilam": ("Firm", "m"), "Aoede": ("Breezy", "f"),
    "Autonoe": ("Bright", "f"), "Callirrhoe": ("Easy-going", "f"), "Charon": ("Informative", "m"),
    "Despina": ("Smooth", "f"), "Enceladus": ("Breathy", "m"), "Erinome": ("Clear", "f"),
    "Fenrir": ("Excitable", "m"), "Gacrux": ("Mature", "f"), "Iapetus": ("Clear", "m"),
    "Kore": ("Firm", "f"), "Laomedeia": ("Upbeat", "f"), "Leda": ("Youthful", "f"),
    "Orus": ("Firm", "m"), "Puck": ("Upbeat", "m"), "Pulcherrima": ("Forward", "f"),
    "Rasalgethi": ("Informative", "m"), "Sadachbia": ("Lively", "m"), "Sadaltager": ("Knowledgeable", "m"),
    "Schedar": ("Even", "m"), "Sulafat": ("Warm", "f"), "Umbriel": ("Easy-going", "m"),
    "Vindemiatrix": ("Gentle", "f"), "Zephyr": ("Bright", "f"), "Zubenelgenubi": ("Casual", "m"),
}

# Delivery knobs → words. "Speed/tone/energy" only exist as instructions.
SPEEDS = {"slower": "slowly, with unhurried pauses", "normal": "at a natural conversational pace",
          "faster": "at a brisk pace"}
TONES = {"calm": "calm and reassuring", "warm": "warm and friendly", "neutral": "neutral and even",
         "formal": "formal and professional", "upbeat": "upbeat and energetic"}
ENERGIES = {"low": "low, steady energy", "medium": "moderate energy", "high": "high energy"}

DEFAULT_LINE = ("Hello Eduardo, I'm Maya. Thanks for making the time today — we'll talk about "
                "the analyst role. To start, tell me a little about yourself.")
MAX_LINE = 400
MAX_EXTRA = 160

TTS_MODEL = "gemini-2.5-flash-preview-tts"
LIVE_OVERRIDE_KEY = "voice_lab_live_override"


def enabled() -> bool:
    return (os.getenv("JOBOT_VOICE_LAB") or "").strip().lower() in ("1", "true", "yes", "on")


def lab_dir() -> Path:
    from core.db import DB_PATH
    d = DB_PATH.parent / "voice_lab"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clean_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a config from the browser to known values (never trust the form)."""
    raw = raw if isinstance(raw, dict) else {}
    pick = lambda v, opts, d: v if v in opts else d  # noqa: E731
    try:
        silence = int(raw.get("silence_ms", 700))
    except (TypeError, ValueError):
        silence = 700
    return {
        "voice": pick(raw.get("voice"), GEMINI_VOICES, "Sulafat"),
        "speed": pick(raw.get("speed"), SPEEDS, "normal"),
        "tone": pick(raw.get("tone"), TONES, "calm"),
        "energy": pick(raw.get("energy"), ENERGIES, "low"),
        "extra": str(raw.get("extra") or "").strip()[:MAX_EXTRA],
        # Live-only knobs (ignored by the line test)
        "affective": bool(raw.get("affective")),
        "proactive": bool(raw.get("proactive")),
        "silence_ms": max(300, min(2000, silence)),
    }


def delivery_line(cfg: dict[str, Any]) -> str:
    """The natural-language delivery instruction for this config — the same
    text drives TTS (style prefix) and Live (replaces P7's Delivery line)."""
    s = (f"Speak {SPEEDS[cfg['speed']]}, in a {TONES[cfg['tone']]} tone, "
         f"with {ENERGIES[cfg['energy']]}.")
    if cfg.get("extra"):
        s += " " + cfg["extra"].rstrip(".") + "."
    return s


def _cache_key(cfg: dict[str, Any], text: str) -> str:
    blob = json.dumps({"v": cfg["voice"], "d": delivery_line(cfg), "t": text, "m": TTS_MODEL},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def line_wav(cfg: dict[str, Any], text: str) -> Optional[bytes]:
    """TTS `text` with (voice, delivery) → WAV. Cached by config+text so
    replaying an A/B costs nothing. None on failure."""
    text = (text or DEFAULT_LINE).strip()[:MAX_LINE]
    path = lab_dir() / f"tts-{_cache_key(cfg, text)}.wav"
    if path.exists():
        return path.read_bytes()
    from core.llm.gemini import resolve_api_key
    from google.genai import types as t
    import google.genai as genai

    from .live import _pcm_to_wav
    try:
        client = genai.Client(api_key=resolve_api_key())
        resp = client.models.generate_content(
            model=TTS_MODEL,
            contents=f"{delivery_line(cfg)} Say exactly:\n{text}",
            config=t.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=t.SpeechConfig(voice_config=t.VoiceConfig(
                    prebuilt_voice_config=t.PrebuiltVoiceConfig(voice_name=cfg["voice"])))),
        )
        pcm = resp.candidates[0].content.parts[0].inline_data.data
    except Exception as exc:  # noqa: BLE001 — the lab reports, never crashes
        print("[voice_lab] tts failed:", type(exc).__name__, str(exc)[:150], flush=True)
        return None
    if not pcm:
        return None
    wav = _pcm_to_wav(pcm)
    try:
        path.write_bytes(wav)
    except OSError:
        pass
    return wav


# ---------- A/B trial log ----------

def _log_path() -> Path:
    return lab_dir() / "trials.jsonl"


def log_trial(a: dict, b: dict, *, winner: str, tags: list[str], note: str, text: str,
              blind: bool) -> dict:
    row = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "a": clean_config(a), "b": clean_config(b),
        "winner": winner if winner in ("a", "b", "tie") else "tie",
        "tags": [str(x)[:24] for x in (tags or [])][:6],
        "note": str(note or "")[:300], "text": str(text or "")[:MAX_LINE], "blind": bool(blind),
    }
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def trials(limit: int = 50) -> list[dict]:
    p = _log_path()
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return list(reversed(rows))[:limit]


def leaderboard(rows: list[dict]) -> list[dict]:
    """Per voice: wins / appearances across logged trials (ties count as
    appearances only). Sorted by win rate, then wins."""
    stats: dict[str, dict] = {}
    for r in rows:
        for side in ("a", "b"):
            v = (r.get(side) or {}).get("voice")
            if not v:
                continue
            s = stats.setdefault(v, {"voice": v, "wins": 0, "played": 0})
            s["played"] += 1
            if r.get("winner") == side:
                s["wins"] += 1
    out = list(stats.values())
    for s in out:
        s["rate"] = round(100 * s["wins"] / s["played"]) if s["played"] else 0
    return sorted(out, key=lambda s: (-s["rate"], -s["wins"], s["voice"]))


# ---------- live override ----------

def live_override() -> Optional[dict]:
    """The config to apply to real practice sessions, or None. Only honoured
    while the lab flag is on (so a stale setting can never reach users)."""
    if not enabled():
        return None
    raw = app_settings.get(LIVE_OVERRIDE_KEY, "")
    if not raw:
        return None
    try:
        return clean_config(json.loads(raw))
    except ValueError:
        return None


def set_live_override(cfg: Optional[dict]) -> None:
    app_settings.set(LIVE_OVERRIDE_KEY, json.dumps(clean_config(cfg)) if cfg else "")
