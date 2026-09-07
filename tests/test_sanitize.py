"""strip_md_escapes: the shared cleanup for markdown escapes the LLM leaks
into plain-text surfaces (the `\\-` rendering Eduardo flagged, 2026-09-01).

Runs without pytest:
    .venv/bin/python tests/test_sanitize.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm.sanitize import strip_md_escapes  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    cases = {
        r"\- five years of experience": "- five years of experience",
        r"B\.Sc\. in Civil Engineering": "B.Sc. in Civil Engineering",
        r"managed a team \(remote\)": "managed a team (remote)",
        r"cost \+ schedule ownership": "cost + schedule ownership",
        "no escapes here": "no escapes here",             # unchanged
        "": "",                                            # empty
    }
    for raw, want in cases.items():
        got = strip_md_escapes(raw)
        _assert(got == want, f"{raw!r} → {got!r}, expected {want!r}")

    # Real newlines/tabs must survive — they are control chars, not `\`+letter.
    _assert(strip_md_escapes("line1\nline2\tend") == "line1\nline2\tend",
            "real control chars must be preserved")

    # Idempotent + non-str coercion.
    once = strip_md_escapes(r"a \- b")
    _assert(strip_md_escapes(once) == once, "must be idempotent")
    _assert(strip_md_escapes(42) == "42", "non-str is coerced")

    print("OK — strip_md_escapes verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
