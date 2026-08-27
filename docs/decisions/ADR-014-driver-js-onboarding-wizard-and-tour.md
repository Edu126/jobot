# ADR-013: Driver.js onboarding — setup wizard + feature tour + "what's new" bell

Date: 2026-08-26
Status: Accepted
Relates to: REQ-013, REQ-010

## Context

New users land with no guidance. REQ-010 already captured the need to ask
language explicitly on first visit (folded with the geo banner). The resume
is the other blocking setup step. Folding both into one wizard before the
Driver.js tour avoids sending a user on a tour of an app with no CV and no
language set.

## Decision

- **Onboarding wizard (modal, 2 steps):** Step 1 = language picker (UI +
  output, prefill from Accept-Language per REQ-010). Step 2 = resume upload.
  Completing step 2 writes `settings.onboarding_seen = '1'` and supersedes
  the standalone `geo_first_visit_banner.html` flow.
- **Feature tour:** Driver.js fires immediately after the wizard closes.
  3 stops: Jobs search → score badge → Journey pipeline. CDN, lazy-loaded
  only when either gate is open. All copy via `_('key')` — nothing hardcoded.
- **Re-trigger:** A "Get an app tour" button lives in the settings panel.
  For now it re-runs the Driver.js tour only (not the wizard). This also
  resolves the accepted tradeoff — users who dismissed the tour can get it
  back without a support ask.
- **"What's new" bell:** `CHANGELOG_VERSION` server constant vs
  `localStorage('jobot_seen_version')`. Mismatch lights a bell next to the
  settings gear; clicking marks the version seen and opens a brief
  "what's new" popover.

## Alternatives rejected

- Geo banner + language banner as two separate first-visit flows: two banners
  is worse UX than one wizard.
- Running the Driver.js tour before the wizard: a user with no CV and no
  language set would tour a broken app.
- Per-route `is_new_user` threading: `get_setting()` is already a zero-cost
  global — no reason to push the value through every route dict.

## Tradeoff accepted

`onboarding_seen` never auto-resets. Wizard skip = no wizard again, forever.
The "Get an app tour" button in settings covers the re-trigger case; a full
wizard reset can be added later if needed.
