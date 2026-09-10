# ADR-040: Gap map = recent, high-fit, single lens, rebuildable

Date: 2026-09-09
Status: Accepted
Relates to: REQ-036 (this rework), ADR-022 (aggregation), ADR-023
(classification cache), ADR-024 (dismiss), ADR-025 (context lenses — narrowed
here), ADR-008 (LLM economy), GOV-005 (honesty)

## Context

Mehran's real usage (2026-09-08) exposed three faults: the map aggregated
all-time scored jobs (stale), it counted gaps from low-fit postings (he was shown
data-architect gaps outside his lane), and it was under-populated (2 gaps) with no
way to rebuild. The Top-3 / Job-specific lenses (ADR-025 Phase 2) never earned
their keep.

## Decision

1. **Recency + fit floor on the aggregation.** `gap_counts_for_resume` and
   `scored_jobs_for_resume` only count jobs whose `scored_at` is within 60 days
   AND `score > 70`. Pure SQL, no new LLM cost. The classification cache is
   untouched (it is résumé × gap, filter-independent).
2. **No fallback.** A thin map after filtering is an honest signal (few recent
   strong-fit roles), not a bug. We do not adaptively widen the window/threshold
   to fill the panel — honesty over a full-looking map (GOV-005).
3. **Single lens — machinery removed, not left dormant.** The All / Top-3 /
   Job-specific switcher is gone, and so is the plumbing behind it: the `scope`
   param on `build_gap_map`, `_scope_job_ids`, `TOP_N_CLOSEST`, the `job_ids`
   filter on `gap_counts_for_resume`, and the route's `context`/`job_id` params.
   The map is always the recent high-fit aggregate. (First draft kept `scope`
   "dormant"; the /simplify pass removed it — dead abstraction kept "just in case"
   is the pattern we avoid. If lenses ever return, the right shape is a `job_ids`
   filter re-added on `gap_counts_for_resume`, not a separate resolver.)
4. **Manual flush** deletes this résumé's `gap_classification` rows and
   re-renders; `build_gap_map` then reclassifies the (now recent/high-fit) gap
   set fresh. User-initiated only, ADR-008 economy preserved.
   **[Superseded by ADR-042 — the manual Rebuild was removed: it was an unbounded
   user-triggered cost vector, and decision 5 (full-classify on every render)
   makes the map self-populate without it.]**
5. **Classify the whole filtered set per build**, draining `missing` in up to
   MAX_CLASSIFY_CHUNKS batches of MAX_GAPS_PER_CALL — not just the first batch.
   Field lesson from Mehran (-hermana): lazy 40-per-render classification never
   caught up (128/209 gaps unclassified), and every unclassified gap defaults to
   real+domain, flooding the domain pillar and starving the others. The >70
   filter bounds the set (tens of gaps), so full classification is cheap and
   cached; without it the flush (decision 4) would *worsen* the map transiently.

## Alternatives considered

- Adaptive fallback (widen if <5 gaps): rejected — hides the honest "you have few
  recent strong-fit roles" truth behind a padded panel.
- Softer threshold (>60): rejected for v1 — 70 is the stated fit bar; revisit if
  -edu investigation shows it starves real maps.
- Keep the lenses: rejected — they added choice without insight (REQ-036).

## Consequences

- The map can legitimately be near-empty; the empty-pillar copy carries that.
- ADR-025's lens machinery is dormant (documented, not deleted).
- 60d cutoff is a lexicographic compare on the ISO8601-UTC `scored_at` string —
  no date parsing in SQL.
- The under-population root cause (few jobs>70 vs. stale cache vs. everything
  classified "wording") is investigated on -edu with Mehran-shaped data; flush
  addresses the stale-cache case only.
