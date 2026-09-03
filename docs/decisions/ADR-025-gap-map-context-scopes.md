# ADR-025: Gap-map context scopes — All / Top 3 / Job-specific over one cache

Date: 2026-09-03
Status: Accepted
Relates to: REQ-020 (tactical gap panel — this is its Phase 2), ADR-022
(aggregation), ADR-023 (per-gap classification cache), ADR-008 (economy)

## Context

REQ-020 Phase 2 wants three lenses over the gap panel: **All Scored Jobs**
(current), **Top 3 Closest Roles** (highest fit score), and **Job Specific**
(one saved/scored vacancy). The panel must switch lens without a new LLM cost.

## Decision

`build_gap_map` gains a `scope`: `("all",)`, `("top3",)`, or `("job", job_id)`.
Scope only narrows WHICH scored jobs feed the frequency aggregation
(`gap_counts_for_resume` gains an optional `job_ids` filter); a new
`scored_jobs_for_resume` ranks the résumé's scored jobs by `score` desc (top-3
job_ids + the Job-specific dropdown options). Everything downstream is unchanged:
the **per-gap classification cache is scope-independent** (a gap's
kind/category/canonical depends on résumé × gap, not which jobs surfaced it), so
every lens reuses the SAME cached rows — **no new LLM call** (ADR-008). Only
counts and the gap set change. The route swaps the `#gap-map` fragment via htmx
on tab/dropdown change; active lens is server-rendered from a `context` param.

## Alternatives considered

- Separate cache per scope: rejected — redundant, classifications don't vary by
  scope, would multiply LLM calls.
- Client-side filtering of the full set: rejected — Top-3 needs score ranking and
  job-specific needs per-job gaps, both server-side data.

## Consequences

- Job-specific counts are all 1 ("in N roles" is hidden for that lens). Top-3 is
  only as meaningful as the score ranking (ADR-018). Empty scopes render the tabs
  + empty pillars (never hide the switcher once anything is scored).
