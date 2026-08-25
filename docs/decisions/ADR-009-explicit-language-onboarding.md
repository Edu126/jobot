# ADR-009: Explicit language onboarding; retire silent auto-detect

Date: 2026-08-25
Status: Accepted
Relates to: [REQ-010](../requirements/REQ-010-explicit-language-onboarding.md),
[ADR-008](ADR-008-prompt-conventions.md),
[llm-surface.md](../architecture/llm-surface.md)

## Context
Language has been an inferred/ambient value since day one: middleware
reads `Accept-Language`, computes a lang, stashes it on the request
context. Some paths also write it into `settings.ui_language` on
first request, which then becomes the persistent source. Different
call sites re-read at different times.

The result is a steady drip of language bugs — one shipped as `PR 1`
per feedback dump for weeks. The 2026-08-25 detour alone produced
three fixes (cache-key, drawer i18n, tojson-in-attr) in the same
class. Root cause is architectural: language is not an explicit user
decision, so the app can't reason about "is this the language the
user meant?" — it just resolves whatever's ambient.

## Decision
1. **On first visit, ask.** Extend the existing
   `geo-first-visit-banner.html` (which already asks country + city)
   to ask UI language + output language ABOVE the geo fields. Default
   the selects to whatever `Accept-Language` suggests, but do NOT
   persist until the user submits the banner.
2. **Post-onboarding, `Accept-Language` is not authoritative.** The
   only code path that reads `Accept-Language` is the banner's
   default suggestion. Middleware reads exclusively from
   `settings.ui_language` after the first save.
3. **The banner is dismissible after fill, never before.** Same
   pattern the geo fields already follow. Blocking modal is
   overkill; a banner that stays until answered is enough.
4. **Existing users don't see it.** Presence check keys off
   `settings.ui_language` being unset — anyone who already has a
   value gets the app as it is today.

## Alternatives considered
- **Modal on first paint.** Louder, but blocks the first look at
  the app and reads as a permissions gate. Banner is friendlier and
  the geo pattern is already familiar.
- **Language picker in the top nav, no banner.** User might never
  click it. The whole point is to force the choice ONCE early.
- **Silent `Accept-Language` forever + fix bugs as they surface.**
  What we've been doing. Cost is one small bug fix + regression
  memory per dump; over months, that adds up to more than the
  onboarding cost.
- **Per-request `Accept-Language` re-detection.** Kills the drift
  in some places by re-introducing it in others (users travel,
  browsers get new locales installed).

## Consequences
- One extra form field on first visit. The four real users are all
  onboarded already, so this only affects the 5th+ user and any
  fresh Fly app deploy.
- llm-surface.md "Known drift risks" section shrinks — three of the
  four remaining risks are downstream of ambient language.
- Middleware simplifies: one read from settings, no
  `Accept-Language` branch. Any test that relied on the header path
  needs updating (probably none today).
- If we later add a third language, the banner already picks it up
  as an option — no code change needed beyond the dict addition
  (see i18n mechanism).
- One class of bug (language ambient/drift) is architecturally
  closed. New language bugs post-ADR-009 are wiring bugs, not
  ambient-state bugs — much easier to reason about.
