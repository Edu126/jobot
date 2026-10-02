# ADR-061: Editorial doctrine (§2A) + 4-size type ladder + one bullet system

Date: 2026-09-28/29 (backfilled 2026-10-01)
Status: Accepted
Relates to: ADR-060, REQ-040 / ADR-046 (typography), commits 80d6470, 90f26f6, ef28999

## Context
Screens looked clean but generic ("student-made"). design.md said *how things look* but never *what earns a place*, so each round added surfaces instead of editing.

## Decision
design.md §2A sets 8 laws:
- one job per screen
- answer first
- a summary synthesizes, never echoes
- subtract first
- secondary looks secondary
- the primary action stays in reach
- right component for the datum, one content surface
- legible measure

Redesigns lead with **what to cut**. Each screen uses at most 4 type sizes (answer 30 · masthead 20 · body 16 · small 14). There's one bullet system (`.ui-list`, en dash).

## Alternatives considered
More styling options per round: that caused the problem.

## Consequences
Rebuilds start subtractive. The Brief was rebuilt first, then Get Ready, Practice and Feedback were rebuilt against it.
