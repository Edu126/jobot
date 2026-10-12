"""Dictation (REQ-053): "Speak your answer" on the Get Ready text fields, and
the keyboard hint that matches the platform.
    .venv/bin/python tests/test_dictate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starlette.requests import Request  # noqa: E402

from ui_web.deps import templates  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


def _req():
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "app": None})


def test_checkin_has_dictate_and_platform_hint():
    html = templates.get_template("pages/interview_checkin.html").render(
        request=_req(), active_tab="prep", interview={"id": 3, "role_title": "S", "company": "C"},
        step="get_ready", improving=False, facts={},
        checkin_steps=[{"id": "a1", "key": "k1", "question": "Specify the budget", "example": "", "card": "How do you budget?"},
                       {"id": "a2", "key": "k2", "question": "Which tools?", "example": "", "card": ""}])
    _assert(html.count("dictate('fact_a1')") == 1 and html.count("dictate('fact_a2')") == 1, "one dictate button per question field")
    _assert("Speak your answer" in html, "labelled button")
    _assert("⌘/Ctrl" not in html and "⌘ + Enter for next" in html and "Ctrl + Enter for next" in html,
            "shortcut hint matches the platform, not both at once")
    _assert("dictate-stop" in html, "changing step stops dictation")
    print("PASS test_checkin_has_dictate_and_platform_hint")


def test_base_loads_script_and_macro_safe():
    src = (ROOT / "ui_web/templates/base.html").read_text()
    _assert("dictate.js" in src, "base loads dictate.js")
    js = (ROOT / "ui_web/static/dictate.js").read_text()
    _assert("webkitSpeechRecognition" in js and "dispatchEvent(new Event('input'" in js, "browser STT + x-model sync")
    print("PASS test_base_loads_script_and_macro_safe")


if __name__ == "__main__":
    test_checkin_has_dictate_and_platform_hint()
    test_base_loads_script_and_macro_safe()
    print("all dictate tests passed")
