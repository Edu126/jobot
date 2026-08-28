# ADR-016: Show fit as a bucket + reasons, not a raw %

Date: 2026-08-27
Status: Accepted
Relates: ADR-015 (single-value scoring), REQ-016, RESEARCH-market-thesis

## Context

Research on how ATS rank resumes (RESEARCH-market-thesis, iteration 2) shows
match scores are **not calibrated** across candidates or jobs — a raw "87%"
is not comparable to another job's "84%". Raw percentages create false
precision, invite "regenerate until greener" gaming, and give the user no
real answer to "is this valid?".

## Decision

Display fit as a **bucket label** (Strong / Good / Weak) plus an approximate
percentile and the **top reasons in plain language**. Never show a raw
comparable-looking numeric score to the user. Score movement is communicated
through **specific gaps closed** (skills matched, exact JD terms added), not a
chased number.

## Consequences

- Honest by construction; can't be gamed by number-chasing (upholds the
  no-escape-hatch non-negotiable).
- The grounded "why" is the user's felt validity; real validity accrues via
  the backend outcome loop (REQ-016).
- Internal numeric scores may still exist for ranking/sorting; they are just
  not surfaced raw.
