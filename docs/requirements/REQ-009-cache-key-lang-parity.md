# REQ-009: Cache-key parity for remaining LLM user-text caches

Date: 2026-08-25
Source: Mehran (2026-08-25 PM feedback dump) + llm-surface.md drift
audit (2026-08-25)
Status: Open

## What they asked for

> Report en inglés post-flip → probablemente admin_reports o
> resume_ai_summary.
> Autofill sugerencias en inglés → resume_suggestions.

Same bug class we fixed for `job_scores` in `08e9619`: the cached
LLM output is user-facing text whose language varies with the UI /
Output setting, but the cache key does not include `lang`. Flipping
language keeps serving the stale-language cached row.

## What they actually need

ADR-008 rule 3 says caches of user-facing LLM text MUST key on every
dimension the output varies by. The 2026-08-25 hotfix applied that
to site #1 (`job_scores`). Sites #7 (`resume_suggestions`) and #8
(`resume_ai_summary`) are the same shape and were flagged as known
drift in llm-surface.md. `admin_reports` (#6) is English-only today
so is out of scope here — flag but don't fix.

Fix pattern is already established: schema bump, migration adds
`lang` column to the cache table, cache read/write paths key on
(existing keys..., lang). The lookup for the language string is
`get_output_language()` for both #7 and #8 per the inventory. The
only decision is whether to do one schema bump covering both tables
or two — cost is similar and one migration is simpler to reason
about.

Because both caches invalidate on resume change, the user-visible
symptom only appears when the user flips language without changing
their resume. That's exactly what Mehran did to expose the bug.

## How we'll know it worked

- Load Jobs page in ES, quick-fill chips render in Spanish.
- Flip UI to EN in Profile. Reload Jobs page. Quick-fill chips
  render in English on the next load (not stale Spanish).
- Same round-trip on Profile's AI summary card.
- `grep` the codebase for cache reads that pass `resume_id` without
  a language dimension — should return zero sites for user-text
  caches after the fix.
- llm-surface.md "Known drift risks" entry for #7/#8 is removed;
  cache-key column reflects the new keys.

## Related

- ADR-008 rule 3 (parent rule).
- [[feedback_cache_key_all_dimensions]] (memory).
- llm-surface.md sites #7, #8 (drift entries to be closed).
- Commit `08e9619` — the reference implementation on `job_scores`.
