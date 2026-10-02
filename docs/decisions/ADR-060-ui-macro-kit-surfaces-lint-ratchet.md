# ADR-060: UI macro kit + "tinta, no contorno" surfaces + lint ratchet

Date: 2026-09-28 (backfilled 2026-10-01)
Status: Accepted
Relates to: REQ-040, ADR-061, commits d4bc597, c43745a, f8ac4b0

## Context
Tokens alone didn't hold the style. Each screen re-drew headers, cards, buttons and chips from raw Tailwind, giving 7 `<h1>` variants, 44 button strings and 47 hand-built cards. Outlines and tints kept piling up.

## Decision
- `macros/ui.html` is the only way to draw shared pieces: page_header, card, callout, notice, button, chip, datum, verdict, and later meter/gauge.
- Surfaces separate by a grey fill, never an outline, on a pure-white page (§7A).
- `scripts/lint_ui.py` fails on new hand-drawn UI. It's a ratchet against a baseline.

## Alternatives considered
- A style guide with no enforcement: it already failed.
- Rewriting every template at once: too big. The ratchet pays the debt down screen by screen.

## Consequences
A small kit to learn. Anything new needs a macro plus a design.md §9.0 entry first.
