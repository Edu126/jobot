# ADR-063: Voice and personality decoupled; each voice is a named coach

Date: 2026-09-25 / 2026-10-01 (backfilled 2026-10-01)
Status: Accepted. Supersedes the "bundled persona" part of ADR-053. The voice set itself is superseded by ADR-069 (lab-picked: Anna, Maya, Tom).
Relates to: ADR-053, REQ-044, commit 520d089

## Context
ADR-053 bundled a voice and a personality into one persona (Maya, David, Sam). Eduardo wanted to choose them separately, and wanted something more personal than "your AI interview coach".

## Decision
- There are two dropdowns: **voice** (timbre only: Sulafat, Callirrhoe, Achird, Enceladus, Charon) and **personality** (neutral, friendly, sharp, harsh). Neutral is the default.
- Each voice carries a first name (Maya, Claire, Daniel, Theo, Marcus). It shows in setup and the header pill, and the coach introduces itself with it.
- `practice_sessions.persona` stores the personality id. `voice` is its own column.

## Alternatives considered
Keeping the bundles: fewer choices, but you can't pair a calm voice with a sharp style.

## Consequences
20 combinations, untested by ear. The voice playground (REQ-046) is where we'll tune them.
