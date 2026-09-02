# REQ-019: The gap map — all your real gaps in one place, not per-JD

Date: 2026-09-01
Source: Eduardo (product architect)
Status: Building — decisions resolved 2026-09-01, ADR-022 for the mechanism

> Evolves REQ-018. Same honesty line (GOV-005). Where REQ-018 answers a gap
> *inside one job's detail*, this makes the gap a **first-class, cross-job
> object** — the surface Eduardo actually wants.

## What they asked for

Eduardo (2026-09-01): *"todo esto para mí debería estar en una sección que
colecta todos los gaps, no por job description."*

## What they actually need

A gap shown per-JD is noise repeated: the same real gap ("no formal PMP",
"missing Kubernetes") reappears across dozens of roles, and a chip in each
job's detail never lets the user *see the pattern*. The product vision says
**"the distance between who you are and the job you want IS the product"**
(gap monetized 3×). A per-JD chip treats the gap as friction; a **collected
gap map** treats it as the thing itself — and it is literally the seed of the
Phase-3 career persona / skill-gap object.

Resolved product decisions (2026-09-01):
1. **Scope = all scored jobs** (cross-search, persona-level — survives between
   searches), not just the open search.
2. **Real gaps aggregate; wording gaps stay per-job.** Real gaps are about the
   *candidate* and cross JDs cleanly ("this blocks you in N of your target
   roles"). Wording gaps are JD-specific (the reword depends on that posting's
   language and is actioned in that tailored résumé) → they stay in the job
   detail (REQ-018 / ADR-021, kept as complement).
3. **Per-job enhance stays** as the complement; the gap map is the hero.

Also folded in (approved 2026-09-01): each real gap carries the **"interviewers
will likely ask about this"** framing (the free Cluster-B ride-along — the
`kind: real` list *is* the interview-objection inventory, per the enhance+prepare
design memo). No new LLM call for that framing.

## Scope guardrails

- **In:** collect gaps from all cached `job_scores` for the current résumé;
  dedupe/cluster; classify the deduped set real-vs-wording **once** (JD-free —
  résumé × gap); show real gaps ranked by how many target roles they block,
  each with an honest suggestion + the interview-objection framing.
- **Out:** course/coaching recommendations (Phase 3, gated); fabricating a
  skill (GOV-005); wording gaps as an aggregate surface (they stay per-job);
  anything on the job *card* (density feedback — the map is its own section).

## How we'll know it worked

The thing that stops happening: a user seeing the same gap over and over with
no sense of *which gap to actually work on*. Success = a user opens the gap map
and can name their top 1-2 real gaps across all their target roles — and acts
on one (edits the résumé, or grasps it as a real skill to build).

## Related

REQ-018 + ADR-021 (per-job enhance, the complement), ADR-022 (aggregation
mechanism), GOV-005 (enhance ≠ fabricate), product vision (gap monetized 3×;
persona seed), milestones Phase 3 (skill-gap object). Callback-signal
instrumentation (approved, gates Cluster B *prepare*) tracked separately.
</content>
