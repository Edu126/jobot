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

Display fit as a **bucket label** (Strong / Good / Weak) derived from
**skills-coverage + title match** — computable from the user's resume + the
JD alone — plus the **top reasons in plain language**. Never show a raw
comparable-looking numeric score. **We do not claim "top X% of applicants":**
we have no applicant pool (that data is the ATS's, not ours), so an
applicant-percentile would be invented — the exact black-box dishonesty we
reject. Buckets come from fixed thresholds on our own signal. Movement is
communicated through **specific gaps closed** (skills matched, exact JD terms
added) and an optional before/after similarity **delta**, not a chased number.

## Consequences

- Honest by construction; can't be gamed by number-chasing (upholds the
  no-escape-hatch non-negotiable).
- The grounded "why" is the user's felt validity; real validity accrues via
  the backend outcome loop (REQ-016).
- Internal numeric scores may still exist for ranking/sorting; they are just
  not surfaced raw.
- The lite scoring engine is **skills-coverage + a fast local text-similarity**
  (TF-IDF cosine or a small embedding) for the delta — deterministic, no
  external call in the hot path (see REQ-016).
