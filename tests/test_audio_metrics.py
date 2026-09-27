"""Pacing metrics from synthetic PCM (no audio files, no network).

    .venv/bin/python tests/test_audio_metrics.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from core.prep import audio_metrics as am  # noqa: E402


def _tone(seconds, rate=24000, freq=180.0):
    t = np.arange(int(seconds * rate)) / rate
    return (np.sin(2 * np.pi * freq * t) * 0.3 * 32767).astype("<i2").tobytes()


def _silence(seconds, rate=24000):
    return np.zeros(int(seconds * rate), dtype="<i2").tobytes()


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_empty():
    m = am.measure_pacing(b"", rate=24000)
    _assert(m["duration_s"] == 0.0 and m["pause_count"] == 0, "empty → zeros")
    print("PASS test_empty")


def test_detects_pauses():
    # speak 2s, pause 0.5s, speak 2s, pause 0.4s, speak 1s
    pcm = _tone(2) + _silence(0.5) + _tone(2) + _silence(0.4) + _tone(1)
    m = am.measure_pacing(pcm, rate=24000)
    _assert(m["pause_count"] == 2, f"expected 2 pauses, got {m['pause_count']}")
    _assert(4.5 <= m["duration_s"] <= 6.5, f"duration off: {m['duration_s']}")
    _assert(m["max_pause_s"] >= 0.4, f"max pause too small: {m['max_pause_s']}")
    _assert(m["longest_run_s"] >= 1.5, f"longest run too small: {m['longest_run_s']}")
    print("PASS test_detects_pauses")


def test_micro_gaps_ignored():
    # a 0.1s gap is below MICRO_GAP_MS → not a pause
    pcm = _tone(1) + _silence(0.1) + _tone(1)
    m = am.measure_pacing(pcm, rate=24000)
    _assert(m["pause_count"] == 0, f"micro gap counted: {m['pause_count']}")
    print("PASS test_micro_gaps_ignored")


def test_wpm():
    pcm = _tone(6)  # 6s of voiced → 30 words = 300 wpm
    m = am.measure_pacing(pcm, rate=24000, words=30)
    _assert(m["wpm"] and 250 <= m["wpm"] <= 340, f"wpm off: {m['wpm']}")
    print("PASS test_wpm")


if __name__ == "__main__":
    test_empty()
    test_detects_pauses()
    test_micro_gaps_ignored()
    test_wpm()
    print("all audio_metrics tests passed")
