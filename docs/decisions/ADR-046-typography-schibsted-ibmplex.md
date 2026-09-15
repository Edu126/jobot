# ADR-046: Type system — Schibsted Grotesk + IBM Plex Sans

Date: 2026-09-15
Status: Accepted — live on jobbotv2-edu, NOT on main
Relates to: REQ-040, [[design-jobot-v2]], supersedes the Plus Jakarta Sans
choice from the Sep-2026 incremental refresh

## Context

Plus Jakarta Sans read childish, and one font for both titles and body left the
app with no visual hierarchy. The fix had to be a *system* (per-level treatment)
and had to sidestep the generic AI-SaaS uniform (Inter/Geist/Space Grotesk).

## Decision

Two-voice type system:
- **Body/content = IBM Plex Sans** (`--font-sans`); **every heading level incl.
  card titles = Schibsted Grotesk** (`--font-display`). Card titles share the
  heading font on purpose — "heading vs content", not "title vs card".
- **Hierarchy from a scale, not weight alone** (app.css): L1 `.text-display`
  (38px, −0.028em) → L2 `.text-title` → h3 (17px) → h4 → L5 EYEBROW, with the
  rule *bigger ⇒ tighter tracking, smaller ⇒ looser*.
- **`.text-label` is now an eyebrow** (11px, uppercase, +0.13em, muted) so all
  section labels restyle in one place.
- **Big metric numbers** use the display grotesque at 600 (IBM Plex bold read
  heavy at size).

## Alternatives considered

- **Serif-on-display** (Instrument Serif / Fraunces on page titles only) — the
  strongest anti-SaaS move and genuinely liked, but Eduardo chose all-sans.
- **Space Grotesk headings** — rejected: too quirky ("ewww").
- **Inter body** — rejected: too close to the generic SaaS look.
- **Keep Plus Jakarta Sans** — rejected: childish, no hierarchy.

Rollout risk: merging to main deploys to all 6 user apps at once — canary first.
