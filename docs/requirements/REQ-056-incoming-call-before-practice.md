# REQ-056: Incoming-call moment before live practice

Date: 2026-10-12
Source: Eduardo (film review page and next-steps page, 2026-10-12)
Status: Open

## What they asked for
The film's scene 4 opens on an incoming-call screen, "Interview practice · Maya".
Eduardo: "something we should replicate" in the product. Decision: build it
once and use the same component in both the film and the app.

## What they actually need
Starting practice should feel like the interview is calling. That gives a
small moment to get ready, not a button that drops you straight into a voice
session. In the film, the same screen proves the product is real.

## Constraints
- A single component (template + CSS) that `landing/film/` renders with fixtures and `/interviews` renders live.
- Only transform and opacity, with a still frame under `prefers-reduced-motion`.
- Answering starts the existing Gemini Live session, so the voice flow doesn't change. Declining returns to the interview page.
- i18n en + es. The interviewer name comes from the existing persona.

## How we'll know it worked
Out of the practice sessions that are opened, more are actually started than before (`prep.practice_*` events).

## Related
REQ-055, `docs/growth/landing-film-script.md` (scene 4), `.claude/skills/motion/`
