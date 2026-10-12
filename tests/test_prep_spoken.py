"""P10 spoken script (REQ-051, ADR-078): the live aid's conversational version
of a prepared answer. Locks down:
  1. the prompt carries every note + the point to land, and the no-new-facts rule;
  2. cache: a hit costs no call; a changed frame is a miss (new script);
  3. failures / no frame → None (the aid falls back to the points);
  4. attach_scripts fills only questions with a frame.
No network, no DB: a fake client + an in-memory artifact store.
    .venv/bin/python tests/test_prep_spoken.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.llm.gemini import GeminiError  # noqa: E402
from core.prep import spoken as SP  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


_STORE: dict = {}
db.get_prep_artifact = lambda iid, kind, lang, v: ({"artifact": _STORE[(iid, kind, lang, v)], "model": "", "created_at": ""}
                                                   if (iid, kind, lang, v) in _STORE else None)
db.save_prep_artifact = lambda iid, kind, lang, v, art, model="": _STORE.__setitem__((iid, kind, lang, v), art)


class _Fake:
    def __init__(self, script="Sure. Right now I'm an analyst at the CRA.", exc=None):
        self.script, self.exc, self.calls, self.last_model_used = script, exc, 0, "fake"

    def generate_json(self, prompt, temperature=None, **_):
        self.calls += 1
        self.prompt = prompt
        if self.exc:
            raise self.exc
        return {"script": self.script}


Q = {"id": "q1", "text": "Walk me through your background.", "point_to_land": "I bring analytics experience.",
     "frame": [{"section": "now", "points": ["I work as an analyst at the CRA."]},
               {"section": "before", "points": ["I led analytics at ABI, saving 60+ hours a month."]}]}


def test_prompt_rules():
    p = SP.build_prompt(Q["text"], Q["frame"], Q["point_to_land"], lang="en")
    _assert("I led analytics at ABI, saving 60+ hours a month." in p and "Point to land: I bring" in p, "all notes in")
    _assert("Never add a fact" in p and "Never change a number" in p, "no-new-facts rule")
    _assert("connectors" in p and '"script"' in p, "connectors + JSON shape")
    _assert("no em dashes" in p, "plain English: no AI-style em dashes (AGENTS.md)")
    h = SP.build_prompt("q", [{"section": "action", "points": ["I cut costs by [[hint: how much?]] in 2023."]}], "", lang="en")
    _assert("[[hint" not in h and "how much" not in h and "I cut costs by in 2023." in h, "unfilled hint slots left out, never guessed")
    print("PASS test_prompt_rules")


def test_cache_and_frame_change():
    _STORE.clear()
    c = _Fake()
    s1 = SP.spoken_script(3, Q, lang="en", client=c)
    s2 = SP.spoken_script(3, Q, lang="en", client=c)
    _assert(s1 == s2 and c.calls == 1, f"second read is a cache hit, calls={c.calls}")
    _assert(SP.spoken_script(3, Q, lang="en") == s1, "cache-only read (no client) works")
    changed = dict(Q, frame=[{"section": "now", "points": ["I work at CMHC."]}])
    _assert(SP.spoken_script(3, changed, lang="en") is None, "a new frame is a miss")
    _assert(SP.spoken_script(3, Q, lang="es") is None, "language is part of the key")
    print("PASS test_cache_and_frame_change")


def test_failures_fall_back():
    _STORE.clear()
    _assert(SP.spoken_script(3, Q, lang="en", client=_Fake(exc=GeminiError("boom"))) is None, "error → None")
    _assert(SP.spoken_script(3, Q, lang="en", client=_Fake(script="  ")) is None, "empty → None")
    _assert(SP.spoken_script(3, dict(Q, frame=[]), lang="en", client=_Fake()) is None, "no frame → None")
    print("PASS test_failures_fall_back")


def test_attach_only_framed():
    _STORE.clear()
    qs = [dict(Q), {"id": "char_growth", "text": "What are you improving?", "type": "character"}]
    asyncio.run(SP.attach_scripts(3, qs, lang="en", make_client=_Fake))
    _assert(qs[0].get("spoken") and "spoken" not in qs[1], f"only framed questions get a script, got {qs}")
    print("PASS test_attach_only_framed")


def test_aid_renders_script_or_fallback():
    from ui_web.deps import templates
    t = templates.get_template("partials/live_talking_points.html")
    html = t.render(frame=Q["frame"], point=Q["point_to_land"], spoken="Sure. Right now I'm an analyst.")
    _assert("Sure. Right now" in html and "I led analytics" not in html, "script shown when present")
    old = t.render(frame=Q["frame"], point=Q["point_to_land"], spoken=None)
    _assert("I led analytics" in old and "I bring analytics" in old, "older sessions fall back to the points")
    print("PASS test_aid_renders_script_or_fallback")


if __name__ == "__main__":
    test_prompt_rules()
    test_cache_and_frame_change()
    test_failures_fall_back()
    test_attach_only_framed()
    test_aid_renders_script_or_fallback()
    print("all spoken-script tests passed")
