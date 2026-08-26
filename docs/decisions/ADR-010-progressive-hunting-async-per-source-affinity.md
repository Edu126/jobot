# ADR-010: Progressive Hunting — async single-query, per-source discovery, affinity-first scoring order

Date: 2026-08-25
Status: Accepted
Relates to: REQ-011

## Context

Today `/jobs/run` blocks the browser for 30–60 s on a single bundled
`scrape_jobs(sites=[indeed, linkedin, google])` call, then redirects to a
results page whose LLM scoring already streams in progressively (batches of
5 via chained HTMX + OOB swaps at `ui_web/routes/jobs.py:776`). The
scoring half of "Hunting feels alive" is shipped. The discovery half is
not — the user stares at a spinner until every source has finished.

We are still 4 real users, solo maintainer + AI pair, Gemini free tier,
Fly hobby. The goal for Sprint 8 is UX responsiveness, not throughput.
"Make Hunting feel alive before making it faster."

## Decision

Ship progressive Hunting as four independent slices, in this order:

1. **Async single-query search.** `/jobs/run` reuses the existing
   `search_tasks` + `/jobs/loading` pattern already used by multi-query.
   Removes the blocking wait; page renders during discovery.
2. **Per-source JobSpy calls.** Replace the bundled `sites=[...]` call
   with a sequential loop over sources, upserting each site's results as
   they land. Downstream (dedupe, scoring queue) picks them up
   immediately. No JobSpy internals rewrite; no streaming shim.
3. **Cheap deterministic affinity signal.** Per-job affinity (title
   token overlap with resume titles + skill-keyword overlap + location
   bonus). Computed as part of ingestion/upsert so it is available when
   the score-batch endpoint selects the next 5. Initial render orders
   by affinity desc. LLM scores update card badges in place; they do
   NOT re-sort the list.
4. **Match-Score filter gate.** Filter is hidden until
   `discovery_complete AND pending_score_count == 0`. Honest over
   convenient.

Constants stay independent: `_SCORE_BATCH_SIZE = 5` (route),
`JobSearchParams.results_wanted` up to ~60 unique post-dedupe (params),
initial visible window a template concern. Changing one must not
require changing the others.

## Alternatives considered

- **Truly concurrent discovery + scoring** (worker appends to cache
  while UI polls): rejected — cards popping in below what the user is
  reading creates state-management debt no observed bug demands. Slice
  2 already gets first-source results into scoring within seconds.
- **Concurrent LLM scoring batches** (parallel `_score_batch` calls):
  rejected for this phase. Gemini per-model RPM is undocumented in this
  repo; risk of 429s outweighs the win. Visible UX gain is "first badge
  at 3 s," which serial already delivers.
- **Explicit `jobs.status` state column** (discovered / queued / scoring
  / scored / failed): rejected. Presence in `job_scores` IS the
  scoring-done marker; `search_tasks` tracks discovery; adding a
  column re-invents state that lives in two places already and
  creates a "who owns the truth" hazard.
- **Retrofit `core/matching/tfidf_match.py` as the affinity signal**:
  rejected. It builds a fresh vocab per (resume, JD) pair — scores are
  not comparable across jobs. Would need vectorizer rework for no
  gain over a deterministic keyword-overlap heuristic.
- **Re-sort the list as LLM scores arrive**: rejected. Stability beats
  optimality when the user is reading. Badges update in place; the
  affinity order at initial render is the order.
- **Infinite scroll for the 30 initial + remaining ~30**: rejected as a
  requirement. Load-more or nothing at all — decision deferred to
  when the code is written and we can eyeball it.
- **Origin tagging (`exact / expanded / related`) and source-diversity
  heuristic**: deferred. No observed bug at 4 users. The current
  `_dedup_across_sources` + Expand's `last_expand_added_ids` cover
  what the UI needs today.

## Consequences

- **What gets easier.** TTFJ (Time to First Job) drops from
  30–60 s to seconds-after-first-source-returns. Scoring priority
  becomes principled instead of scraped-order. The "60 discovered, 40
  scored" awkward state gets an honest UI answer.
- **What gets harder / accepted debt.**
  - Per-source scraping means per-source rate-limit exposure is now
    slightly more visible — a single-source block used to be masked
    inside the bundled call, now it surfaces as a partial. Handled by
    the existing `search.blocked` event; UI shows partial results.
  - The affinity heuristic will produce mediocre priority for
    off-domain resumes (users whose resume vocabulary doesn't match
    their target roles yet). Acceptable at 4 users; revisit if the
    Pulse report shows scoring order feels wrong.
  - We are explicitly betting that "feel alive" beats "be fast." If
    TTFJ improves but users still complain about total time, we
    revisit concurrent scoring in a later ADR — not silently amend
    this one.
- **Success is measured**, not asserted. REQ-011 defines TTFJ, TTFS,
  and search-completion as the observable outcomes. Instrumentation
  lands in Slice 1.
