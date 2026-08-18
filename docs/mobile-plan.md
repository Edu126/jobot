# Mobile — Plan

**Status:** design + implementation plan, synthesized from three parallel
research forks (UI/UX, mobile-dev, general-dev).
**Date:** 2026-08-18
**Related:** [results-page-ux.md](./results-page-ux.md),
[rate-limiting-quotas.md](./rate-limiting-quotas.md),
[working-plan.md](./working-plan.md).

## 1. Framing

**Mobile-as-companion, desktop-as-cockpit.**

Mobile earns its keep for passive-attention moments — triage-skimming
cards on the bus, saving a job for later, marking an application as
"applied," checking if an Expand pass finished. Desktop remains where the
heavy work happens: reading long descriptions side-by-side, tailoring
resumes, downloading DOCX, multi-search comparisons.

The design rule: on mobile a user should be able to *make progress* on a
job search without ever completing anything heavy. Completions happen at
desktop.

If we accidentally end up building "full desktop parity on a phone,"
we've overreached.

## 2. Stack recommendation

**A → B, skip C.**

- **Option A: Responsive polish + `manifest.webmanifest` for install.**
  ~3–4 dev-days. Fixes touch targets, mobile-hostile splits, adds
  add-to-home-screen. No new tooling. **Start here.**
- **Option B: Full PWA with service worker, offline cache, push
  notifications.** +8–12 dev-days on top of A. Justified only if push
  ("expand done", "new high-fit job") becomes a felt need OR MAU > 20.
- **Option C: Native shell (Capacitor / React Native).** Skip until App
  Store presence is a real ask. Cost is real (Apple Developer $99/yr,
  provisioning, review latency, second maintenance surface); value at 3
  users is zero. Revisit at 20+ MAU.

**Why A → B is right for us:**
- HTMX is a server-driven-UI framework; native rewrites throw it away.
- iOS Safari's PWA gap has closed enough in 2026 for our threat model
  (push works since 16.4 for installed PWAs).
- 3-user population doesn't justify store distribution overhead.
- Add-to-home-screen from a PWA covers ~80% of the felt "app on my
  phone" benefit at 0% of the certificate pain.

## 3. The critical gap

The single most-broken thing on mobile today:

`pages/jobs_results.html` line 259 wraps the detail pane in
`<aside class="hidden lg:block">`. **Below 1024px the entire
detail-reading UX vanishes.** Clicking a card still fires
`selectedJob.select()`, HTMX still loads `/jobs/detail/{id}` into
`#job-detail-pane`, viewed still gets marked after 3s — but nothing
renders because the target is CSS-hidden.

Same pattern on `pages/jobs.html`. Both need a mobile bottom sheet
controlled by the same `selectedJob` store. This is PR 1.

## 4. Journey inventory (from UI/UX fork)

Ranked by mobile importance.

| # | Journey | Priority | Trigger |
|---|---|---|---|
| J1 | Triage skim | mobile-primary | Commute, waiting room. Reduce unread pile in 2–5 min. |
| J2 | Save-and-defer | mobile-primary | Promising role during triage; can't tailor now. |
| J3 | Check if Expand tab finished | mobile-primary | Kicked off Expand on desktop; want to see result. |
| J4 | Deep read of one description | mobile-primary | A card looks strong; want to actually read the JD. |
| J5 | Kick off a new search | mobile-OK | Phrase from a conversation; seed a search from mobile. |
| J6 | Tailor a resume | desktop-primary | Read-only preview on mobile; "Continue on desktop" nudge. |
| J7 | Mark application as applied | mobile-OK | Applied via mobile; want to flip status one-handed. |

Mobile-primary flows are the ones we spend UX budget on.
Desktop-primary flows should remain usable on mobile but don't need
polish beyond correctness.

## 5. Cross-cutting patterns worth building

- **Bottom nav** (Home / Jobs / Applications / Profile). Fixed 56px bar
  with safe-area padding for iOS home indicator. Icons + short labels
  (10px). Replaces the current top-nav approach eating vertical space.
- **Bottom sheet for detail pane.** Drag-down or Back-gesture dismiss.
  Native-feeling with CSS transforms + one Alpine store extension.
  Reuses the existing `.drawer-panel` CSS pattern.
- **Swipe-to-save / swipe-to-dismiss on cards.** Where mobile pays for
  itself. Small library (~2KB) or CSS scroll-snap.
- **Haptic feedback** on save/dismiss (`navigator.vibrate(10)`). One
  line, big feel boost on Android; iOS ignores gracefully.
- **Sticky mini-header** (visible/hidden count as a 32px pill on scroll).
- **Skip: pull-to-refresh** — conflicts with native browser PTR on iOS.
- **Skip: long-press for actions** — discoverability tax; swipe covers it.

## 6. Ordered PR plan

Merged from all three forks' recommendations. Each PR is independently
deployable and ships as its own commit.

### Phase 1 — Unblock (mostly PR 1)

**PR 1 — Mobile detail sheet (~1 day). The critical unblock.**
Files: `pages/jobs_results.html`, `pages/jobs.html`, `base.html`,
`static/app.css`, `Alpine.store('selectedJob')`.
- New `.detail-sheet` component: bottom-anchored, `100dvh` with
  `-webkit-fill-available` fallback, drag-handle, backdrop-tap dismiss.
- `selectedJob.select(id)` picks target by viewport width:
  `#job-detail-pane` on ≥lg, `#mobile-detail-body` (in the sheet) on
  smaller. HTMX target swap only; store logic unchanged.
- Sticky bottom action bar in sheet: Save, Tailor, Open posting.
- Enables J1, J2, J4 on mobile end-to-end.

**PR 2 — Touch targets + safe-area + `100dvh` (~2 h).**
Files: `partials/save_action.html`, `partials/job_card.html`,
`base.html`, `static/app.css`.
- Heart button 36 → 44px. "Show description" button `min-h-[44px]`.
- Toast: `bottom: calc(1rem + env(safe-area-inset-bottom))`.
- Drawer + detail sheet: `height: 100dvh` with legacy fallback.
- Chip padding bump: `py-1.5 px-2.5` min so gaps/skills tap cleanly.
- Score badge shrinks 48 → 36px below lg only.

**PR 3 — Poll gating + bfcache fix (~2 h).**
Files: `pages/jobs_loading.html`, `pages/jobs_results.html`,
`base.html`.
- Poll `every 2s` triggers gated by `document.visibilityState` so
  hidden tabs don't hit the server every 2s on cellular.
- `window.addEventListener('pageshow', e => if (e.persisted)
  htmx.process(document.body))` in base.html — score-batch resumes
  after iOS Safari bfcache restore.
- Adaptive delay based on `navigator.connection.effectiveType`:
  score-batch chain slows from 200ms → 1s on 2g/slow-2g.

### Phase 2 — Make it feel like an app (mobile-primary polish)

**PR 4 — Bottom nav (~half day).**
New `partials/mobile_nav.html`. Fixed bottom bar, four tabs, iOS
safe-area padding. Body gets `padding-bottom` for the bar height so
cards aren't clipped. `lg:hidden` — desktop keeps its top nav.

**PR 5 — Session-cookie identity (~1 h). CGNAT fix.**
`ui_web/middleware.py`: set a `sid` cookie on first hit
(`SameSite=Lax`, `Secure`, `HttpOnly`, 90-day). `get_identity(request)`
prefers `sid` over IP. Mobile users on the same carrier NAT stop
sharing rate-limit buckets. Backward compat: existing IP-keyed
`rate_limits` rows age out via normal expiry.

**PR 6 — Manifest + Add-to-Home-Screen (~half day).**
`ui_web/static/manifest.webmanifest` with icons, theme, `display:
standalone`. `<link rel="manifest">` + `apple-touch-icon` in
`base.html`. iOS-only one-time onboarding hint ("Tap Share → Add to
Home Screen") triggered by user-agent sniff on second session, dismissible.

**PR 7 — Swipe-to-save on cards (~half day).**
Left / right swipe gestures on `article.job-card` via a tiny hammer
alternative. Swipe-right → save (opens confirm toast with Undo).
Swipe-left → new `dismissed` job status (see §7 open decisions).
`navigator.vibrate(10)` on gesture completion. Respects
`prefers-reduced-motion`.

### Phase 3 — Full PWA (only if push/offline become felt needs)

Deferred. Concrete steps when we decide:
- `ui_web/static/sw.js` service worker (Workbox or hand-rolled).
- Cache strategy: static assets cache-first, `/jobs/detail/{id}`
  stale-while-revalidate, POSTs network-only with Background Sync queue.
- IndexedDB mirror of viewed + score subset for offline browse.
- VAPID push registration + backend endpoint to store subscriptions.
- Push triggers: expand-done, new-high-fit-job daily digest.

Estimate: 8–12 dev-days total for Phase 3, spread across ~3 PRs.

## 7. Open decisions

Questions the user must resolve before Phase 2 lands. Each has a
recommendation.

| # | Question | Recommendation |
|---|---|---|
| 1 | Dismiss vs. delete on swipe-left? | **Yes, add a `dismissed` job status** — persistent, filterable, undo-able. Purer than piggybacking on viewed state. |
| 2 | On mobile, keep Expand's new-tab behavior, or route to an in-app "recent expansions" list? | **In-app list on mobile only**, via user-agent branch. Desktop keeps new-tab. Mobile browser tabs are less discoverable and iOS PWA standalone ignores `target="_blank"`. |
| 3 | PWA install prompt: how aggressive? | **Once, after the user's second J1 triage session** — a natural "you're using this like an app" moment. |
| 4 | On mobile, where does description lazy-load land? | **Bottom sheet** (comes for free from PR 1) — not appended-to-card. Solves the "5KB pushes everything below the fold" problem. |
| 5 | Bottom nav labels: with or without? | **Icons + labels** (10px). Extra 4px is worth it for a first-time user. |
| 6 | Do we allow tailor generation on mobile, or force "Continue on desktop"? | **Allow generation, silently block DOCX download on iOS**. The Files-app dance on Safari is uniformly bad; user can still preview text. |

## 8. Explicit non-goals

- **Native app store distribution.** Cost real; value at 3 users zero.
  Revisit at 20+ MAU.
- **Offline resume editing.** Resumes are big and structured; offline
  conflict resolution across phone + laptop is nasty. Keep online-only.
- **Push notifications before Phase 3.** Dead-end work in a non-PWA.
- **SMS 2FA / biometric auth pre-auth.** No accounts to protect yet.
- **Camera / share-sheet plugins.** File input handles both; native
  plugins would need Capacitor.
- **Voice search / voice-tailored resumes.** Zero user pull.
- **Pull-to-refresh.** iOS Safari native PTR conflicts with app PTR.
- **In-app drag-and-drop Applications kanban on mobile.** Desktop-primary
  flow. Mobile gets a simple status list.

## 9. What NOT to touch (from the codebase audit)

- **The tailor drawer** (`base.html:490+`) — already responsive, don't
  rework.
- **The mobile nav drawer collapse pattern** — clean already.
- **The `lg:hidden` job-card action row** — correct split; don't try to
  unify with desktop.
- **`journey.html`'s CSS breakpoint** — battle-tested; the pattern to
  copy elsewhere.
- **`applications.html`'s `grid-cols-2 sm:grid-cols-4`** — cleanest
  responsive pattern in the repo.
- **Score badge visual size on desktop.** Only shrink on mobile.

## 10. Rough timing

| Phase | PRs | Days | Ship condition |
|---|---|---|---|
| 1 — Unblock | PR 1, 2, 3 | ~1.5 dev-days | Ship whenever. |
| 2 — Feel-like-an-app | PR 4, 5, 6, 7 | ~2 dev-days | After Phase 1 lives for a few days. |
| 3 — Full PWA | (deferred) | ~8–12 days | Only if push/offline become felt needs. |

Total for Phases 1+2: ~3.5 dev-days, spread across 7 PRs.

## Sources

Synthesized from three parallel research forks on 2026-08-18:

1. **UI/UX fork** — journey inventory, wireframes, touch-target audit,
   cross-cutting mobile patterns.
2. **Mobile-dev fork** — stack recommendation (A→B, skip C), iOS Safari
   quirks, offline cache strategy, CGNAT / rate-limit implications.
3. **General-dev fork** — file-by-file codebase audit, cross-cutting
   HTMX/Alpine concerns on mobile, bfcache handling, first 3 PR-sized
   changes.
