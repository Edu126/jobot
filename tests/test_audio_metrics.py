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


def _speech(seconds, rate=16000, gain=0.3):
    """Syllable-like bursts: 200ms tone / 80ms gap — gaps a speaking clock must bridge."""
    t = np.arange(int(0.2 * rate)) / rate
    burst = (np.sin(2 * np.pi * 180.0 * t) * gain * 32767).astype("<i2").tobytes()
    return (burst + _silence(0.08, rate)) * int(np.ceil(seconds / 0.28))


def test_speaking_seconds_bridges_word_gaps_not_answer_gaps():
    # 3s wait · 10s talking · 4s wait (coach turn already cut out) · 6s talking · 2s wait
    pcm = _silence(3, 16000) + _speech(10) + _silence(4, 16000) + _speech(6) + _silence(2, 16000)
    s = am.speaking_seconds(pcm, rate=16000)
    _assert(15 <= s <= 17, f"expected ~16s speaking, got {s}")
    print("PASS test_speaking_seconds_bridges_word_gaps_not_answer_gaps")


def test_speaking_seconds_quiet_mic():
    # session 39: speech ~0.002 rms never crossed the browser's fixed 0.02 gate → 0s
    rng = np.random.default_rng(0)
    pcm = _silence(2, 16000) + _speech(8, gain=0.003) + _silence(2, 16000)
    x = np.frombuffer(pcm, "<i2").astype(np.float32) + rng.normal(0, 2, len(pcm) // 2)
    s = am.speaking_seconds(x.astype("<i2").tobytes(), rate=16000)
    _assert(7 <= s <= 9, f"quiet mic should still measure ~8s, got {s}")
    print("PASS test_speaking_seconds_quiet_mic")


def test_speaking_seconds_silence_and_noise_are_zero():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 200, 16000 * 5).astype("<i2").tobytes()
    _assert(am.speaking_seconds(_silence(5, 16000), rate=16000) == 0, "silence → 0")
    _assert(am.speaking_seconds(noise, rate=16000) == 0, "steady noise → 0")
    _assert(am.speaking_seconds(b"", rate=16000) == 0, "empty → 0")
    print("PASS test_speaking_seconds_silence_and_noise_are_zero")


def test_speaking_seconds_wav():
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(_silence(1, 16000) + _speech(5) + _silence(1, 16000))
    s = am.speaking_seconds_wav(buf.getvalue())
    _assert(4 <= s <= 6, f"wav → ~5s, got {s}")
    _assert(am.speaking_seconds_wav(b"not a wav") == 0, "garbage → 0")
    print("PASS test_speaking_seconds_wav")


def test_answer_seconds_split_on_coach_turns():
    import io
    import wave
    # coach turn · "yes, ready" (1.4s) · coach · 20s answer · coach · 45s answer
    r = 16000
    parts = [_speech(1.4), _silence(1, r), _speech(20), _silence(1, r), _speech(45)]
    bounds, pos = [0], 0
    for p in parts[:-1]:
        pos += len(p) // 2
        if p is parts[0] or p is parts[2]:
            bounds.append(pos)   # the coach spoke right after these
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(r)
        w.writeframes(b"".join(parts))
    got = am.answer_seconds_wav(buf.getvalue(), bounds)
    _assert(len(got) == 2, f"short 'yes' dropped, two answers left: {got}")
    _assert(19 <= got[0] <= 22 and 44 <= got[1] <= 47, f"per-answer seconds off: {got}")
    junk = am.answer_seconds_wav(buf.getvalue(), ["x", -5, 10**12])
    _assert(len(junk) == 1 and junk[0] >= 60, f"junk bounds ignored → one whole answer: {junk}")
    _assert(am.answer_seconds_wav(b"", [100]) == [], "no audio → no answers")
    print("PASS test_answer_seconds_split_on_coach_turns")


if __name__ == "__main__":
    test_empty()
    test_detects_pauses()
    test_micro_gaps_ignored()
    test_wpm()
    test_speaking_seconds_bridges_word_gaps_not_answer_gaps()
    test_speaking_seconds_quiet_mic()
    test_speaking_seconds_silence_and_noise_are_zero()
    test_speaking_seconds_wav()
    test_answer_seconds_split_on_coach_turns()
    print("all audio_metrics tests passed")
