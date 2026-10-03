"""Voice playground (REQ-046 / ADR-068). Locks:
  1. every /lab route 404s without JOBOT_VOICE_LAB (can never reach users);
  2. configs from the browser are coerced to known values;
  3. the live override is ignored when the flag is off, and when on it reaches
     the REAL Live config: voice, delivery line in P7, affective, proactive, VAD;
  4. every Play is a recorded take (deduped); rate/like/delete; summary; page renders.
    .venv/bin/python tests/test_voice_lab.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core.prep import live as L  # noqa: E402
from core.prep import voice_lab as V  # noqa: E402
from ui_web.routes import interviews as RI  # noqa: E402
from ui_web.routes import lab as R  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


_store: dict = {}
V.app_settings.get = lambda k, d="": _store.get(k, d)
V.app_settings.set = lambda k, v: _store.__setitem__(k, v)
_tmp = Path(tempfile.mkdtemp())
V.lab_dir = lambda: _tmp


def _client():
    app = FastAPI()
    app.include_router(R.router)
    return TestClient(app)


def test_closed_without_flag():
    os.environ.pop("JOBOT_VOICE_LAB", None)
    c = _client()
    for method, url in [("get", "/lab/voice"), ("post", "/lab/voice/take"), ("get", "/lab/voice/take/abc.wav"),
                        ("post", "/lab/voice/take/abc"), ("post", "/lab/voice/live")]:
        r = getattr(c, method)(url, json={}) if method == "post" else c.get(url)
        _assert(r.status_code == 404, f"{url} must 404 without the flag")
    _store[V.LIVE_OVERRIDE_KEY] = '{"voice": "Kore"}'
    _assert(V.live_override() is None, "stale override ignored when flag off")
    _store.clear()
    print("PASS test_closed_without_flag")


def test_clean_config():
    cfg = V.clean_config({"voice": "Evil", "speed": "warp", "tone": "calm", "silence_ms": 99999,
                          "extra": "x" * 2000, "affective": 1})
    _assert(cfg["voice"] == "Sulafat" and cfg["speed"] == "normal", "unknown values → defaults")
    _assert(cfg["silence_ms"] == 2000 and len(cfg["extra"]) == V.MAX_EXTRA and cfg["affective"] is True, "clamped")
    _assert(len(V.GEMINI_VOICES) == 30, "the full Gemini catalogue")
    line = V.delivery_line(V.clean_config({"speed": "slower", "tone": "calm", "energy": "low", "extra": "lower pitch"}))
    _assert("slowly" in line and "calm" in line and "low, steady energy" in line and "lower pitch." in line, line)
    print("PASS test_clean_config")


def test_override_reaches_live_config():
    os.environ["JOBOT_VOICE_LAB"] = "1"
    try:
        V.set_live_override({"voice": "Vindemiatrix", "speed": "slower", "tone": "calm", "energy": "low",
                             "affective": True, "proactive": True, "silence_ms": 1200})
        L.candidate_first_name = lambda iv: "Eduardo"
        cfg = L._config({"role_title": "Analyst", "company": "CMHC"}, "en", "neutral", "Sulafat")
        _assert(cfg.speech_config.voice_config.prebuilt_voice_config.voice_name == "Vindemiatrix", "lab voice wins")
        prompt = cfg.system_instruction.parts[0].text
        _assert("Speak slowly" in prompt and "I'm Vindemiatrix" in prompt, "delivery line + lab coach name in P7")
        # worst case: long real role + company + a max-length extra instruction
        V.set_live_override({"voice": "Vindemiatrix", "tone": "calm", "extra": "x" * V.MAX_EXTRA})
        worst = L._config({"role_title": "Specialist, IT Financial and Capacity Management",
                           "company": "Canada Mortgage and Housing Corporation (CMHC)"}, "en", "harsh", "Sulafat")
        n = len(worst.system_instruction.parts[0].text)
        # 2026-10-02: Live measured fine up to 20k chars (direct + ephemeral token),
        # so the lab may run long; keep a sane ceiling well under that.
        _assert(n < 6000, f"lab worst case stays bounded ({n})")
        V.set_live_override({"voice": "Vindemiatrix", "speed": "slower", "tone": "calm", "energy": "low",
                             "affective": True, "proactive": True, "silence_ms": 1200})
        _assert(cfg.enable_affective_dialog is True, "affective on")
        _assert(cfg.proactivity and cfg.proactivity.proactive_audio is True, "proactive on")
        _assert(cfg.realtime_input_config.automatic_activity_detection.silence_duration_ms == 1200, "VAD silence")
        V.set_live_override(None)
        cfg2 = L._config({"role_title": "Analyst", "company": "CMHC"}, "en", "neutral", "Sulafat")
        _assert(cfg2.speech_config.voice_config.prebuilt_voice_config.voice_name == "Sulafat", "cleared → normal coach")
    finally:
        os.environ.pop("JOBOT_VOICE_LAB", None)
    print("PASS test_override_reaches_live_config")


def test_takes_rate_like_page():
    os.environ["JOBOT_VOICE_LAB"] = "1"
    calls = []

    def fake_live(cfg, text):
        calls.append(cfg["voice"])
        return b"\0\1" * (24000 * 3), "Hello there"  # 3 s of 24 kHz 16-bit mono
    V.live_pcm = fake_live
    try:
        c = _client()
        r1 = c.post("/lab/voice/take", json={"cfg": {"voice": "Sulafat", "tone": "calm"}, "text": "Hello"}).json()
        r2 = c.post("/lab/voice/take", json={"cfg": {"voice": "Vindemiatrix", "speed": "slower"}, "text": "Hello"}).json()
        _assert(len(r2["takes"]) == 2 and r2["takes"][0]["cfg"]["voice"] == "Vindemiatrix", "every Play is a take, newest first")
        _assert(r1["take"]["seconds"] == 3.0, "duration from the WAV")
        again = c.post("/lab/voice/take", json={"cfg": {"voice": "Sulafat", "tone": "calm"}, "text": "Hello"}).json()
        _assert(len(again["takes"]) == 3 and calls.count("Sulafat") == 2, "Live varies per call → every Play is a new take")
        _assert(r1["take"]["engine"] == "live" and r1["take"]["said"] == "Hello there", "records engine + what Live said")
        tid = r2["take"]["id"]
        d = c.post(f"/lab/voice/take/{tid}", json={"rating": 9, "liked": True}).json()
        t = next(x for x in d["takes"] if x["id"] == tid)
        _assert(t["rating"] == 5 and t["liked"] is True, "rating clamped to 5, liked")
        _assert(d["summary"][0]["voice"] == "Vindemiatrix" and d["summary"][0]["avg"] == 5.0
                and d["summary"][0]["likes"] == 1, "winning-so-far summary")
        _assert(c.get(f"/lab/voice/take/{tid}.wav").headers["content-type"] == "audio/wav", "take audio served")
        _assert(c.get("/lab/voice/take/..%2Fetc.wav").status_code == 404, "no path games on take ids")
        _assert(c.post("/lab/voice/take/nope", json={"rating": 3}).status_code == 404, "unknown take → 404")
        _assert(c.get(f"/lab/voice/take/{tid}.wav?v=raw").status_code == 200, "raw version served")
        _assert(c.get(f"/lab/voice/take/{tid}.wav?v=evil").status_code == 404, "unknown version → 404")
        d = c.post(f"/lab/voice/take/{tid}/delete").json()
        _assert(len(d["takes"]) == 2 and not (_tmp / f"take-{tid}-raw.wav").exists(), "delete removes take + audio")
        r = c.post("/lab/voice/live", json={"cfg": {"voice": "Kore"}})
        _assert(r.json()["override"]["voice"] == "Kore" and "Speak" in r.json()["delivery"], "override set")
        _assert(c.post("/lab/voice/live", json={"clear": True}).json()["override"] is None, "override cleared")
        RI._current = lambda: (None, "", 0, "")
        r = c.get("/lab/voice")
        _assert(r.status_code == 200 and "Vindemiatrix — Gentle" in r.text and "voiceLab(" in r.text
                and "Top rated" in r.text, "page renders with the takes list")
    finally:
        os.environ.pop("JOBOT_VOICE_LAB", None)
    print("PASS test_takes_rate_like_page")


def test_stretch_pauses():
    import array
    rate = 24000
    tone = array.array("h", [8000, -8000] * (rate // 4))          # 0.5 s loud
    gap = lambda sec: array.array("h", [0]) * int(sec * rate)     # noqa: E731
    pcm = (tone + gap(0.30) + tone + gap(0.06) + tone).tobytes()  # one real pause, one tiny gap
    out = V.stretch_pauses(pcm, min_pause_s=0.18, target_s=0.60)
    added = (len(out) - len(pcm)) / 2 / rate
    _assert(abs(added - 0.30) < 0.03, f"0.30 s pause stretched to ~0.60 s (+{added:.2f})")
    _assert(V.stretch_pauses(pcm, min_pause_s=0.40, target_s=0.60) == pcm, "pauses under the threshold untouched")
    cfg = V.clean_config({"min_pause_s": 9, "pause_target_s": "x", "mode": "opening"})
    _assert(cfg["min_pause_s"] == 0.5 and cfg["pause_target_s"] == V.STRETCH_TARGET_S and cfg["mode"] == "opening", "knobs clamped")
    print("PASS test_stretch_pauses")


def test_promoted_coach_voices():
    """ADR-069: the lab winners are the real coach — names, delivery, rules."""
    _assert(list(L.VOICES) == ["Erinome", "Sulafat", "Iapetus"] and L.DEFAULT_VOICE == "Erinome", "3 picked voices")
    _assert([L.coach_name(v) for v in L.VOICES] == ["Anna", "Maya", "Tom"], "friendly names")
    users = {"Melissa", "Sara", "Andrea", "Emma", "Carlos", "Mehran", "Eduardo"}
    _assert(not users & {m[2] for m in L.VOICES.values()}, "never a real user's name")
    os.environ.pop("JOBOT_VOICE_LAB", None)
    L.candidate_first_name = lambda iv: "Eduardo"
    for v in L.VOICES:
        cfg = L._config({"role_title": "Specialist, IT Financial and Capacity Management",
                         "company": "Canada Mortgage and Housing Corporation (CMHC)"}, "en", "harsh", v)
        p = cfg.system_instruction.parts[0].text
        _assert("Speak slowly" in p and "Max one filler per turn" in p and f"I'm {L.coach_name(v)}" in p, v)
        _assert(len(p) < 4500, f"{v} prompt bounded ({len(p)})")
    _assert("high energy" in L.coach_delivery("Sulafat") and "moderate energy" in L.coach_delivery("Erinome"),
            "per-voice energy from the lab")
    print("PASS test_promoted_coach_voices")


if __name__ == "__main__":
    test_closed_without_flag()
    test_clean_config()
    test_override_reaches_live_config()
    test_takes_rate_like_page()
    test_stretch_pauses()
    test_promoted_coach_voices()
    print("all voice-lab tests passed")
