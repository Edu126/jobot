# REQ-017: The "land it" stage — from applied to offer

Date: 2026-09-01
Source: Eduardo (product architect)
Status: Open — framing note; near-term slice scoped, rest deferred

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

## Open product decisions (Eduardo owns these — do NOT build until resolved)

1. **Confirm the lead.** Cluster A (profile & gap) first, or jump to the
   moat feature (interview prep)? Recommendation: A.
2. **"Enhance the gap" depth.** On-paper only (reword/surface existing skills,
   honest) for near-term, vs. "for real" (course/coaching recommendation =
   the Phase-3 education rev-share)? Near-term = on-paper; the rev-share arc
   is later and governance-gated.
3. **LinkedIn eval input.** User pastes their profile text (safe) vs. scraping
   (LinkedIn ToS + data-governance call). Recommendation: paste.
4. **Cluster B honesty guardrail.** Write a GOV note codifying "practice, not
   fabrication" (assessments) + "candidate-side employer risk is allowed"
   before any B feature starts.

## Related

Product vision (candidate-model moat; gap monetized 3×; on-candidate-side),
`docs/product/milestones.md` (Phase 1 apply-better, Phase 3 persona/education),
GOV-003 (candidate alignment), `core/llm/company_research.py` (existing),
REQ-016 (matched/gaps this builds on). ADRs to follow once a slice is chosen.
