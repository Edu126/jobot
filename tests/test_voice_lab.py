"""Voice playground (REQ-046 / ADR-068). Locks:
  1. every /lab route 404s without JOBOT_VOICE_LAB (can never reach users);
  2. configs from the browser are coerced to known values;
  3. the live override is ignored when the flag is off, and when on it reaches
     the REAL Live config: voice, delivery line in P7, affective, proactive, VAD;
  4. the A/B log + leaderboard round-trip; the page renders.
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
    for method, url in [("get", "/lab/voice"), ("post", "/lab/voice/line"),
                        ("post", "/lab/voice/trial"), ("post", "/lab/voice/live")]:
        r = getattr(c, method)(url, json={}) if method == "post" else c.get(url)
        _assert(r.status_code == 404, f"{url} must 404 without the flag")
    _store[V.LIVE_OVERRIDE_KEY] = '{"voice": "Kore"}'
    _assert(V.live_override() is None, "stale override ignored when flag off")
    _store.clear()
    print("PASS test_closed_without_flag")


def test_clean_config():
    cfg = V.clean_config({"voice": "Evil", "speed": "warp", "tone": "calm", "silence_ms": 99999,
                          "extra": "x" * 500, "affective": 1})
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
        _assert(n < 3500, f"lab worst case stays well under the ~4000 Live hang ({n})")
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


def test_trials_page_and_board():
    os.environ["JOBOT_VOICE_LAB"] = "1"
    try:
        c = _client()
        a, b = {"voice": "Sulafat"}, {"voice": "Vindemiatrix"}
        for w in ("b", "b", "a"):
            r = c.post("/lab/voice/trial", json={"a": a, "b": b, "winner": w, "tags": ["calm"], "blind": True})
        d = r.json()
        _assert(len(d["trials"]) == 3 and d["trials"][0]["winner"] == "a", "newest first")
        board = {x["voice"]: x for x in d["board"]}
        _assert(board["Vindemiatrix"]["wins"] == 2 and board["Vindemiatrix"]["rate"] == 67, "leaderboard")
        r = c.post("/lab/voice/live", json={"cfg": {"voice": "Kore"}})
        _assert(r.json()["override"]["voice"] == "Kore" and "Speak" in r.json()["delivery"], "override set")
        _assert(c.post("/lab/voice/live", json={"clear": True}).json()["override"] is None, "override cleared")
        RI._current = lambda: (None, "", 0, "")
        r = c.get("/lab/voice")
        _assert(r.status_code == 200 and "Vindemiatrix — Gentle" in r.text and "voiceLab(" in r.text, "page renders")
    finally:
        os.environ.pop("JOBOT_VOICE_LAB", None)
    print("PASS test_trials_page_and_board")


if __name__ == "__main__":
    test_closed_without_flag()
    test_clean_config()
    test_override_reaches_live_config()
    test_trials_page_and_board()
    print("all voice-lab tests passed")
