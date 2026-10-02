"""Voice playground (REQ-046, ADR-068) — tune the coach's voice by ear, -edu only.

Gemini has no pitch/rate/SSML knob on native audio. What really moves the
sound is: the voice (30 prebuilt), a natural-language DELIVERY line ("speak
slowly, calm…"), the personality, and — in Live only — the experimental
toggles (affective dialog, proactive audio) and turn-taking (VAD). This module
exposes exactly those knobs:

  - Line test: TTS one sentence with (voice, delivery) → WAV, cached on disk.
  - Takes: every Play is recorded (config + line + WAV) in a side list where
    Eduardo replays, rates 1–5 and likes them to compare mixed settings —
    one JSON file on the volume (the lab never touches users' schemas).
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


# ---------- takes: every Play is recorded ----------
# A take = one generated sample (config + line + WAV). Eduardo plays, rates
# (1–5) and likes them in a side list to compare across mixed settings.
# Stored as one JSON file on the volume (an internal tool on one app — no DB).

def _takes_path() -> Path:
    return lab_dir() / "takes.json"


def _load_takes() -> list[dict]:
    p = _takes_path()
    if not p.exists():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return []
    return rows if isinstance(rows, list) else []


def _save_takes(rows: list[dict]) -> None:
    tmp = _takes_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_takes_path())


def takes() -> list[dict]:
    """Newest first (by `seq` — timestamps tie when two Plays land in one second)."""
    return sorted(_load_takes(), key=lambda r: (r.get("seq", 0), r.get("ts", "")), reverse=True)


def record_take(cfg: dict[str, Any], text: str) -> Optional[dict]:
    """Generate (or reuse) the sample for (cfg, text) and record it as a take.
    The same config + line twice → the same take (no duplicates), moved to the
    top. None when TTS fails."""
    cfg = clean_config(cfg)
    text = (text or DEFAULT_LINE).strip()[:MAX_LINE]
    key = _cache_key(cfg, text)
    rows = _load_takes()
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    seq = max((r.get("seq", 0) for r in rows), default=0) + 1
    for r in rows:
        if r.get("id") == key and (lab_dir() / f"tts-{key}.wav").exists():
            r["ts"], r["seq"] = now, seq
            _save_takes(rows)
            return r
    wav = line_wav(cfg, text)
    if not wav:
        return None
    take = {"id": key, "ts": now, "seq": seq, "cfg": cfg, "text": text, "delivery": delivery_line(cfg),
            "seconds": round(max(0, len(wav) - 44) / 48000, 1),  # 24 kHz · 16-bit mono
            "rating": 0, "liked": False, "note": ""}
    rows = [r for r in rows if r.get("id") != key] + [take]
    _save_takes(rows)
    return take


def take_wav(take_id: str) -> Optional[bytes]:
    if not take_id.isalnum():
        return None
    p = lab_dir() / f"tts-{take_id}.wav"
    return p.read_bytes() if p.exists() else None


def update_take(take_id: str, *, rating: Any = None, liked: Any = None,
                note: Any = None) -> Optional[dict]:
    rows = _load_takes()
    for r in rows:
        if r.get("id") == take_id:
            if rating is not None:
                try:
                    r["rating"] = max(0, min(5, int(rating)))
                except (TypeError, ValueError):
                    pass
            if liked is not None:
                r["liked"] = bool(liked)
            if note is not None:
                r["note"] = str(note)[:300]
            _save_takes(rows)
            return r
    return None


def delete_take(take_id: str) -> bool:
    rows = _load_takes()
    keep = [r for r in rows if r.get("id") != take_id]
    if len(keep) == len(rows):
        return False
    _save_takes(keep)
    return True


def voice_summary(rows: list[dict]) -> list[dict]:
    """Per voice across rated takes: average rating, likes, take count —
    "which voices are winning so far". Unrated takes don't drag the average."""
    stats: dict[str, dict] = {}
    for r in rows:
        v = (r.get("cfg") or {}).get("voice")
        if not v:
            continue
        s = stats.setdefault(v, {"voice": v, "takes": 0, "likes": 0, "_sum": 0, "_n": 0})
        s["takes"] += 1
        s["likes"] += 1 if r.get("liked") else 0
        if r.get("rating"):
            s["_sum"] += r["rating"]
            s["_n"] += 1
    out = []
    for s in stats.values():
        avg = round(s.pop("_sum") / s["_n"], 1) if s["_n"] else 0
        s.pop("_n")
        out.append({**s, "avg": avg})
    return sorted(out, key=lambda s: (-s["avg"], -s["likes"], s["voice"]))


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
