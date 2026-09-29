"""UI lint ratchet (design.md §9.0): templates may not get MORE hand-drawn
UI than the frozen baseline, and each rule actually catches its pattern.

Runs without pytest:
    .venv/bin/python tests/test_ui_lint.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.lint_ui import BASELINE, check_text, compare, scan  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    # 1. The repo is at or under its baseline.
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    problems = compare(scan(), baseline)
    _assert(not problems, "new UI lint violations:\n  " + "\n  ".join(problems))

    # 2. Every rule fires on its pattern…
    samples = {
        "raw-color": '<span style="color: hsl(140 50% 25%)">',
        "text-opacity": '<p class="text-base-content/50">',
        "adhoc-radius": '<div class="rounded-xl p-4">',
        "arbitrary-size": '<h3 class="text-[0.95rem]">',
        "outlined-box": '<div class="rounded-xl border border-base-300 bg-base-100">',
        "hand-h1": '<h1 class="text-2xl">Title</h1>',
        "bare-btn": '<button class="btn btn-sm">Go</button>',
    }
    for rule, html in samples.items():
        _assert(check_text(html)[rule] >= 1, f"{rule} should fire on {html!r}")

    # 3. …and stays quiet on what the kit renders.
    clean = (
        '{{ ui.page_header(_("t")) }}'
        '<div class="card-quiet p-5">'
        '<a class="btn btn-primary btn-sm">Go</a>'
        '<a class="btn btn-quiet btn-sm">Back</a>'
        '<p class="text-body-muted">x</p></div>'
    )
    hits = {k: v for k, v in check_text(clean).items() if v}
    _assert(not hits, f"kit output should be clean, got {hits}")

    # 4. The ratchet: one more violation than the baseline allows → reported.
    fake_now = {"pages/x.html": {"hand-h1": 2}}
    _assert(compare(fake_now, {"pages/x.html": {"hand-h1": 1}}), "increase must be reported")
    _assert(not compare(fake_now, {"pages/x.html": {"hand-h1": 2}}), "equal must pass")
    _assert(compare({"pages/new.html": {"raw-color": 1}}, {}), "a new file starts at zero")

    print("OK — UI lint ratchet verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
