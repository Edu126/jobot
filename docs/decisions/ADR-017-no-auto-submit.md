# ADR-017: jobot drafts, the human submits — no auto-submit

Date: 2026-08-27
Status: Accepted
Relates: GOV-003, product/vision.md (Phase 4), RESEARCH-market-thesis

## Context

The Phase-4 vision includes an agent that helps apply. Research
(RESEARCH-market-thesis) shows platforms (LinkedIn, Indeed) ban automated
submission / "human-impossible velocity" and auto-apply bots — but permit
AI-assisted drafting the user reviews. The legal climate reinforces caution
(Mobley v. Workday; AEDT liability). Auto-submission also floods employers
with synthetic applications and risks getting users blacklisted.

## Decision

jobot **never submits an application on the user's behalf without explicit
per-application review.** It is a drafting/assistant surface. Even the future
"agent" mode is *agent drafts, human submits each one*.

## Consequences

- Keeps jobot on the safe side of platform ToS and emerging AEDT law.
- Preserves the "editing effort predicts success" and "user-voiced" findings.
- Constrains the Phase-4 agent vision to human-in-the-loop submission — a
  feature, not a limitation, consistent with GOV-003 (candidate alignment).
