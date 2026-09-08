# ADR-032: The user is the hero; jobot is the guide

Date: 2026-09-07
Status: Accepted — amends the "heart" of [product/vision.md](../product/vision.md)
Relates to: REQ-027 (presentation/onboarding page), non-negotiable #1 (honesty),
non-negotiable #2 (no fabrication)

## Context
`product/vision.md` framed the heart as *"Jobot carries that load."* That casts
**jobot as the hero** — which implies *we do the work for you* (ghost-writing,
replacement), the exact fabrication smell our honesty non-negotiables ban. The
load is real, but the user is the one who carries it; we only lighten the weight.

## Decision
Flip the narrative role, per StoryBrand (customer = hero, brand = guide):
**"La estrella eres tú. Somos tu equipo de soporte — para que brilles, descubras
y presentes tu mayor potencial."** Jobot lightens the load and helps the user
present their *real* potential; it never performs the candidacy for them. All
user-facing copy (landing, onboarding, prompts) adopts the guide voice.

## Alternatives considered
- Keep "jobot carries the load": simpler, but reinforces replacement/fabrication.
- "Co-pilot" framing: overused, and still shares authorship of the candidacy.

## Consequences
Copy across the app must be audited for hero/guide voice — a one-time cost.
Strengthens honesty (#1) and no-fabrication (#2): "we help YOU present" is
grounded; "we do it for you" is not. `product/vision.md` heart to be amended
explicitly (not silently) to match.
