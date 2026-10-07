"""Avatar lab (REQ-047): /lab/avatar 404s without JOBOT_VOICE_LAB; with it, the
page renders in en and es, links the voice lab, and ships all four variants.
    .venv/bin/python tests/test_avatar_lab.py
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ui_web.routes import lab as R  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


def _client():
    app = FastAPI()
    app.include_router(R.router)
    return TestClient(app)


def test_closed_without_flag():
    os.environ.pop("JOBOT_VOICE_LAB", None)
    _assert(_client().get("/lab/avatar").status_code == 404, "must 404 without the flag")
    print("PASS test_closed_without_flag")


def test_page_renders():
    os.environ["JOBOT_VOICE_LAB"] = "1"
    try:
        r = _client().get("/lab/avatar")
        _assert(r.status_code == 200, r.status_code)
        for needle in ("avatarLab()", "voice_visuals.js", "Avatar lab", "/lab/voice", "data-thumb=\"minimal\"", "Use my mic"):
            _assert(needle in r.text, f"missing {needle}")
        from ui_web import i18n
        _assert(i18n.translate("lab.avatar.title", "es") == "Laboratorio de avatar", "es string")
    finally:
        os.environ.pop("JOBOT_VOICE_LAB", None)
    print("PASS test_page_renders")


def test_js_interface_and_i18n():
    js = (ROOT / "ui_web/static/voice_visuals.js").read_text()
    for f in ("makeWave", "makeEthereal", "makeGeometric", "makeMinimal"):
        _assert(f"function {f}(canvas)" in js, f)
    _assert(js.count("frame(state, level, t) {") == 4 and js.count("destroy: s.destroy") == 4, "same interface x4")
    _assert("prefers-reduced-motion" in js, "reduced motion respected")
    from ui_web import i18n
    src = (ROOT / "ui_web/i18n.py").read_text()
    for k in ("lab.avatar.title", "lab.avatar.mic", "lab.nav.avatar", "lab.avatar.state.thinking"):
        _assert(src.count(f'"{k}"') == 2, f"{k} in en and es")
    print("PASS test_js_interface_and_i18n")


if __name__ == "__main__":
    test_closed_without_flag()
    test_page_renders()
    test_js_interface_and_i18n()
    print("all avatar-lab tests passed")
