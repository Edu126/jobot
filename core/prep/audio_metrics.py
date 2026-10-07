"""Objective pacing metrics from a WAV — the numbers behind "does the coach breathe?"

Pure numpy (numpy+scipy are installed; no librosa/webrtcvad). Given 16-bit mono PCM,
frames the signal, finds silence relative to an adaptive floor, and reports pause
structure + (if a word count is supplied) words-per-minute. This is how I evaluate the
saved coach/candidate audio objectively — I can't hear timbre, but I can measure pace.

    .venv/bin/python -c "from core.prep.audio_metrics import measure_wav; print(measure_wav('x.wav'))"
"""
from __future__ import annotations

import io
import wave
from typing import Optional

import numpy as np

FRAME_MS = 20
MIN_PAUSE_MS = 250      # a real breathing pause
MICRO_GAP_MS = 120      # shorter gaps are just phoneme boundaries, ignore
BRIDGE_GAP_MS = 1000    # speaking time: gaps shorter than this are part of speech (ADR-070)
MIN_SNR_DB = 15         # loudest speech must clear the noise floor by this much to count


def measure_pacing(pcm16: bytes, rate: int = 24000, words: Optional[int] = None) -> dict:
    """Pacing metrics from raw 16-bit little-endian mono PCM."""
    x = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
    if x.size == 0:
        return {"duration_s": 0.0, "voiced_s": 0.0, "pause_count": 0, "pause_ratio": 0.0,
                "mean_pause_s": 0.0, "max_pause_s": 0.0, "longest_run_s": 0.0, "wpm": None}
    hop = max(1, int(rate * FRAME_MS / 1000))
    n = x.size // hop
    frames = x[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    peak = np.percentile(db, 95)
    floor = max(peak - 35, -45)
    silent = db < floor

    frame_s = hop / rate
    min_pause = MIN_PAUSE_MS / 1000
    micro = MICRO_GAP_MS / 1000
    pauses, runs = [], []
    cur_sil = cur_voiced = 0.0
    for s in silent:
        if s:
            cur_sil += frame_s
            if cur_voiced:
                runs.append(cur_voiced); cur_voiced = 0.0
        else:
            cur_voiced += frame_s
            if cur_sil:
                if cur_sil >= micro:
                    pauses.append(cur_sil)
                cur_sil = 0.0
    if cur_voiced:
        runs.append(cur_voiced)
    real_pauses = [p for p in pauses if p >= min_pause]

    duration = float(x.size / rate)
    voiced = float((~silent).sum() * frame_s)
    silence_total = float(sum(p for p in pauses))
    wpm = round(words / (voiced / 60), 1) if (words and voiced > 0) else None
    return {
        "duration_s": round(duration, 2),
        "voiced_s": round(voiced, 2),
        "pause_count": len(real_pauses),
        "pause_ratio": round(silence_total / duration, 3) if duration else 0.0,
        "mean_pause_s": round(float(np.mean(real_pauses)), 2) if real_pauses else 0.0,
        "max_pause_s": round(float(np.max(real_pauses)), 2) if real_pauses else 0.0,
        "longest_run_s": round(float(np.max(runs)), 2) if runs else 0.0,
        "wpm": wpm,
    }


def speaking_seconds(pcm16: bytes, rate: int = 16000) -> int:
    """Seconds the candidate was speaking, measured from their recorded audio
    (ADR-070). Voiced frames are found against THIS recording's own noise floor
    (not a fixed level, so a quiet mic still counts), then gaps < BRIDGE_GAP_MS
    are folded in: speaking rate norms (REQ-043, 130–160 wpm) include the short
    pauses between words and phrases, not the long silences between answers.
    Returns 0 when nothing in the audio stands out from its noise."""
    x = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
    hop = max(1, int(rate * FRAME_MS / 1000))
    n = x.size // hop
    if n == 0:
        return 0
    rms = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    noise, peak = np.percentile(db, 10), np.percentile(db, 95)
    if peak - noise < MIN_SNR_DB:
        return 0
    voiced = db > max(noise + 10, peak - 35)
    idx = np.flatnonzero(voiced)
    bridge = BRIDGE_GAP_MS / FRAME_MS
    total = 1
    for gap in np.diff(idx):
        total += gap if gap <= bridge else 1
    return int(round(total * hop / rate))


def speaking_seconds_wav(wav_bytes: bytes) -> int:
    """`speaking_seconds` from WAV bytes (mono 16-bit); 0 if unreadable."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                return 0
            return speaking_seconds(w.readframes(w.getnframes()), rate=w.getframerate())
    except (wave.Error, EOFError):
        return 0


def measure_wav(path: str, words: Optional[int] = None) -> dict:
    """Same, from a WAV file (mono 16-bit)."""
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        pcm = w.readframes(w.getnframes())
    return measure_pacing(pcm, rate=rate, words=words)
