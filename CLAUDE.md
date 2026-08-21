# Jobot — repo notes for AI pairs

## Architecture practice

This project uses the `solution-architecture` skill. Docs live in `docs/`.
Mandatory: requirement notes before features, ADRs at the moment of decision.

- `docs/architecture/vision.md` — the north star. Every decision must be
  checkable against it.
- `docs/architecture/overview.md` — what jobot is, big pieces, boundaries.
- `docs/architecture/components.md` — Mermaid diagram of the system shape.
- `docs/decisions/ADR-XXX-<slug>.md` — one decision per file, under 150 words.
- `docs/requirements/REQ-XXX-<slug>.md` — the ask + the need underneath.
- `docs/governance/GOV-XXX-<slug>.md` — who touches what data.

Never delete a superseded ADR; write a new one and mark the old
`Superseded by ADR-YYY`.
