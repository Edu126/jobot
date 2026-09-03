# REQ-021: Profile shell — persistent resume header, inline ATS insights

Date: 2026-09-03
Source: Eduardo (product architect)
Status: Building — Phase A (shell + IA only); structured Tab 1, languages, and
undo/hidden-gaps carved out to later REQs.

> Evolves the REQ-020 two-sub-tab Profile. REQ-020 gave us the tabs and the
> tactical gap map; it left the **résumé card trapped inside a tab** and the ATS
> detail behind a **modal**. This fixes the shell: the résumé becomes a
> persistent header above both tabs (the source of truth the whole page acts on),
> and the ATS report's actionable fixes surface inline instead of hiding behind
> "See report".

## What they asked for

Eduardo (2026-09-03), reviewing prod on jobbotv2-edu against a to-be mockup:
promote the résumé + ATS + AI first-read into a **compact global header** that
stays visible across both sub-tabs; rename/reorder the tabs to **My Profile &
Skills** | **Market Fit & Gaps**; and fold the "See report" modal into an
**inline ATS report & recommendations card** at the top of Tab 1.

## What they actually need

The current shell breaks the mental model twice. First, the résumé card lives
*inside* the Market-Fit tab, so switching to the parsed-résumé tab drops the very
document the page is about — the source of truth flickers in and out. Second, the
ATS fixes ("add a Certifications section", "DOCX parses more reliably") are the
insights the user came for, yet they sit behind a modal click. Pulling the résumé
out to a persistent header and inlining the fixes gives one stable frame:
*header = how I'm doing · Tab 1 = what I am / what to improve · Tab 2 = where I
stand vs. the market.*

## Resolved decisions (2026-09-03)

1. **Persistent global header.** Résumé identity (filename, Active, words/pages,
   uploaded), the 4-tier ATS score badge, the AI first-read, and Download/Replace
   /older-versions move above the tabs. The score number lives here **once**;
   Tab 1's card must not repeat the big number.
2. **Kill the ATS modal (`atsModal`).** Replace "See report" with an inline
   **ATS report & recommendations** card as Tab 1's opener. It shows the
   actionable fixes + a collapsed `N checks passed` line — not the giant score.
   Escape-hatch removed, not relocated (simplicity over escape hatches).
3. **Density guard for the inline card.** Show top 2–3 fixes; any remainder folds
   under an in-place "N more ˅" (same box, never a new modal/layer). The card
   never grows unbounded regardless of how many issues a résumé has.
4. **Tab 1 keeps today's generic parsed-section readout for now.** No structured
   Executive-Summary / Work-Experience / Skills / Education modules this pass —
   those depend on parse quality we don't have clean (the mockup's own "Detected
   Skills" leaked `Solution`, `Huminity`). Deferred to its own REQ.
5. **Responsive header is a first-class requirement**, not a desktop-only layout:
   the compact row must collapse gracefully at medium widths (no ugly wrap of
   ATS + actions + badges + summary).
6. **Design system, not raw daisyUI.** Reuse the project tokens (`card-quiet`,
   `pill`, `chip`, `text-label`); no dropped-in daisyUI defaults
   (`tabs-lifted`, `badge badge-outline`, etc.).

## Scope guardrails

- **In:** persistent résumé header across both tabs; tab rename/reorder to
  *My Profile & Skills* | *Market Fit & Gaps*; inline ATS report card with
  top-N fixes + "N more" fold + collapsed passed count; removal of `atsModal`;
  responsive collapse of the header.
- **Out:** structured Tab 1 modules (own REQ, blocked on parse quality);
  Add Languages as a real feature; gap-map undo toast + "hidden gaps" restore;
  any change to the gap-map engine itself (REQ-020, ships as-is); the danger
  zone and settings (untouched).

## How we'll know it worked

The thing that stops happening: the résumé context vanishing when the user
switches tabs, and users clicking a modal to find out what to fix. Success = the
résumé + score stay pinned while the user moves between tabs, and the top ATS
fixes are readable without a single click.

## Related

REQ-020 (the two-sub-tab Profile this reshapes; gap map unchanged), REQ-003
(grounded AI first-read shown in the header), ADR-008 (no new LLM call site — this
is pure shell), feedback: simplicity-over-escape-hatches (kill the modal),
feedback: card-density (the inline-card fold guard), product vision (Profile as
the persistent career-persona surface).
