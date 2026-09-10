# REQ-036: The gap map earns trust — recent, high-fit, one lens, rebuildable

Date: 2026-09-09
Source: Eduardo (product architect), from Mehran's real usage (2026-09-08)
Status: Building — decisions resolved 2026-09-09 (ADR-040); skill-tree
presentation is an evolution of the REQ-020 pillars, not a redesign.

> Evolves REQ-019 / REQ-020 / ADR-025. Same real-only map (GOV-005), same
> classification cache (ADR-023). Where REQ-020 Phase 2 added three lenses over
> an all-time all-jobs aggregation, this narrows WHAT feeds the map so the signal
> is trustworthy, drops the lenses that never landed, and gives the user a way to
> rebuild a stale map.

## What they asked for

Eduardo (2026-09-08), from watching Mehran use it:
1. **"All scored" should mean the last 60 days**, not all-time — the market-fit
   view must stay current as the user's search focus moves.
2. **Only high-fit jobs (score > 70) should feed the aggregation.** Mehran was
   shown *data-architect* gaps when that is not his lane — low-fit postings
   pollute the gap signal with requirements from roles he is not actually
   targeting.
3. **A manual flush/recompute**, because Mehran saw only **2 gaps** — the map
   looked under-populated and there was no way to force a rebuild.
4. **Hide the low-value lenses:** "Top 3 Closest" is useless and "Job-specific"
   even more so. Leave one clean view.
5. **Present the skill tree better** — the pillars are the gap map's core
   artifact (the monetized moat) and the current rendering is not landing.

## What they actually need

The gap map is the product's monetized artifact (vision: gap monetized 3×). A
map that mixes stale postings and roles the user is not chasing does not describe
*this candidate against the market they want* — it describes noise, and noise in
the hero artifact quietly destroys trust. Recency + a fit floor make every gap on
the map answer one honest question: "across the good, recent roles I'm targeting,
what actually blocks me?" One lens removes choices that only added confusion. A
flush gives the user authorship when the cached map has gone stale. And the
pillars need visible ranking (frequency weight) so the eye lands on the gap that
blocks the most roles first.

## Resolved decisions (2026-09-09, ADR-040)

1. **Hard filter, no fallback.** Counts feed from jobs with `scored_at` within 60
   days AND `score > 70`. If that leaves the map thin, that is an honest signal
   (few recent strong-fit roles), not something to paper over with an adaptive
   widen. The 2-gap case is investigated as a data/cache question on -edu, not
   fixed by loosening the threshold.
2. **Single lens.** Remove the All / Top-3 / Job-specific switcher (ADR-025
   Phase 2 lenses). The map is always the recent high-fit aggregate. The `scope`
   plumbing may remain internal but the UI shows one view.
3. **Manual flush** clears this résumé's cached gap classifications and re-renders
   (reclassifying fresh) — the user's rebuild button when the map looks stale or
   wrong. One LLM call, user-initiated (ADR-008 economy respected: not automatic).
4. **Skill tree = improved pillars**, not a new metaphor. Keep the 3-column grid
   (Technical · Certifications+Languages · Domain); add a frequency bar so
   ranking is visible at a glance. Evolution of REQ-020, honoring card-density and
   mobile-first.

## What the -hermana investigation actually found (2026-09-09)

Reproducing Mehran's map against his real DB (read-only over SSH) corrected the
premise and surfaced the real defect:

- **The "2 gaps" was a stale snapshot** — his map now renders 13 clusters. Not
  the bug.
- **The >70 filter is validated:** of 209 distinct gaps, 125 appear *only* in
  ≤70 jobs (pure noise — the IT/QA/AVIXA gaps at fit 48-68 he complained about);
  the filter removes them, leaving 84.
- **The real bug — classification never completes.** 128/209 gaps were
  unclassified; each unclassified gap defaults to real+**domain**, so the domain
  pillar filled with junk while technical/certs were starved. Lazy 40-per-render
  classification can't keep up with a user scoring faster than that. → New
  decision 5 below; also means the flush had to reclassify the *whole* set, not
  40, or it would worsen the map.
- **Two things this rework does NOT fix (logged as REQ-037):** the scoring layer
  emits *advice as a gap* (e.g. "localiza tu cv al francés para este mercado"
  stored in `gaps_json`), and it *over-scores off-lane roles* (Sage 90, furniture
  installation 82) so their gaps survive the >70 filter. Those are `semantic_score`
  problems, not gap-map problems.

## Resolved decisions (addendum, 2026-09-09)

5. **Classify the whole filtered gap set per build** (bounded, ADR-040 dec. 5) so
   no gap is left unclassified and mis-bucketed into domain.
6. **The manual flush (decision 3) was REMOVED same day (ADR-042).** Decision 5
   makes the map self-populate on every render, so the ask behind decision 3
   (Mehran's under-populated map) is met without a button — and a user-triggered
   full reclassification is an unbounded LLM-cost vector. Recompute is now
   incremental + cached on each visit; no rebuild button, no rate-limit needed.

## Scope guardrails

- **In:** 60-day recency window + `score > 70` floor on the aggregation and the
  scored-jobs ranking; removal of the lens switcher UI; a manual flush that clears
  classifications for the résumé and rebuilds; frequency bars on pillar clusters.
- **Out:** adaptive/fallback thresholds (rejected — honesty over a full-looking
  map); a literal branching tree viz (rejected — density/mobile); course/coaching
  recs (Phase 3); wording gaps as an aggregate (stay per-job, ADR-021); anything
  on the job card (density feedback).

## How we'll know it worked

The thing that stops happening: a user (Mehran) seeing gaps from roles he is not
targeting, or a stale/near-empty map with no way to refresh. Success = the map
shows only gaps from recent, strong-fit roles; the dominant gap per pillar is
obvious from its bar; and the user can flush to rebuild when it looks wrong.

## Related

REQ-019 / REQ-020 (the map this evolves), ADR-022 (aggregation), ADR-023
(classification cache — flush targets it), ADR-024 (dismiss), ADR-025 (lenses,
now narrowed), ADR-040 (this rework's decisions), GOV-005 (enhance ≠ fabricate),
product vision (gap monetized 3×).
