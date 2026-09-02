# REQ-020: The gap map becomes a tactical panel — pillars, clusters, dismiss

Date: 2026-09-02
Source: Eduardo (product architect)
Status: Building — v1 = full engine (pillars + clustering + ✕ dismiss);
context filters (Top 3 / Job-specific) deferred to a Phase-2 slice.

> Evolves REQ-019. Same source gaps, same honesty line (GOV-005), same
> real-only map. Where REQ-019 shipped a flat ranked list of real gaps, this
> turns it into a **diagnostic panel**: gaps bucketed into three themes,
> near-duplicate phrasings clustered into one concept, and the user given a
> ✕ to kill a false positive the AI merged or flagged wrong.

## What they asked for

Eduardo (2026-09-02), full design memo *Market Fit & Gap Map*: split Profile
into two sub-tabs (**Market Fit & Gap Map** default, **Parsed Resume &
Details**); render the map as a 3-column grid (**Technical & Tools** ·
**Certifications & Languages** · **Domain & Experience**), top 5 per column;
each gap is a pill with an "in N roles" badge, a click-popover (grouped
variant terms + defensive talking point), and a hover ✕ to un-group / remove
an AI false positive. Product-vision note: this block migrates to a dedicated
**Growth** tab once active recommendations (courses, mentoring) land.

## What they actually need

A flat list of real gaps answers "what's missing" but not "what should I work
on first, and is this even a real gap or the AI double-counting synonyms?" The
panel makes the map *tactical*: the theme columns tell the user which kind of
gap dominates; clustering stops "Fluent French" and "Bilingual French (CBC)"
reading as two separate problems; the ✕ gives the user authorship over the AI's
semantic calls. That authorship is the seed of the Phase-3 career-persona
object — the first piece of user-corrected truth on their derived gap set.

## Resolved decisions (2026-09-02)

1. **v1 = full engine of one go** (pillars + clustering + ✕ dismiss). Context
   filters (All / Top 3 Closest / Job-specific) are a Phase-2 slice — v1 ships
   the "All scored jobs" lens only.
2. **✕ = dismiss only.** The ✕ marks a cluster as a false positive and drops it
   from the map (persisted per résumé). Term-level un-grouping (splitting a
   cluster, re-counting) is deferred — it opens "what does the split produce?"
   questions not worth v1 (ADR-024).
3. **Map stays real-only** (GOV-005). Wording gaps still live per-job (ADR-021).
   The popover's "grouped terms" are the raw JD/résumé variants that collapsed
   into one real gap, not wording gaps surfacing here.
4. **Clustering + category ride the existing classify call** — no new LLM call
   site (ADR-008 economy). See ADR-023.

## Scope guardrails

- **In:** 3-theme bucketing; semantic clustering of near-duplicate gaps into one
  concept with member-term list; top-5 per pillar ranked by summed cluster
  count; ✕ dismiss with persistence; the Profile two-sub-tab restructure.
- **Out:** context filters (Phase 2); term-level un-grouping (deferred);
  course/coaching recs (Phase 3, gated); the Growth-tab migration (future);
  wording gaps as an aggregate; anything on the job *card* (density feedback).

## How we'll know it worked

The thing that stops happening: a user scanning a flat wall of gaps, unsure
which are real vs. synonym noise and which theme to attack. Success = a user
opens the panel, reads the dominant pillar, names their top clustered gap, and
either dismisses a false positive or grasps a real one to work on.

## Related

REQ-019 (the flat map this evolves), REQ-018 / ADR-021 (per-job enhance, the
complement), ADR-022 (aggregation mechanism, still the base), ADR-023 (clustering
+ category in the classify call), ADR-024 (✕ dismiss persistence), GOV-005
(enhance ≠ fabricate), product vision (gap monetized 3×; persona seed), Growth
tab (Phase-3 milestone).
