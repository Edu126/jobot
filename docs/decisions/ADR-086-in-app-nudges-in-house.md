# ADR-086: In-app nudges built in-house, rules in code

Date: 2026-10-12
Status: Accepted (Eduardo, guide decision page)

## Context
Users didn't know where to start, and nothing pointed to the next step (REQ-058). Novu is the best open-source option, but it needs Mongo and Redis to self-host, or a hosted service that gets user data. Each tester also has their own database.

## Decision
- Rules live in `core/nudges.py`, one at a time per page. Shipping a change reaches every tester.
- State is kept as `nudge.*` events in the existing events table. A dismissed nudge never returns.
- The look is a calm callout with one action. A "Show me" action uses the Driver.js already loaded to spotlight the target.
- The feedback button says hello once, after the first fit score. Pages can ask gently through a `feedback-open` event: after a 20 s wait, and after practice.
- `/admin/controls` lists every rule with on/off and its counts, next to the usage caps. `JOBOT_NUDGES_OFF` turns a rule off without a deploy.

## Consequences
Editing copy needs a deploy. We revisit Novu with the shared app (ADR-083).
