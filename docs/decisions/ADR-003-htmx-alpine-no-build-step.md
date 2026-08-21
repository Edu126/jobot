# ADR-003: HTMX + Alpine + CDN Tailwind — no build step

Date: ~2026-07 (documented retroactively 2026-08-21)
Status: Accepted — under active reconsideration if the ceiling gets
hit or if a better-documented / more privacy-mature stack proves
worth the added complexity.

## Context
Solo maintainer + AI-pair setup, POC phase, target: ship fast, iterate
against real users. Every layer of build tooling is a maintenance
surface a single person carries and an extra step the AI pair has to
reason about. UI needs were modest at inception: forms, tables, some
Alpine state for modals and toggles.

## Decision
FastAPI + Jinja2 templates + HTMX (server-driven interactivity) +
Alpine (client-side state) + Tailwind + DaisyUI via CDN. **No build
step.** Any file edit reflects immediately on the running dev server.

## Alternatives considered
- **React / Next.js.** Better component model, huge ecosystem, more
  documented patterns for auth + i18n. Rejected: build step + more
  layers for the AI pair to reason about; each server-side / client-
  side split adds coupling to think about.
- **SvelteKit.** Simpler than React, still has a compile step.
  Rejected on the same "no build step" criterion.
- **Plain Jinja (no HTMX).** Would have worked but every interaction
  becomes a full page reload — the UX suffers.

## Consequences
- Zero build complexity. Any edit propagates instantly. No `npm
  install`, no bundle to reason about, no CDN cache-buster issues
  except our own `static_url()` helper.
- **AI-pair pattern works cleanly:** the whole app is server-rendered
  strings; nothing is behind a compiler. Model can read what will
  render.
- Fewer client-side abstractions available. Complex client-side state
  (multi-step wizards, real-time collab) would strain the pattern.
  The `feedbackWidget()` refactor (extracting Alpine JSON out of
  attribute values into a global function) is an example of the
  pattern showing seams at scale.
- CDN dependencies (Tailwind, DaisyUI, Alpine, HTMX) mean **outbound
  requests on every page load**. Fine for a personal app; would be a
  privacy consideration for a wider audience — the migration path
  would be bundling these locally, not swapping frameworks.
- **Open trade-off:** we've prioritized this for AI-pair velocity, but
  a better-documented stack (e.g. Next.js) might handle the planned
  multi-user + auth phase more naturally. If HTMX+Alpine starts to
  strain under multi-user complexity, a framework migration is on the
  table.
