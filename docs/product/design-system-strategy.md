# Design System Strategy — from three references to Jobot's `design.md`

> **Status:** Discussion draft · 2026-09-17
> **Author:** Eduardo + Claude (pairing)
> **Purpose:** Decide the shape and direction of a real `design.md` for Jobot v2 before we build it. This is the *presentation to argue over* — not the design system itself.
> **Related:** [ADR-046 (typography)](../decisions/ADR-046-typography-schibsted-ibmplex.md) · design memory `design-jobot-v2`, `project-jobot-design-refresh`
>
> **Decisions recorded (2026-09-17):** **A1** — keep salmon, hard-scope it (green = structure/CTAs; salmon = top-match/celebration only, ≤1 per view). · **B1** incremental cleanup · **C1** full doc, phased · **D1** soft-motion tokens. · Live captures of all three reference sites reviewed (see §3.4). · **New scope:** a two-layer color model with a secondary/marketing palette, gradient, and extended neutrals — see §7-bis.

---

## 1 · The problem

We don't have a design system. We have a **1,945-line `app.css` with the design system living inside it as prose comments**, plus rules scattered across chat memory. That worked while one person held it all in their head. It stopped working the moment consistency drift showed up in real work:

- A **black-background CTA** appeared that isn't in our language (primary is hunter-green).
- **"Washed" text** is applied inconsistently — no rule for when text is muted vs. full-contrast.
- A code comment literally flags *"the 4-different-radii drift on the same screen."*
- The **plum rebrand (ADR-044) was built by parallel agents, then rejected** — partly because it *added* color fragmentation instead of reducing it. We burned real effort re-deriving decisions we'd already half-made.

The job to be done: **turn the design system from tribal knowledge into an authoritative document we (and coding agents) check against**, so we stop re-deriving and stop drifting. This doc studies how three teams who are *very good at this* structure and enforce their systems, contrasts that with where we actually are, and proposes how to close the gap.

**Why this matters for a job-hunting app specifically:** job hunting is emotionally loaded (rejection, self-doubt, decision paralysis). A calm, coherent, "expensive-feeling" interface isn't vanity — it's the product doing emotional scaffolding. Visual noise reads as anxiety.

---

## 2 · Method

- Three references Eduardo selected for specific qualities (see §3).
- One cheap research agent per reference extracted: the **structure** of each style guide (so we can model our TOC), the **concrete tokens**, the **feel/mechanisms**, and — deliberately — **what would be a mistake to copy**.
- Contrasted against a full read of our current `app.css` + design memory.
- Then challenged the findings with our own judgment (§6) — we are a data-dense product app, not a marketing site, and some of their orthodoxy doesn't bind us.

---

## 3 · Findings — the three references

### 3.1 MDF Italia "Contract" — *why Eduardo picked it: "expensive, clean, soft animations"*
Architectural furniture brand. Monochrome (7 colors: white, black, 4 grays, one signal blue for links only). Type is huge and confident (100px display, aggressive −5px negative tracking). **Zero shadows, zero border-radius** — depth comes from *full-width black↔white band inversion* and *1px hairline borders*. Motion is smooth but barely-there.

- **The move:** elegance through omission. Hairlines do all the structural work; photography carries all the warmth while the chrome stays achromatic.
- **Steal:** hairline borders as honest structure (vs. stacked shadows); intentional color scarcity; full-width bands as deliberate "rest" between thought-chunks.
- **Don't copy:** *no filled buttons* (all actions are underlined text links). Fine for browsing sofas — hostile for an anxious job seeker who needs an obvious **Apply / Save**. Pure achromatic also reads sterile; our salmon needs *permission* to show warmth at moments that matter.

### 3.2 Monotype — *why Eduardo picked it: "editorial but functional, breathes without dead space"*
Type foundry. "The type is the artifact, the chrome recedes." 8-color monochrome + one Signal Blue (CTAs only). **Binary radius (8px UI / 16px images). Exactly one shadow** (a 2px button shadow). 8px spacing base with 80–104px section gaps — huge breathing room, but density held by tightly-cropped imagery and compact 16–24px card padding.

- **The move:** whitespace as *rhythm*, not emptiness. Type size+weight carries the entire hierarchy; the UI has almost no chrome to compete.
- **Steal:** monochrome-plus-one-accent; typography-first hierarchy (state changes via size/weight/color, not background fills); an 80px vertical rhythm between major sections.
- **Don't copy:** the gallery-wall 3-column grid starves a data-dense matches list; and *one CTA per page* would paralyze our profile/tailor flows (we legitimately need Save + Tailor + View + Apply).

### 3.3 Fiverr — *why Eduardo picked it: "complete guide, easy to find cohesion between elements"* — **our structural template**
Marketplace. The most *complete* of the three: 10 sections, 9 color tokens, single typeface (Macan) across 4 weights, **4 radius values only**, **one shadow rule** (`rgba(0,0,0,.13) 0 3px 10px`, cards only), 7 Do's / 7 Don'ts, **14 documented components**.

- **The killer rule:** *"Green must read as punctuation, not as a wash"* — accent only in links/active states/tag borders, **never** as a fill or background. **We independently discovered this** when the salmon body-wash was rejected. Three references now validate it.
- **Cohesion mechanism:** ruthless repetition — one type family, one shadow, fixed radii, identical card padding (16px internal / 24–40px external) everywhere. Users learn the pattern once because it never breaks.
- **Steal:** the whole *do/don't + component-inventory* discipline; accent-as-punctuation as a hard rule; "depth is earned, not free" (shadow on floating surfaces only).
- **Don't copy:** marketplace density and full-bleed promo banners — those break calm. Our Coach/onboarding/settings belong in quiet drawers, not banners.

---

### 3.4 Visual read (live site captures, 2026-09-17)
Drove Chrome through all three homepages. What the captures confirmed:

- **MDF Italia** — spare black wordmark + text-only nav, huge "Best sellers" display type, product cards on faint grey tiles, names as *bold + muted-category + muted-designer*. Tellingly, **the product photography itself is sage-green + terracotta/clay** — i.e. *our* hunter-green + salmon family. Live proof our palette can read "expensive." Images lazy-load slowly, which reads as unhurried, not broken.
- **Monotype** — giant black *"Typography that works."*, blue used **only** as punctuation ("At any scale.", the 01/02/03 numerals, the primary CTA). Filled-primary **+** outlined-secondary button pair. A numbered **benefit list** on the right — exactly the welcome/landing benefit-card pattern we now want to design.
- **Fiverr** — the green is **literally just the dot after "fiverr."** Everything else monochrome (black Join button, white outlined category chips with arrows, dark search button); the full-bleed hero photo carries all warmth. "Accent as punctuation, never a wash," made visible in one glance.

**Takeaway that feeds §7-bis:** every one of these keeps the *chrome* near-monochrome and lets **photography / one accent** do the colour work. When they DO use colour expressively, it's on marketing/hero surfaces — never in the working UI. That's the exact two-layer split Eduardo asked for.

## 4 · Three-way comparison

| Dimension | MDF Italia | Monotype | Fiverr | **Common law** |
|---|---|---|---|---|
| **Colors** | 7 (mono + 1 link blue) | 8 (mono + 1 CTA blue) | 9 (mono + 1 green) | **Mono neutrals + ONE accent** |
| **Accent role** | Links only | CTAs only | "Punctuation, never wash" | **Reserved, scannable, never a fill/wash** |
| **Typeface** | 1 (Plain) | 1 (Helvetica Now) | 1 (Macan) | **One family, hierarchy via weight/size** |
| **Radius** | 0px (2px inputs) | 8 / 16 binary | 4 values max | **A tiny fixed set — no ad-hoc values** |
| **Shadow** | None | One (button) | One (cards only) | **≤1 shadow rule; depth is earned** |
| **Depth from** | Bands + hairlines | Hairlines + type | Hairlines + one shadow | **Borders & type, not shadow soup** |
| **Motion** | Subtle/smooth | Minimal | Minimal | **Soft, restrained** |
| **Doc shape** | ~11 sections | ~13 + CSS vars | 10 + 14 components | **Overview→tokens→rules→components→quick-start** |

**The unanimous verdict:** these systems feel expensive because of what they *refuse to do*. Restraint + repetition = cohesion. And all three are enforced by **one authoritative document**, not tribal memory.

---

## 5 · Gap mapping — where Jobot actually stands

Severity: 🟢 strength · 🟡 drift · 🔴 debt

| Dimension | Reference pattern | Jobot today | Gap |
|---|---|---|---|
| **Typography** | One family, weight-driven scale | Real system: IBM Plex body + Schibsted display, L1–L5 (size·weight·tracking·leading), one eyebrow rule unifying ~63 labels | 🟢 **Already reference-grade.** Our biggest asset. |
| **Accent discipline** | "Punctuation, never wash" | We *learned* this (salmon wash rejected) but salmon now sprawls: chip, pill (infinite breathe), badge, celebration, label-dot glow, nav-progress gradient, seg-tab "top light"… | 🔴 Rule known, not enforced. |
| **Number of accents** | Exactly one | **Two** (hunter-green + salmon) | 🟡 One more than all three — the exact "fragmentation" that helped kill plum. Decision needed (§7-A). |
| **Color model** | One model, tokenized | OKLCH tokens **and** raw HSL (score badges, chips, verdict pills) — the "green" is 170° in OKLCH but 155–165° in HSL | 🔴 Two models; not even the same green. |
| **Radius** | ≤4 fixed values | 8+ values (0.75/0.5/0.375rem tokens + 0.6rem card + 16px panel + 12/10px badge + 6px calendar…) | 🔴 Drift, self-flagged in code. |
| **Shadow** | ≤1 rule, cards only | Memory rule "never shadow cards" — but `card-quiet` has one, plus ~10 bespoke shadows, no scale | 🔴 Own rule already broken. |
| **Motion** | Soft, restrained | 11 keyframes, several **infinite** (breathe/pulse/loader); every duration/easing hardcoded (0.15–2.8s); reduced-motion guards inconsistent | 🟡→🔴 No tokens; "calm" not enforced. |
| **Buttons** | Documented variant set | **No `.btn-*` system** — DaisyUI + one-off black CTA + green FAB + lang-pill | 🔴 The gap that started this. |
| **Governance** | One authoritative doc + component inventory + do/don't | Prose comments in 1,945-line CSS + scattered memory; ~30 undocumented components | 🔴 No source of truth. |

**One-line diagnosis:** *Our typography is already where the references are. Everything else needs their two disciplines — **restraint** (fewer values) and a **single source of truth**.*

---

## 6 · Our own challenge to the research (don't cargo-cult)

The references are marketing/brand sites. **We are a data-dense product app.** Where that changes the answer:

1. **Keep two type voices — reject "one typeface" orthodoxy.** A foundry uses one font because *the font is the product*. Our Schibsted-display + IBM-Plex-body pairing is a deliberate "two voices" call (this = heading, this = content) and it already reads editorial. We adopt their **weight discipline**, not their single-family rule. *No change to type — it's the asset.*
2. **We can't go near-monochrome — verdict color is data, not decoration.** Fit verdicts (strong/workable/stretch/poor) *must* be color-coded; that's information the references never had to show. So we'll always carry more color than they do. The fix isn't fewer semantic colors — it's **one color model** (kill raw HSL, express verdicts as OKLCH tokens) and a **disciplined verdict scale**.
3. **Filled CTAs stay.** All three agents independently flagged that minimal/ghost CTAs hurt anxious users. Non-negotiable: obvious primary actions.
4. **The real question isn't "one accent vs. two" — it's "is salmon earning its keep?"** Salmon was demoted from the body wash for reading as an uneven peach; it helped sink the plum rebrand by fragmenting color. Yet it's the one warm, human beat in a green/neutral system. That's a genuine fork, not a cleanup — see §7-A.
5. **Motion is our biggest unforced deviation from Eduardo's own taste.** He picked MDF for *"soft animations,"* yet we run several **infinite** loops (breathing pills, pulsing dots, a 9-cell wave loader). "Soft" is currently aspiration, not a rule.

---

## 7 · Strategy & options to discuss

I'm framing the pivotal calls as decisions with options + a recommendation. **These are the things to argue about before I build `design.md`.**

### Decision A — Accent strategy *(the big one)* — ✅ **CHOSEN: A1**
- **A1 (CHOSEN): Keep green + salmon, but hard-scope each.** Green = structure/primary/CTAs. Salmon = *one reserved job* only (top-match / celebration / "the eye lands here"), never decorative, never a wash. Codify "≤1 salmon element per view." Keeps warmth, kills fragmentation. → Cleanup list to enforce this in §7-bis.
- **A2: Single accent (green only).** Maximally coherent, matches all three references literally. Cost: loses the one warm human beat; risks feeling clinical for an emotional product.
- **A3: Formalize a two-tier accent** (green primary, salmon secondary with its own documented rules). Most flexible, least restrained — closest to today, highest drift risk.

### Decision B — How aggressive is the cleanup?
- **B1 (recommended): Incremental, within the green identity.** Document first, then refactor tokens in small safe passes (color-model unification, radius collapse, shadow scale, motion tokens). *This mirrors what already worked* — the incremental green direction survived; the big-bang plum rebrand didn't.
- **B2: Big-bang token refactor.** Faster to "clean," but this is exactly the pattern that got rejected once. Not recommended.

### Decision C — Scope of `design.md` v1
- **C1 (recommended): Full Fiverr-shaped doc, built in phases.** Ship the *tokens + rules + do/don't* first (closes the drift), then backfill the 30-component inventory over time.
- **C2: Lean tokens+rules only.** Faster, but leaves the component sprawl undocumented — the drift returns.

### Decision D — Motion posture
- **D1 (recommended): "Soft by default" motion tokens.** A small duration/easing scale; **no infinite loops** except a genuine loading state; reduced-motion guard on everything. Matches the MDF taste Eduardo chose.
- **D2: Keep current motion, just document it.** Lower effort; but enshrines the infinite-pulse noise we probably don't want.

---

## 7-bis · Color architecture — two layers (per Eduardo, 2026-09-17)

Eduardo's ask: *the product keeps consistency with its two accents (green + salmon), but we need **secondary colours**, a **gradient**, and **neutrals** for other surfaces — e.g. benefit cards on a welcome / landing page.*

This is exactly what the references do (see §3.4): the **working UI stays disciplined**, and **expressive colour lives on marketing surfaces**. So we adopt a **two-layer colour model** — the same pattern Stripe/Linear use (calm product, vivid marketing).

> **The governing rule:** Secondary colours + the gradient are for **expressive/marketing surfaces only** — `welcome.html`, landing/hero, feature & benefit cards, empty-state art, celebration moments. They **never** enter the working product chrome (job cards, forms, nav, tabs, drawers), which stays **green + salmon + neutrals**. This keeps "accent as punctuation" intact where users *work*, and gives *storytelling* pages room to breathe.

### Layer 1 — Product accents (unchanged, now disciplined per Decision A1)
- **Hunter green** `--p` = `35.5% 0.075 170` (#004E3D) — structure, nav, primary CTAs, links, save, active states.
- **Salmon** `--a` = `72% 0.17 30` (~#FF7F6B) — top-match / celebration ONLY, ≤1 per view, never a fill/wash.

### Layer 2 — Secondary palette (marketing surfaces)
Six harmonised hues, tuned to sit next to hunter-green + salmon (warm, earthy, **low chroma** so nothing screams). Each is a **pair**: a light **tint** (card/section background) + a deep **ink** (heading/icon on that tint) of the same family — the benefit-card recipe. *Values are OKLCH `L% C H` with hex approximations; draft for tuning.*

| Token | Role | Tint (bg) | Ink (text/icon) |
|---|---|---|---|
| `--sec-sage` | green-family benefit card (bridges to primary) | `95% 0.02 150` ≈ #E9F0E8 | `40% 0.06 155` ≈ #3A5A46 |
| `--sec-clay` | warm "salmon grown up" — earthier | `94% 0.03 40` ≈ #F6E7DE | `46% 0.09 40` ≈ #9C5A44 |
| `--sec-honey` | warm gold / ochre | `95% 0.04 85` ≈ #F5ECD6 | `48% 0.07 75` ≈ #8A6A34 |
| `--sec-teal` | cool counterpoint (calm, muted) | `94% 0.02 220` ≈ #E1EAEE | `42% 0.06 230` ≈ #3E5A6B |
| `--sec-plum` | soft berry (one cool-warm bridge) | `94% 0.02 330` ≈ #EEE6EC | `44% 0.07 340` ≈ #7A4E68 |
| `--sec-stone` | hue-neutral warm card | `94% 0.006 80` ≈ #ECE8E1 | `40% 0.01 70` ≈ #5E5A52 |

- Chroma capped ~0.04 on tints so a row of benefit cards reads as a calm, coordinated set, not a crayon box.
- All hues live in a warm 40–150° arc **plus** two cool anchors (teal, plum) for variety — but all desaturated enough to belong to the same family as the linen page.
- **Note (my recommendation):** for a first landing page, use **3–4** of these, not all six. Sage + Clay + Honey is the tightest, warmest set and stays closest to the brand; add Teal only when you need a cool beat.

### Signature gradient
- `--grad-brand` (hero / big moments): `linear-gradient(135deg, oklch(35.5% 0.075 170) 0%, oklch(52% 0.09 120) 50%, oklch(72% 0.17 30) 100%)` — hunter-green → olive → salmon. It literally *is* the two accents connected through a natural midpoint, so it feels inevitable, not arbitrary.
- `--grad-soft` (section wash): `linear-gradient(160deg, oklch(96.7% 0.005 95) 0%, oklch(95% 0.02 150) 100%)` — linen → faint sage. For quiet full-width bands between landing sections (our calm answer to MDF's black/white band inversion).
- Rule: at most **one** `--grad-brand` per page (the hero); `--grad-soft` for section rest. Never behind body text.

### Extended neutrals (warm stone ramp)
Today we have `b1/b2/b3 + bc`. A landing page needs more steps. One coherent warm ramp (all share hue ~80°, chroma near-zero — so they harmonise with linen instead of going cold-grey):

| Token | Value | ≈hex | Use |
|---|---|---|---|
| `--n-0` | `100% 0 0` | #FFFFFF | cards, lightest surface |
| `--n-1` | `96.7% 0.005 95` | #F5F4F0 | page (linen) |
| `--n-2` | `94% 0.006 80` | #ECE8E1 | soft section fill |
| `--n-3` | `91% 0.014 88` | #E5E1D7 | hairline border |
| `--n-4` | `80% 0.012 85` | #C9C3B6 | muted lines, disabled |
| `--n-5` | `56% 0.010 80` | #8A8578 | secondary text |
| `--n-6` | `40% 0.008 75` | #5E5A52 | deep taupe text |
| `--n-7` | `22% 0.010 265` | #26241F | near-black ink |

This replaces the ad-hoc greys currently scattered as raw HSL, and gives the "washed text" problem a real scale: body = `--n-7`, secondary = `--n-5`/`--n-6`, never a random opacity.

### What this closes
- Gives welcome/landing/benefit cards a **sanctioned** expressive palette instead of one-off colours → no more drift *into* marketing surfaces.
- Keeps the product app on **two accents** → Decision A1 holds where it matters.
- Turns "washed text" into a neutral ramp; kills the raw-HSL greys.

## 8 · Proposed `design.md` structure (synthesized from all three TOCs)

Fiverr's is the cleanest spine; MDF's "Imagery/Surfaces" and Monotype's "CSS custom properties export" are worth grafting on:

1. **Overview** — one paragraph: calm, editorial, confidence-building; who it's for.
2. **Principles** — the 5–7 laws (accent as punctuation; depth is earned; restraint; type-first; soft motion; filled CTAs for high-stakes actions).
3. **Color** — token table (name → OKLCH → role), *one model*, the **two-layer model** from §7-bis (Layer 1 product accents + Layer 2 secondary/marketing palette), the signature gradient, the warm neutral ramp, accent rules, and the verdict/semantic scale.
4. **Typography** — lift from ADR-046; the L1–L5 ladder + eyebrow + numerals. (Mostly done.)
5. **Spacing & shape** — base unit, spacing scale, the fixed radius set, max-widths per page.
6. **Elevation & depth** — the one shadow rule + hairline/border rules; "how depth works here."
7. **Motion** — duration/easing tokens, allowed patterns, reduced-motion contract.
8. **Components** — inventory with specs (buttons **first** — the reconciled variant set — then cards, pills/chips, tabs, drawers, score elements…).
9. **Surfaces & layout** — linen page / white cards, split-viewport, dual-scroll, container widths.
10. **Do / Don't** — the enforceable list.
11. **Quick start** — the token block for engineers/agents; how to check work against this doc.

**Artifacts to generate alongside:** the token source-of-truth block, a button-variant sheet (resolves the black-CTA debt), a color/contrast + text-tint scale (resolves "washed text"), and a component inventory checklist.

---

## 9 · Open questions for Eduardo — RESOLVED (2026-09-18)
1. ~~Decision A~~ — **A1** (keep salmon, hard-scoped).
2. ~~Secondary palette~~ — **Full 6** (all six hues) chosen after seeing the Landing Lab.
3. ~~Gradient~~ — **Soft** (`--grad-soft`, linen→sage) chosen as the hero; `--grad-brand` reserved for high-energy moments.
4. ~~design.md location~~ — **app root** (`jobot-app/design.md`), next to `CLAUDE.md` — core backbone.

➡️ **The backbone is now written: [`../../design.md`](../../design.md).** This strategy doc is the reasoning; `design.md` is the enforceable system. Next = the §12 P1 paydown (button system · salmon audit · color-model unification).

### Recommended next step
Build a single **`welcome`/landing benefit-card mockup** using Layer 2 (3–4 secondary tints + `--grad-brand` hero) so the palette is judged *in situ*, not as hex codes — then lock values and start `design.md` §3 (Color) as the first real section. This matches Decision B1 (incremental) and how the font system was picked (a live "Font Lab", not a spec on paper).
