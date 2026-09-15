# REQ-040: A typography system — hierarchy, not just two fonts

Date: 2026-09-15
Status: Implemented on -edu (not merged to main)
Relates to: ADR-046 (the decision), [[design-jobot-v2]], the Sep-2026 design
refresh arc

## The ask (Eduardo, 2026-09-15)

Plus Jakarta Sans read "de juguete" (childish), and titles + body shared one
face so the app had **no visual hierarchy**. Fix typography — but "a real
system, not two fonts + bold": every heading level (h1–h5) should earn its rank
through spacing/size/weight, and the result must NOT look like every other
generic AI-SaaS (Inter/Geist everywhere).

## The need underneath

Hierarchy is what lets the eye triage a dense screen (job cards, funnels,
settings). A single-font, weight-only hierarchy reads flat; and the default
"clean grotesque" pairing is the SaaS uniform we want to avoid to feel
considered/premium (the Wealthsimple-minimalism north star).

## What shipped (see ADR-046)

- **Body = IBM Plex Sans** (humanist character, not the generic Inter look);
  **all headings incl. card titles = Schibsted Grotesk** (clean editorial
  grotesque). Two voices: display = "this is a heading", body = "this is content".
- **A type scale** (L1 `.text-display` 38px → L2 title → h3 card → h4 → L5
  eyebrow), each level tuned on size · weight · line-height · **tracking**. Rule:
  bigger type ⇒ tighter tracking; smaller ⇒ looser.
- **Eyebrow** = `.text-label` redefined (11px, UPPERCASE, +0.13em, muted) → all
  ~63 section labels became consistent kickers via ONE css change.
- **Big metric numbers** (`.hero-num`, `.funnel-count`, `.text-metric*`) use the
  display grotesque at weight 600 — IBM Plex bold numerals read "sad" at size.

## Acceptance / done

- Rendered + screenshot-verified live on **jobbotv2-edu** (cards, /profile,
  /journey): fonts load, eyebrows consistent, metrics look designed.
- Interactive picking done via a temporary in-page "Font Lab" switcher, since
  removed; base.html now loads only the two production families.
- Rejected on the way: Space Grotesk (too quirky/"ewww"), serif-on-display
  (Instrument Serif + Fraunces — considered, premium, but went all-sans), plain
  Inter body (too SaaS).

## Not done / next

- **NOT merged to main** — merging deploys to all 6 user apps at once; do a
  heads-up + decide canary-vs-all first (see the design-refresh memory).
- A broader **/jobs tab rework** was deferred to its own session.
