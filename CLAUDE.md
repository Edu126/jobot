# Jobot — repo notes for AI pairs

## Architecture practice

This project uses the `solution-architecture` skill. Docs live in `docs/`.
Mandatory: requirement notes before features, ADRs at the moment of decision.

- `docs/architecture/vision.md` — the north star. Every decision must be
  checkable against it.
- `docs/architecture/overview.md` — what jobot is, big pieces, boundaries.
- `docs/architecture/components.md` — Mermaid diagram of the system shape.
- `docs/architecture/llm-surface.md` — inventory of every Gemini call
  site (site, batch, cache, language, output). Update when you add or
  remove a call — [ADR-008](docs/decisions/ADR-008-prompt-conventions.md)
  makes it a hard rule.
- `docs/decisions/ADR-XXX-<slug>.md` — one decision per file, under 150 words.
- `docs/requirements/REQ-XXX-<slug>.md` — the ask + the need underneath.
- `docs/governance/GOV-XXX-<slug>.md` — who touches what data.

Never delete a superseded ADR; write a new one and mark the old
`Superseded by ADR-YYY`.

## Verification

Visual / end-to-end verification runs on **jobbotv2-edu** (the user's Fly
staging app), **not** locally. Use the `verify-on-edu` skill: it deploys the
current code, seeds deterministic fixtures over SSH, drives the deploy from a
headless browser, and restores -edu exactly as found. -edu holds the user's own
data — the skill's backup/restore is mandatory; never skip it. Unit tests
(`.venv/bin/python tests/test_*.py`) still run locally as the first gate.
