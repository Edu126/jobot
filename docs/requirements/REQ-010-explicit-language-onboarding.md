# REQ-010: Explicit language pick on first visit

Date: 2026-08-25
Source: Mehran (2026-08-25 PM feedback dump — bucket B)
Status: Open

## What they asked for

> "Preguntar idioma al primer visit en vez de auto-detectar + overwrite.
> Evita toda esta clase de bugs. Merece REQ + ADR."

Concrete: on first visit, the user picks UI language explicitly.
Auto-detection from `Accept-Language` stops being the source of truth
that gets written back into `settings.ui_language`.

## What they actually need

The last two weeks of language bugs (stale-Spanish gaps, tojson-in-attr,
cache-key drift, tailor drawer in English while UI in Spanish, quick-fill
autofill in English, admin report language mismatch) all stem from
the same root: **language is an inferred/ambient value that different
parts of the app resolve at different times and different ways.**

Fixing each downstream symptom (as PRs 1–6 + the 2026-08-25 detour did)
plugs holes one at a time. The upstream fix is to make language an
explicit user decision, captured once at onboarding, stored in
`settings.ui_language` (+ `settings.output_language`), and never
silently overwritten by browser signals afterwards.

Two properties matter:
1. The user's ONE explicit choice wins forever after — no code path
   that reads `Accept-Language` post-onboarding.
2. Onboarding is fast enough that a user in the wrong language for
   a few seconds isn't the failure mode. Auto-detect is fine as the
   *default suggestion* — just not as an authoritative overwrite.

## How we'll know it worked

- On a fresh app, first visit shows a banner (or modal) asking for
  UI language + output language (defaults suggested from
  `Accept-Language` but not persisted until the user confirms).
- After the user picks, `settings.ui_language` and
  `settings.output_language` are written, banner never appears again.
- `grep -rn 'Accept-Language' ui_web/` returns hits ONLY inside
  the banner/onboarding path — no other code path reads it.
- Existing users (already have `settings.ui_language` set) never see
  the banner; nothing changes for them.
- The whole class of "language drifted somewhere I didn't touch"
  Mehran-style bug reports stops.

## Related

- [[req-007]] (destructive modals) / [[req-008]] (filter reactivity) /
  [[req-009]] (cache-key parity) — the *symptoms* this REQ addresses
  upstream.
- [llm-surface.md](../architecture/llm-surface.md) "Known drift
  risks" — three of the four remaining risks disappear once language
  is explicit.
- ADR-009 (to be written) — decision on onboarding mechanism +
  scope of the "Accept-Language" retreat.
- Fold in with the existing `geo-first-visit-banner.html` flow if
  possible — one banner covers lang + country + city instead of two.
