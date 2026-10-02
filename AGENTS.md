# Jobot — repo notes for AI pairs

> **Single source of truth** for every AI agent (Claude Code imports this via
> `CLAUDE.md`; Codex/Cursor/others read it directly). Edit HERE only — never
> fork the rules into CLAUDE.md again (they drifted once, 2026-10-01).

## Way of working (the loop, every change)

1. **Ask → REQ.** A new feature or user/tester feedback gets a
   `docs/requirements/REQ-XXX` *before* code: their words + the need underneath.
2. **Decide → ADR.** Choosing between approaches, or reversing one, gets a
   `docs/decisions/ADR-XXX` at the moment of decision (<150 words).
3. **Build** following the rules below (UI kit, prompts, scores).
4. **Gate locally:** `.venv/bin/python tests/test_*.py` (all), `scripts/lint_ui.py`.
5. **Deploy to -edu** (`fly deploy -a jobbotv2-edu`) and verify there.
6. **Report honestly** — what changed, what was verified and how, what's still weak.

Commit only when Eduardo asks. Work on a feature branch; **merging to `main`
ships to every user at once** — never merge or push to main unasked.

## Architecture docs

This project uses the `solution-architecture` skill. Docs live in `docs/`.

- `docs/architecture/vision.md` — the north star. Every decision must be
  checkable against it.
- `docs/architecture/overview.md` — what jobot is, big pieces, boundaries.
- `docs/architecture/components.md` — Mermaid diagram of the system shape.
- `docs/architecture/llm-surface.md` — inventory of every Gemini call
  site (site, batch, cache, language, output). Update when you add, remove
  or change a call's output — [ADR-008](docs/decisions/ADR-008-prompt-conventions.md)
  makes it a hard rule.
- `docs/decisions/ADR-XXX-<slug>.md` — one decision per file, under 150 words.
- `docs/requirements/REQ-XXX-<slug>.md` — the ask + the need underneath.
- `docs/governance/GOV-XXX-<slug>.md` — who touches what data.

Never delete a superseded ADR; write a new one and mark the old
`Superseded by ADR-YYY`.

## Scores and grades

Every score, band or verdict shown to a user is listed in
[REQ-042](docs/requirements/REQ-042-scoring-inventory-and-principles.md) with
its logic and intent, and must follow its principles: **the LLM gives
evidence, code does the maths; no credit without verifiable proof; strict by
default; explainable; measured numbers (wpm, fillers, seconds) come from code,
never a model.** Adding or changing a score = update REQ-042 in the same change.
Delivery numbers are always shown against a research baseline
([REQ-043](docs/requirements/REQ-043-delivery-gauges-and-baselines.md)).

## Prompts (Gemini)

- `temperature=0.0` for anything graded; JSON out; "unknown → null"; never invent
  facts (GOV-005). Version prompts (`PROMPT_VERSION`) — bump to regenerate.
- **Live voice system prompt stays < 2500 chars** (the Live API silently hangs
  near ~4000; `tests/test_prep_practice.py` enforces it). Context goes in the
  first client turn, not the pinned prompt.
- The coach's register is a calm, professional HR interviewer — never salesy.

## UI work (read before touching any template or app.css)

The style lives in **`design.md`** — it is the authority, not memory and not
the nearest existing template. Before any UI change read §2 + §2A (principles,
editorial doctrine), §7A (surfaces: *tinta, no contorno* — white page, grey
fills, no outlines around things) and §9.0 (the macro kit).

- Build with **`ui_web/templates/macros/ui.html`** (`{% import "macros/ui.html" as ui %}`):
  `page_header`, `section`, `card`, `callout`, `notice`, `button`, `chip`,
  `datum`, `verdict`, `meter`, `gauge`, `seg_tabs`/`utabs`, `empty_state`,
  `split_workspace`. Never hand-draw a header, card, notice, button or chip
  from Tailwind utilities.
- Need something the kit lacks? Add a macro (and its classes in `app.css`,
  from tokens) and document it in design.md §9.0 — don't inline it once.
- No raw colours, `text-base-content/NN`, ad-hoc `rounded-*`, `text-[..]` or
  `border border-base-300` boxes in templates.
- Every user-facing string goes through i18n (`ui_web/i18n.py`) in **both
  `en` and `es`**; plurals get a `_one` key.
- Templates must render for **old data shapes** too (legacy rows in -edu/prod) —
  guard optional fields; add a render test for both shapes.
- **Gate:** `.venv/bin/python scripts/lint_ui.py` (ratchet vs
  `scripts/lint_ui_baseline.json`) and `tests/test_ui_lint.py`. When you pay
  debt down, run `--update` to lock the lower baseline in.

## Verification

- **Eduardo does the visual QA himself.** Don't take browser screenshots by
  default (2026-09-20 — it burns usage); verify in code: unit tests, template
  render checks with fixtures, grep, and HTTP status on the deploy.
- End-to-end runs on **jobbotv2-edu** (the user's Fly staging app), **not**
  locally. When fixtures are needed use the `verify-on-edu` skill (seed over
  SSH → check → restore). -edu holds the user's own data — back up before any
  write, and the skill's restore is mandatory; never skip it.
- Unit tests (`.venv/bin/python tests/test_*.py`) run locally as the first gate.
