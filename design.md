# Jobot — Design System Backbone

> **The authoritative design reference for Jobot v2.** All UI work (human or agent) checks against this doc instead of re-deriving. Rules here override ad-hoc choices in `ui_web/static/app.css`; where the CSS and this doc disagree, the doc is the target and the CSS is debt to be reconciled (see §12 Audit backlog).
>
> **Status:** v1 · 2026-09-18 · supersedes scattered rules in design memory + CSS comments.
> **Companion:** [`docs/product/design-system-strategy.md`](docs/product/design-system-strategy.md) (the research + decisions behind this) · [ADR-046 typography](docs/decisions/ADR-046-typography-schibsted-ibmplex.md)
> **For AI pairs:** before adding any page/partial/component, read §2 + §2A (Principles, Editorial doctrine), §7A (Surfaces — tinta, no contorno), §9.0 (the macro kit) and §11. Build with `ui_web/templates/macros/ui.html`; never hand-draw a header, card, notice, button or chip. `scripts/lint_ui.py` (ratchet) fails the build on new hand-drawn UI. Never introduce a token value not defined here.

---

## 1 · What Jobot should feel like

Calm, editorial, confidence-building — **never** dashboard-y, Bootstrap-y, or generic-AI-SaaS. Job hunting is emotionally loaded (rejection, self-doubt, decision paralysis); the interface does emotional scaffolding. Visual noise reads as anxiety. We earn "expensive" the way our references do — **through what we refuse to do**: one disciplined accent system, a tiny set of radii, earned depth, soft motion, and typography carrying the hierarchy.

Two surfaces, two postures:
- **Product app** (job cards, forms, nav, tabs, drawers) — disciplined, quiet, two accents only.
- **Marketing surfaces** (welcome / landing / benefit cards) — expressive, allowed the secondary palette + gradient. Never bleeds into the product.

---

## 2 · Principles (the laws)

1. **Accent is punctuation, never a wash.** Green + salmon mark where the eye should go; they are not backgrounds. (Learned the hard way — salmon body-wash was rejected; validated by all three references.)
2. **Two accents, hard-scoped.** Green = structure/CTAs. Salmon = top-match/celebration only, **≤1 salmon element per view**.
3. **Tinta, no contorno.** Things separate by a warm-grey *fill*, never by an outline drawn around them; type does the rest. Shadow is reserved for genuinely floating surfaces. No shadow soup, no box-in-box. (§7A)
4. **Type carries hierarchy.** Size · weight · tracking · leading — not background fills, not color, not bold-vs-regular.
5. **Soft motion.** Restrained, purposeful, `prefers-reduced-motion`-safe. No infinite loops except one loading state.
6. **Restraint = cohesion.** A tiny fixed set of radii, one shadow family, one color model, repeated everywhere. Predictable because it never breaks.
7. **Filled CTAs for high-stakes actions.** We are a product for anxious users — primary actions are obvious, not ghost links.
8. **One color model: OKLCH.** No raw HSL, no hex in components. Everything references a token.

---

## 2A · Editorial doctrine — what earns a place (information design)

§2 governs *how it looks*. This governs *what earns a place, and with what weight* — the half that, missing, let competent styling paper over unresolved information architecture (the "looks like a student made it" failure). Same tier as §2; these are laws.

1. **One job per screen.** Before designing, state the screen's job in one sentence and its single primary action. Anything that doesn't serve that job is cut. (Brief's job: *"in 10s know where you stand for this interview; then go practice."*)
2. **Answer first, evidence below.** A screen opens with the at-a-glance *answer* to its job; the detail that justifies it comes under.
3. **A summary synthesizes; it never echoes.** The top layer must *compute* something the detail doesn't give at a glance — a verdict, the single gap, a distribution. If it shares the same tokens as a layer below (same names, bands, words), it is failing → rebuild or delete it. (Learned the hard way — the Brief showed the same four competencies as oversized chips *and* as cards; the echo read as noise.)
4. **Subtract first.** Every element justifies its existence or dies. Design advances by *removing*, not adding. Accretion across rounds is the failure mode; when in doubt, cut.
5. **Secondary looks secondary.** Supporting content carries clearly lower weight (size, color, position) and never pretends to be co-equal with the core. A weak side column styled like the main column is a lie about importance.
6. **The primary action stays in reach.** One primary action per screen, persistent — never buried below a scroll.
7. **Right component for the datum.** A pill is a 1–2-word tag; long names/phrases do not go in pills. Each datum wears the shape its size and role demand — component misuse reads as amateur instantly. **One content surface:** content blocks use `.card-quiet` (grey `--surf-1` field on the white page, §7A); primary vs secondary comes from heading size + position, *never* a second box style. The one exception is `ui.callout` (green tint + rule) for THE answer on a screen — max one per view. Footnotes/caveats are plain muted text, not cards. Three box styles on one screen = the repeat failure.
8. **Legible measure and contrast.** Reading text ≤ ~70 characters wide; muted ink is for support only — never the main content, never section headings.

**Process rule (people + agents):** every redesign opens by stating the screen's job and proposing *what to cut*, before any visual proposal. A design agent is asked *"what's redundant, and why does this screen exist?"* — never *"give me 3 styling options."* Styling-first briefs produce styling-first bloat.

---

## 3 · Audit summary (health → target)

Rated against this backbone. 🟢 healthy · 🟡 drift · 🔴 debt. Actions tracked in §12.

| Dimension | Today | Target | State | Priority |
|---|---|---|---|---|
| **Typography** | IBM Plex + Schibsted, L1–L5 scale, unified eyebrow | Keep as-is (§5) | 🟢 | — |
| **Accent discipline** | Salmon sprawls (chip, breathe-pill, glow, gradient, seg-tab light) | Green structural + salmon ≤1/view (§4.1) | 🔴 | P1 |
| **# of accents** | 2 (green + salmon) | 2, hard-scoped | 🟡→🟢 | P1 |
| **Color model** | OKLCH tokens **+ raw HSL** in score/chip/verdict | OKLCH only (§4.5) | 🔴 | P1 |
| **Secondary/marketing palette** | none (one-off colors) | Full-6 sanctioned palette (§4.2) | 🟢 new | — |
| **Radius** | 8+ values | 5-step scale (§6) | 🔴 | P2 |
| **Shadow** | ~10 bespoke; "never shadow cards" already broken | 4-step elevation (§7) | 🔴 | P2 |
| **Motion** | 11 keyframes, several infinite, ad-hoc timings | Duration/easing tokens; no infinite loops (§8) | 🟡→🔴 | P2 |
| **Text tint** | Scattered opacities (/0.72, /0.6, /0.55…) | 4-step neutral ramp (§4.4) | 🔴 | P2 |
| **Buttons** | No `.btn-*` system; one-off black CTA | Variant set (§9.1) | 🔴 | P1 |
| **Information architecture** | Additive rounds; summary echoes detail; pills misused for long names | One job/screen; synthesize-don't-echo; subtract (§2A) | 🔴 | P1 |
| **Governance** | Rules in CSS comments + memory | This doc + component inventory (§9) | 🟢 now | — |

**One-line diagnosis:** *typography is already reference-grade; everything else needs restraint + a single source of truth. This doc is that source; §12 is the paydown plan. The doc was also missing an editorial half (§2A) — styling can't fix unresolved information architecture, which is why the same "student-made" problem recurred across rounds.*

---

## 4 · Color

### 4.0 Green scale — 12-step, generated with Radix (accessible foundation)
Tool-defined (not hand-rolled): [Radix custom palette](https://www.radix-ui.com/colors/custom?accent-light=004E3D&gray-light=8A8578&bg-light=F5F4F0) with **accent = #004E3D**, gray = #8A8578 (warm stone), background = #F5F4F0 (linen). It kept our hunter green as **step 9 (solid)** and built an accessible ramp around it. This is the source of truth for green; the semantic tokens below are aliases into it.

| Step | OKLCH (hue 171.8) | Radix role → Jobot use |
|---|---|---|
| 1 | `95.7% 0.008 171.8` | app bg tint |
| 2 | `94.3% 0.015 171.8` | subtle bg |
| 3 | `91.8% 0.043 171.8` | component bg — **green chip/pill fill** |
| 4 | `88.9% 0.068 171.8` | hovered component bg |
| 5 | `85.3% 0.088 171.8` | active / selected bg |
| 6 | `80.7% 0.104 171.8` | subtle border |
| 7 | `74.6% 0.110 171.8` | border / **focus ring** |
| 8 | `66.9% 0.110 171.8` | strong border |
| **9** | `37.8% 0.073 171.8` | **solid — `--p` primary** (≈ #004E3D) |
| 10 | `44% 0.110 171.8` | solid hover — **`--pf`** |
| 11 | `46% 0.110 171.8` | low-contrast text on light |
| 12 | `35% 0.073 171.8` | high-contrast green text |

Success/matched greens (§4.5) draw from steps 3 (tint) + 11/12 (ink) of this same scale — so "success green" and "brand green" are finally one family.

### 4.1 Layer 1 — Product accents (the working UI)
| Token | OKLCH `L C H` | ≈hex | Role |
|---|---|---|---|
| `--p` primary (hunter green) | `35.5% 0.075 170` | #004E3D | nav, primary CTAs, links, save, active, structure |
| `--pf` primary-focus | `30% 0.070 170` | — | pressed/hover-dark |
| `--a` accent (salmon) | `72% 0.17 30` | ~#FF7F6B | **top-match / celebration ONLY**, ≤1/view |
| `--af` accent-focus | `65% 0.18 28` | — | salmon text/emphasis on light |

**Salmon rule (hard):** allowed on the top-match badge, a celebration/offer pill, and the "eye lands here" moment — *one* per view. **Forbidden:** as a card/section background, decorative dots, breathing glows, gradient filler, button fills, or generic emphasis. When in doubt, salmon does **not** go there.

### 4.2 Layer 2 — Secondary palette (marketing surfaces only) — **CHOSEN: Full 6**
For welcome/landing/benefit cards/empty-state art. Each hue is a **tint** (card bg) + **ink** (heading/icon). Low chroma so a row reads coordinated. **Never** enters the product chrome.

| Token | Tint (bg) | Ink (text/icon) | Character |
|---|---|---|---|
| `--sec-sage` | `95% 0.02 150` (#E9F0E8) | `40% 0.06 155` (#3A5A46) | green family — bridges to primary |
| `--sec-clay` | `94% 0.03 40` (#F6E7DE) | `46% 0.09 40` (#9C5A44) | warm terracotta — salmon's grown-up sibling |
| `--sec-honey` | `95% 0.04 85` (#F5ECD6) | `48% 0.07 75` (#8A6A34) | warm gold / ochre |
| `--sec-teal` | `94% 0.02 220` (#E1EAEE) | `42% 0.06 230` (#3E5A6B) | cool counterpoint |
| `--sec-plum` | `94% 0.02 330` (#EEE6EC) | `44% 0.07 340` (#7A4E68) | soft berry |
| `--sec-stone` | `94% 0.006 80` (#ECE8E1) | `40% 0.01 70` (#5E5A52) | hue-neutral warm |

Card body text on tints = `--n-6`; card border = ink at 16% alpha. Benefit grids cycle the six in order.

### 4.3 Gradients — **CHOSEN hero: Soft**
| Token | Value | Use |
|---|---|---|
| `--grad-soft` *(hero + section wash)* | `linear-gradient(160deg, oklch(96.7% 0.005 95) 0%, oklch(92% 0.035 150) 100%)` | **the chosen landing hero** (linen → faint sage, dark text) + quiet full-width section bands |
| `--grad-brand` *(reserved)* | `linear-gradient(135deg, oklch(35.5% 0.075 170) 0%, oklch(52% 0.10 120) 52%, oklch(70% 0.17 34) 100%)` | high-energy moments only (launch banner, celebration) — **not** the default hero |

Rules: at most **one** gradient per page; never behind body copy; dark text on `--grad-soft`, white text on `--grad-brand`.

### 4.4 Neutral ramp (warm stone — Radix-generated, hue 89)
From the **same Radix run** (gray = #8A8578 warm stone). All share hue ~89° at low chroma, so they harmonize with linen instead of going cold-grey. This fixes the old ink token that was accidentally cool (hue 265). **Text color and muted surfaces come from this ramp — never ad-hoc `/0.72` opacities.**

| Token | OKLCH | ≈hex | Radix gray step → Use |
|---|---|---|---|
| `--n-0` | `100% 0 0` | #FFFFFF | cards, lightest surface |
| `--n-1` | `96.7% 0.005 89` | #F5F4F0 | 1–2 · page (linen) |
| `--n-2` | `94.3% 0.005 89` | #ECE8E1 | 2–3 · soft section fill |
| `--n-3` | `91.4% 0.005 89` | #E5E1D7 | 3 · hairline border |
| `--n-4` | `80.1% 0.013 89` | #C9C3B6 | 7 · muted lines, disabled |
| `--n-5` | `55.1% 0.020 89` | #8A8578 | 10 · meta / tertiary text |
| `--n-6` | `44.6% 0.016 89` | #6C665C | 11 · secondary text |
| `--n-7` | `24.3% 0.017 89` | #262420 | 12 · body / primary ink (now warm) |

**Text tint scale:** body = `--n-7` · secondary = `--n-6` · meta = `--n-5` · disabled = `--n-4`. That's the whole "washed text" answer — pick a step, don't invent an opacity.

### 4.5 Semantic + verdict scale (OKLCH — retires the raw HSL)
Data colors we can't avoid as a product (fit verdicts, status). One model, disciplined.

| Purpose | Tint | Ink |
|---|---|---|
| success / strong_fit / workable | `94% 0.04 165` | `38% 0.09 165` |
| warning / stretch | `93% 0.05 75` | `44% 0.10 60` |
| danger / poor_fit | `94% 0.04 25` | `50% 0.15 25` |
| info | `93% 0.04 235` | `45% 0.10 240` |
| none / neutral | `--n-2` | `--n-5` |

Migrate `.score-badge*`, `.chip-*`, `.verdict-pill*`, `.score-ring*` off `hsl(...)` onto these. The "green" is now one green.

---

## 5 · Typography (from ADR-046 — healthy, do not churn)

- **Body:** IBM Plex Sans (`--font-sans`). **Display/headings:** Schibsted Grotesk (`--font-display`). Two voices on purpose (heading vs content). Resume DOCX export = Calibri, **separate — never touch when editing UI type.**
- Hierarchy = a scale, not bold-vs-regular. Bigger → tighter tracking; smaller → looser.

| Level | Class / tag | Size | Weight | Tracking |
|---|---|---|---|---|
| L1 Display | `.text-display` / h1 | 38px | 600 | −0.028em |
| L2 Title | `.text-title` / h2 | 24px | 600 | −0.018em |
| L3 Heading | h3 | 17px | 600 | −0.011em |
| L4 Subhead | h4 | 15px | 600 | −0.004em |
| L5 Eyebrow | `.text-eyebrow` / `.text-label` / h5 | 11px UPPER | 600 | +0.13em |
| Metric | `.text-metric` | 36px | 600 | −0.02em, tabular |

Big numerals wear the display face (IBM Plex bold numerals read "sad" large). One eyebrow rule styles all ~63 section labels — change once, changes everywhere.

---

## 6 · Spacing & shape

- **Spacing base = 4px.** Scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64. Section rhythm on marketing pages: 64–80px vertical; card internal 16–24px.
- **Container widths (one per screen — pick from this set, never ad-hoc `xl`/`2xl`/`4xl`):** `max-w-5xl` (form-heavy / **workspace**: Applications, Profile, **all of Prep — Home, New Interview, Brief, Get Ready, Story Bank, editor, Practice, Feedback**) · `max-w-7xl` (split-viewport: Jobs) · `max-w-3xl` (focused single-task / loaders / transient status: the Prep **generating** + **voice-capture** + **consent** + "building feedback" screens only). **A module is coherent when every content screen shares ONE width** — the header spans `max-w-7xl`, so a content column narrower than `5xl` reads as lost/off-centre under it. Prep learned this the hard way (was a mix of `xl`/`2xl`/`3xl` → looked incoherent, fixed 2026-09-21).
- **Radius — the fixed set (collapse everything to these):**

| Token | Value | Use |
|---|---|---|
| `--r-sm` | 0.375rem (6px) | chips, badges, small controls |
| `--r-md` | 0.5rem (8px) | buttons, inputs, tiles, seg-tabs interior |
| `--r-lg` | 0.75rem (12px) | cards, panels, drawers, modals, score-hero |
| `--r-xl` | 1rem (16px) | large marketing/benefit cards, bottom sheets |
| `--r-pill` | 9999px | pills, avatars, toggles |

No value outside this set. (Migrate job-card 0.6rem→`--r-md`, results-panel 16px→`--r-xl`, calendar 6px→`--r-sm`, etc.)

---

## 7A · Surfaces — "tinta, no contorno" (2026-09-28, supersedes the hairline-border default)

Eduardo compared the component-kit artifact (white page; the recommendation = green tint + 3px rule, no border) against the app's components (grey plate, white outlined cards, selected card = dark green border + ring + shadow, every chip/tab/field outlined) → the app read high-contrast and "everything floats". The rule that came out of it:

**Page = pure white. Things separate by a warm-grey FILL, never by an outline. States step greyer. Green is a signal, never a border.**

| Level | Token | Value | Use |
|---|---|---|---|
| 0 | `--b1` | white | the page; text sits directly on it |
| 1 | `--surf-1` | `oklch(var(--n-7) / .035)` | resting cards, notices, chips, secondary buttons |
| 2 | `--surf-2` | `oklch(var(--n-7) / .06)` | hover; tab track; search field; neutral chips |
| 3 | `--surf-3` | `oklch(var(--n-7) / .085)` | selected / active — **plus** the 3px green leading bar (`--lead-bar`) |
| ★ | `ui.callout` | `oklch(var(--p) / .07)` + 3px rule | THE answer / recommendation on a screen — max one per view |

- Alpha over white, so levels stack correctly when nested (a chip inside a card is still one step darker).
- **Borders:** only a hairline *between* things (list rows, search-bar segments, section rules). Never *around* a card, chip, tab or button. Keep `border: 1px solid transparent` where needed so box sizes don't shift.
- **Selection** = `--surf-3` + green leading bar. No outline, no ring, no shadow.
- **Hover** only on things you can act on (links, buttons, `hx-get`, `@click`). A static content card never reacts.
- **The one resting shadow:** the white thumb of the active `.seg-tab`, because it physically sits on the grey track.

## 7 · Elevation & depth

Depth is earned. Default is **flat, no border** (§7A). Shadow only on genuinely floating surfaces. Warm/green-tinted, never grey-black.

| Token | Value | Use |
|---|---|---|
| `--elev-0` | none | default; hairline border does the work |
| `--elev-1` | `0 1px 2px oklch(var(--p) / .05)` | small floating controls (active seg-tab thumb) — **not** resting cards (§7A) |
| `--elev-2` | `0 10px 25px -18px oklch(var(--p) / .28)` | popovers, typeahead |
| `--elev-3` | `0 24px 60px -24px oklch(var(--n-7) / .28)` | modals, drawers, overlays |

Rules: never stack beyond one token; never on inline/text elements; selection is shown by `--surf-3` + the **green leading bar** — never a border, ring or heavier shadow.

---

## 8 · Motion

Soft, purposeful, accessible. **Every animation guarded by `@media (prefers-reduced-motion: reduce)`.**

- **Duration tokens:** `--dur-1` 120ms (micro/hover), `--dur-2` 200ms (state change), `--dur-3` 320ms (enter/exit).
- **Easing tokens:** `--ease-out` `cubic-bezier(.22,.61,.36,1)` (default), `--ease-spring` `cubic-bezier(.34,1.56,.64,1)` (playful — save/heart only, sparingly), `--ease-in-out` (the one loading loop).
- **Allowed patterns:** one arrival (`cascade`/`detail-in`), one selection (leading-bar grow), one loading loop (the overlay). Hover = one surface step greyer (§7A) — no lift, no shadow.
- **Banned:** infinite loops on resting UI (`pillBreathe`, `geo-banner-pulse`, `pill-accent` breathe) — retire or make finite/one-shot. No animation without a reduced-motion guard.

---

## 9 · Components

### 9.0 The macro kit — `ui_web/templates/macros/ui.html` (2026-09-28)

**Why it exists:** tokens alone didn't hold the style. Every new screen re-drew its header, card, notice and buttons from raw Tailwind (1 macro for 85 templates; 7 `<h1>` variants, 11 `<h2>`, 44 button class strings, 47 hand-built cards, 10 text opacities). The macros are the ONLY sanctioned way to draw these pieces. Change the look in `app.css`, never with utilities at the call site.

```jinja
{% import "macros/ui.html" as ui %}
```

| Macro | Signature | Replaces |
|---|---|---|
| `page_header` | `(title, lede=None, eyebrow=None, back=(href, label), size='md'\|'lg')` + optional call block for actions | hand-classed `<h1>` + back link + subtitle |
| `section` | `{% call ui.section(eyebrow, title=None, action=(href,label)) %}` | ad-hoc `<h2>` / `uppercase tracking-*` kickers |
| `card` | `{% call ui.card(href=None, selected='alpineExpr', pad='sm'\|'md'\|'lg'\|'none', tag='div', attrs={}) %}` | `rounded-xl border border-base-300 bg-base-100 …` |
| `callout` | `{% call ui.callout(eyebrow=None) %}` | — (Level ★: THE answer, ≤1 per view) |
| `notice` | `{% call ui.notice(icon=None) %}` | outlined info/warning boxes |
| `button` | `(label, variant='primary'\|'secondary'\|'ghost'\|'danger'\|'danger-solid', size='sm'\|'md', icon, icon_after, href, type, attrs={})` | 44 `btn …` class strings |
| `chip` | `(label, kind='neutral'\|'suggest'\|'matched'\|'gap'\|'accent'\|'applied'\|'fresh'\|'viewed'\|'dismissed', icon, title)` | inline-`hsl()` chips |
| `datum` | `(value, label, unit=None, note=None, size='md'\|'lg')` | stat tiles |
| `verdict` | `(verdict_key, score=None, label=None, note=None)` | wraps `macros/ring.html` |
| `seg_tabs` / `utabs` | `(items=[(value,label,icon)], model='alpineVar')` | copy-pasted `:class` ternaries |
| `empty_state` | `(sentence, hint=None, action=(href,label,icon), icon=None)` | illustration + giant-button empties |
| `split_workspace` | `{% call(pane) ui.split_workspace() %}` — body rendered for `'list'` and `'detail'` | the ADR-012 grid |

- `attrs` passes hx-*, `@click`, `:class`, `x-show`, `data-*`, `aria-*` straight through — HTMX/Alpine wiring stays at the call site.
- Text ramp: `text-body-muted` (secondary) · `text-subtle` (meta, hints) · `text-faint` (separators, decorative icons). Never `text-base-content/NN`.
- Page width comes from `{% block container_class %}` — one of the three in §6.
- **Lint (ratchet):** `.venv/bin/python scripts/lint_ui.py` — fails on any (file, rule) count above `scripts/lint_ui_baseline.json` (raw colours, text opacities, ad-hoc radius, `text-[..]`, outlined boxes, hand `<h1>`, `btn` without variant). Fix debt → `--update` to lower the baseline. Test: `tests/test_ui_lint.py`.

Inventory of the ~30 existing components with their canonical rules. **Buttons first** — they were the gap that started this.

### 9.1 Buttons (the reconciled variant set)
Retires the one-off **black-background CTA** (map "See my matches" → `.btn-primary`).

| Variant | Look | Use |
|---|---|---|
| `.btn-primary` | `--p` fill, white text, `--elev-1` | the one primary action per view |
| `.btn-secondary` | outline (`--n-3` / current), transparent | secondary action |
| `.btn-quiet` | text-only, underline on hover | tertiary / low-stakes |
| `.btn-danger` | danger-ink text / tint bg | destructive (delete, withdraw) |

- Sizes: `sm` (0.5rem 1rem), `md` (0.72rem 1.5rem). Radius `--r-md`. Focus ring = `--p` at 40%.
- **Salmon is never a button fill.** No black button. Icon-only actions use `.btn-quiet` + aria-label.
- **One primary per view, and in job surfaces it is always Tailor.** On job cards + job detail, **Tailor** (✨ magic-wand) is the single green `.btn-primary` — the natural next step after reading a posting. Apply directly / View / Prep / Mark-as-Applied are all `.btn-quiet`. (Fixed 2026-09-19: previously Apply stole the green when a direct-apply URL existed, and the card had two greens.)

### 9.2 Surfaces & cards
- `.card-quiet` — `--surf-1` fill, **no border, no shadow**, `--r-lg`; hover (interactive only) → `--surf-2`; `--selected` → `--surf-3` + green leading bar (§7A).
- `.job-card` — `--surf-1` grey field, no border, no shadow; hover → `--surf-2`; selected → `--surf-3` + the full-height green **leading bar** that grows in (`::before` scaleY). (2026-09-28: dropped the green border + ring + shadow selection — it was the loudest element on screen.)
- `.results-panel` — **visually removed** (transparent; class kept only for the grid layout). The Top-matches/Saved workspace is open, cards sit directly on the page.
- `.score-hero`, `.modal-panel`, `.drawer-panel`, `.mobile-detail-sheet`, `.settings-panel`, `.whats-new-panel` — all `--r-lg`, `--elev-3` when floating.
- `.bene` (marketing) — secondary-palette tint card, `--r-xl`; icon+title in hue ink, body `--n-6`.

### 9.3 Pills, chips, badges
- `.pill` (+ `.pill-dot .live/.warn`) · semantic `.pill-success/warn/danger/info/neutral` · `.pill-celebration` (salmon — the sanctioned salmon moment).
- `.chip-matched` (success) / `.chip-gap` (warning) / `.chip-neutral` — **migrate to OKLCH scale §4.5.**
- `.score-badge` / `.score-ring` / `.verdict-pill` — verdict tints from §4.5, radius `--r-sm`/`--r-lg`.

### 9.4 Navigation & tabs
- `.nav-tab` — text + animated green underline (Wealthsimple). `.utabs/.utab` — lighter section switch (inactive `--n-5`, active ink + green underline).
- `.seg-tabs/.seg-tab` — affordance ladder rest→hover→active; active = white + `--elev-2`. **Remove the salmon "top light"** inset (accent discipline) — use green.

### 9.5 Data & journey
- `.journey-rail` (sticky steps, active dot — green, not salmon), `.kanban-column`, `.funnel-*` (green intensity ramp), `.calendar-*` (contribution grid), `.typeahead-*`, `.jobot-searchbar` (airline-style focus ring), `.lang-pill`.

### 9.6 Feedback & loaders
- `.toast` (bottom-right), `.geo-loader` (overlay — the *one* allowed infinite loop), `.nav-progress` (top ribbon — recolor off the salmon gradient to green), `.feedback-fab` (green pill).

---

## 10 · Layout & surfaces

- **Page = pure white `--b1`; cards = grey `--surf-1` fields on it (§7A).** (Was: off-white page + white outlined cards — superseded 2026-09-25/28; the off-white read "cream", the outlines read high-contrast.) **No background wash/gradient** — the old radial green "cloud" was removed 2026-09-19 (read dirty/uneven); the page is flat and clean. Never reintroduce a full-bleed color wash.
- **Split viewport** (email-app): `grid lg:grid-cols-2`, list left / detail right; click → `Alpine.store('selectedJob').select(id)` → HTMX loads `/jobs/detail/{id}`.
- **Dual-scroll** (ADR-012): `app-shell` fixed shell OR bounded block; `min-height:0` on every link in the chain is load-bearing.
- Generous whitespace: `mb-8` between sections, `mb-4` between related blocks. Never DaisyUI `alert`/`stats`/`tabs-boxed`/`hero`. Emoji only in row-level data, never headings.

---

## 11 · Do / Don't

**Do**
- Use green for structure/CTAs; reserve salmon for one top-match/celebration beat.
- Pull every color from a §4 token; every radius from §6; every shadow from §7.
- Let type size/weight carry hierarchy; use the eyebrow for section labels.
- Guard every animation with reduced-motion.
- Keep secondary palette + gradient on marketing surfaces only.

**Don't**
- A border drawn *around* a card, chip, tab, button or field — separate by fill (§7A). Selection by outline/ring/shadow.
- Hand-drawn headers, cards, notices, buttons or chips — use `macros/ui.html` (§9.0).
- Salmon as a background, wash, glow, gradient filler, or button.
- Raw `hsl()`/hex in a component, or a new radius/shadow value.
- Ad-hoc text opacities — use the neutral ramp.
- Infinite animations on resting UI.
- Black-background buttons, DaisyUI `alert/stats/hero`, or shadow soup.
- Secondary/marketing hues inside the product chrome.

---

## 12 · Audit backlog (paydown plan — incremental, per Decision B1)

Each item → an ADR/REQ when picked up. Incremental (small safe passes), not a big-bang refactor.

| # | Item | Fixes | Priority |
|---|---|---|---|
| 1 | **Button variant system** in `app.css`; retire black CTA | §9.1, the original gap | P1 |
| 2 | **Salmon audit** — strip salmon from chip/breathe-pill/label-dot/nav-progress/seg-tab; keep top-match + celebration | §2, §4.1 | P1 |
| 3 | **Color-model unification** — HSL → OKLCH scale in score/chip/verdict | §4.5 | P1 |
| 4 | **Text tint ramp** — replace scattered opacities with `--n-*` | §4.4 | P2 |
| 5 | **Radius collapse** to the 5-step set | §6 | P2 |
| 6 | **Elevation scale** — consolidate ~10 shadows to 4 tokens | §7 | P2 |
| 7 | **Motion tokens** + kill infinite resting loops + reduced-motion everywhere | §8 | P2 |
| 8 | **Component inventory** — backfill specs/screens for all §9 items | §9 | P3 |

**Progress (on -edu, unmerged):**
- ✅ #1 Button system — `.btn-quiet`/`.btn-danger`/`.btn-danger-solid` + **Tailor always primary** in job surfaces (2026-09-19).
- 🟡 #2 Salmon audit — the visible /jobs sprawl done (For-you/suggestion/role chips → `.chip-suggest` green; seg-tab/nav-progress/utab/journey-dot/card-hover/label-dot → green; infinite `pillBreathe` removed). **Remaining:** inline `style="color:oklch(var(--a))"` across journey/insights/welcome/applications (several celebration-legit) — fine pass.
- ✅ #3 Color model — score-badge/score-ring/chip-matched/chip-gap/score-hero-badge/verdict-pill migrated HSL → OKLCH via `--v-strong/stretch/poor-*` tokens (§4.5) (2026-09-20). **Remaining:** inline HSL banners/spinners in jobs.html/jobs_results.html/ring.html (low-visibility status banners) — fine pass.
- ➕ Also shipped: page bg → clean flat off-white (`--b2` 98.4%), radial green "cloud" wash removed.
- ⬜ #4 text ramp · #5 radius collapse · #6 elevation · #7 motion tokens (vars defined, not yet wired into existing components) · #8 component inventory.
- ✅ 2026-09-28 **Composition layer**: `macros/ui.html` (§9.0) + surfaces "tinta, no contorno" (§7A) in app.css (card-quiet, job-card, chips, pills, seg-tabs, btn-quiet, searchbar) + `scripts/lint_ui.py` ratchet. Pilot migrated: Prep/Practice/Stories headers → `ui.page_header`, outlined notices → `.ui-notice`, back links → `.ui-back`, job_card chips off inline HSL. #4 text ramp started (`text-subtle`/`text-faint`). Remaining debt = the lint baseline — lower it screen by screen.

**Verification:** visual/e2e on `jobbotv2-edu` via `verify-on-edu`; unit tests local first. Remember: merging to `main` auto-deploys all 6 user apps — canary on -edu first.
