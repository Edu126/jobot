# Milestones — the implementation arc

Last updated: 2026-08-27

The path from today (vibe-coded POC, friends testing) to a company. Each
phase is **gated by the data of the prior one** — user-centered and
data-centered. Reads alongside `vision.md` (the why) and
`founder-roadmap.md` (the founder-side view of the same arc).

The KPI Gold, the per-phase North Star, and the revenue arc are **the same
line seen at three heights** — engagement → throughput → outcome →
continuous — all pointing at the eternal north star (*career advancement
per hour of user effort*).

---

## Phase 0 · Instrument (now)
- **User value:** — (invisible)
- **Data:** the 2 Gold + 3 support KPIs (below) flowing
- **Revenue:** —
- **Phase driver:** % of the funnel we can actually see
- **Unlocks:** the *right* to make any bet

## Phase 1 · Apply better (episodic · quality)
- **User value:** honest fit score + tailoring that passes screening
- **Data:** the **outcome loop** begins ("did you hear back?") ← moat seed
- **Revenue:** freemium episode
- **Phase driver (NSM):** interview rate per application

## Phase 2 · Apply more, same effort (episodic · quantity)
- **User value:** Chrome autofill + culture-fit answers in your voice
- **Data:** form friction, which answers work
- **Revenue:** paid tier for volume / agent
- **Phase driver (NSM):** interviews per hour of effort

## Phase 3 · The career persona (continuous · kills the retention paradox)
- **User value:** persona survives the hire — skill-gap, market worth,
  passive matching
- **Data:** longitudinal career data
- **Revenue:** subscription that survives employment + **education
  partnerships monetizing the gap**
- **Phase driver (NSM):** retention + progression events of *already-employed*
  users (raise, promotion, better role, gap closed)
  - *Soft — needs a crisp definition of "progression event" before we build.*

## Phase 4 · Career OS + network (the moat compounds)
- **User value:** warm-intros / referrals (attacks the real hiring channel)
- **Data:** aggregate outcome = market intelligence
- **Revenue:** B2B2C, market intelligence (governance-gated)
- **Phase driver (NSM):** % of outcomes via warm-intro / referral in jobot

---

## The metrics to instrument in Phase 0

**2 Gold** (if these move, we win):
- **G1 — Weekly returning users** (W1/W4 retention). *The number we can't
  see today. No business without it.*
- **G2 — Applications completed with jobot / week.** The behavior that
  matters; text without a submitted application = zero value.

**3 support** (explain why G1/G2 move):
- **S1 — Activation:** % reaching first tailored artifact in session 1.
- **S2 — Artifact acceptance:** % of artifacts used with minimal edits
  (quality/trust proxy).
- **S3 — Score trust:** do they apply to high-scored jobs? score→action
  correlation.

Note: the existing architecture already treats the BI/pulse loop as a
first-class surface (`docs/architecture/vision.md` non-negotiable #5). Phase 0
is making these specific KPIs visible on top of that loop.
