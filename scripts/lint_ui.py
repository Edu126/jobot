"""UI lint — keeps templates on the design system (design.md §9.0 / §11).

A grep-level check, not a parser: it counts patterns that mean "someone drew
this by hand instead of using macros/ui.html or an app.css token". It is a
RATCHET: current violations are frozen in lint_ui_baseline.json, and the lint
fails only when a (file, rule) count goes UP. Fixing debt lowers the count;
run with --update to lock the new, lower baseline in.

    .venv/bin/python scripts/lint_ui.py            # check (exit 1 on new violations)
    .venv/bin/python scripts/lint_ui.py --update   # rewrite the baseline
    .venv/bin/python scripts/lint_ui.py --report   # show every current hit
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "ui_web" / "templates"
BASELINE = Path(__file__).resolve().parent / "lint_ui_baseline.json"

# The kit itself is allowed to spell out the classes it wraps.
EXEMPT_DIRS = {"macros"}

# rule id → (regex, what to use instead)
RULES: dict[str, tuple[re.Pattern[str], str]] = {
    "raw-color": (
        re.compile(r"hsl\(|oklch\(|#[0-9a-fA-F]{6}\b"),
        "a token/class from app.css (§4) — never a literal colour in a template",
    ),
    "text-opacity": (
        re.compile(r"text-base-content/\d+"),
        "text-body-muted / the --n-* ramp (§4.4) — no ad-hoc opacities",
    ),
    "adhoc-radius": (
        re.compile(r"\brounded-(?:sm|md|lg|xl|2xl|3xl)\b"),
        "ui.card / ui.notice (radius comes from the component, §6)",
    ),
    "arbitrary-size": (
        re.compile(r"\btext-\[[0-9.]+(?:px|rem|em)\]"),
        "the type ladder: .text-display/.text-title/h3/h4/.text-eyebrow (§5)",
    ),
    "outlined-box": (
        re.compile(r"\bborder border-base-300\b"),
        "tinta, no contorno: ui.card / ui.notice (grey fill, no outline, §7A)",
    ),
    "hand-h1": (
        re.compile(r"<h1\b"),
        "ui.page_header(...)",
    ),
    "bare-btn": (
        # a `btn` class string with no variant from the kit
        re.compile(
            r"""class="(?![^"]*\bbtn-(?:primary|quiet|ghost|danger|danger-solid|link|circle|square)\b)[^"]*\bbtn\b[^"]*\""""
        ),
        "ui.button(label, variant=...)",
    ),
}


def check_text(text: str) -> dict[str, int]:
    """Count rule hits in one template's source."""
    return {rid: len(rx.findall(text)) for rid, (rx, _) in RULES.items()}


def scan() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(TEMPLATES)
        if rel.parts[0] in EXEMPT_DIRS:
            continue
        counts = {k: v for k, v in check_text(path.read_text(encoding="utf-8")).items() if v}
        if counts:
            out[str(rel)] = counts
    return out


def compare(current: dict[str, dict[str, int]], baseline: dict[str, dict[str, int]]) -> list[str]:
    """Return one message per (file, rule) that got worse than the baseline."""
    problems = []
    for f, rules in current.items():
        for rid, n in rules.items():
            allowed = baseline.get(f, {}).get(rid, 0)
            if n > allowed:
                problems.append(f"{f}: {rid} {allowed} → {n}  (use {RULES[rid][1]})")
    return problems


def main(argv: list[str]) -> int:
    current = scan()
    if "--update" in argv:
        BASELINE.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        total = sum(sum(r.values()) for r in current.values())
        print(f"baseline written: {total} violations across {len(current)} files")
        return 0
    if "--report" in argv:
        for f, rules in current.items():
            print(f, rules)
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    problems = compare(current, baseline)
    if problems:
        print("UI lint — new violations (see design.md §9.0 / §11):")
        for p in problems:
            print("  " + p)
        return 1
    now = sum(sum(r.values()) for r in current.values())
    was = sum(sum(r.values()) for r in baseline.values())
    hint = "  — lower than baseline, run --update to lock it in" if now < was else ""
    print(f"UI lint OK — {now} known violations (baseline {was}){hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
