# REQ-017: The "land it" stage — from applied to offer

Date: 2026-09-01
Source: Eduardo (product architect)
Status: Open — framing note; 4 product decisions RESOLVED 2026-09-01
(see below); first slice broken out to REQ-018 + GOV-005

> Umbrella/stage note, not a single feature. It frames the whole post-apply
> arc so the individual features get their own REQs against a shared spine.
> Follows the solution-architecture practice (capture the ask + the need
> before building).

## What they asked for

In his words (2026-09-01): *"ahora cómo lo enhance (gap analysis), LinkedIn
profile evaluation, cómo lo support — Interview prep, company outlook,
preguntas situacionales relacionadas al fit con el rol, assessment practice
for behavioral tests or logical / problem-solving situations, questions to
ask, risk — everything that could be helpful on this stage."*

The stage after **apply**: help the candidate actually *land* the role.

## What they actually need

Today jobot's funnel ends at `apply`. But applying isn't the goal —
**landing** is. The moment a candidate gets a callback they hit a *second*
blank-page cliff (what do I say, is this company even good, how do I prep),
which is exactly the high-cognitive-load, demoralizing surface the product
vision exists to carry. And answering novel questions in the candidate's own
voice ("why you?", culture fit, situational fit) is the single sharpest
expression of the **candidate-model moat** (product vision: "the central
asset"). So this stage is deeply on-vision for the *moat* — while being in
tension with *sequencing* (below).

The scattered list is really **two clusters with different logic**:

**Cluster A — Profile & gap (always-on, fires for every user today)**
- Gap *enhancement* — we already compute `matched/gaps` at score time; this
  is *closing* the gap, not just showing it (the "close the gap on paper"
  arc; product vision "the gap monetized 3×").
- LinkedIn profile evaluation — be seen · be ranked · be real.
- On-sequence with Phase 1 ("apply better") and seeds the persona.

**Cluster B — Interview readiness (post-callback, "the land-it kit")**
- Interview prep, company outlook, situational fit Qs, assessment practice
  (behavioral / logical / problem-solving), questions to ask, employer risk.
- Fires only *after* a callback → few events today, and we're **not yet
  instrumented** (milestones Phase 0). Building breadth here before the
  callback signal exists is off-sequence. Note: `core/llm/company_research.py`
  already exists as a partial building block for "company outlook".

## The strategic read (honest, for the record)

- Cluster B is the most *defensible* thing we could build (the moat) but the
  most *premature* (post-callback, uninstrumented). Cluster A serves everyone
  now and is on-sequence. → **Recommendation: lead with Cluster A**, capture B
  as the north of where the stage goes.
- **Honesty non-negotiable cuts both ways here:** "company outlook / employer
  risk" is a LinkedIn-can't-build, candidate-side feature (great). The same
  non-negotiable **bans** anything that smells like "cheat the assessment" —
  practice/coaching is on-side, fabrication is not. This needs a GOV note
  *before* Cluster B is built, not after.

## How we'll know it worked (near-term, Cluster A)

The thing that stops happening: a user looking at their `gaps` list with **no
next action**. Success = a user opens the gap-enhance view and makes at least
one concrete change (edits résumé/profile, or acts on a LinkedIn suggestion) —
not a number on a dashboard.

## Product decisions — RESOLVED 2026-09-01 (Eduardo)

1. **Lead = Cluster A** (profile & gap first, not the moat/interview-prep jump).
   On-sequence, fires for all 5 users today.
2. **"Enhance the gap" depth = on-paper only** near-term (reword/surface
   existing skills, honest). The "for real" course/coaching rev-share stays
   deferred to Phase 3 (governance-gated).
3. **LinkedIn eval input = paste** (user pastes profile text). Scrape rejected
   for now — would need its own LinkedIn-ToS/data-governance note.
4. **Cluster B honesty guardrail = write it now.** Done: **GOV-005**
   (enhance ≠ fabricate; practice ≠ cheat; candidate-side employer risk
   allowed) — binding on the whole stage, prerequisite to any B feature.

**First slice broken out → REQ-018** (gap enhancement, on-paper). LinkedIn
profile eval is the next Cluster A slice (its own REQ when it starts).

## Deferred decisions — capture only, decide LATER (Eduardo, 2026-09-02)

- **Gap-detail / defense-hook packaging.** The per-gap extra detail (wording
  reword + real-gap *defense hook*) could be a **paid** feature. Alternative:
  keep the plain gaps free/visible and **relocate** the richer real-gap
  material (defense · improvement · strategy) into a dedicated **"Preparation
  for the interview"** surface (Cluster B) and/or the **candidate-profile
  enhancement** surface — rather than living inline on the results detail.
  Not decided; revisit when the aggregated gap map (REQ-019) and any Cluster B
  scoping are on the table. Ties to "gap monetized 3×" (vision) and the
  enhance→prepare seam (design memo 2026-09-01).

## Related

Product vision (candidate-model moat; gap monetized 3×; on-candidate-side),
`docs/product/milestones.md` (Phase 1 apply-better, Phase 3 persona/education),
GOV-003 (candidate alignment), `core/llm/company_research.py` (existing),
REQ-016 (matched/gaps this builds on). ADRs to follow once a slice is chosen.
