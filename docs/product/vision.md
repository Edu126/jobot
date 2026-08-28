# Product Vision — the real north star

Last updated: 2026-08-27

This is jobot's **product & business** north star: what we're building,
for whom, why anyone pays, and how the company grows. It sits *above*
`docs/architecture/vision.md` (which is the **technical** north star and
must serve this). If a product decision conflicts with this doc, either
the decision changes or this doc changes explicitly — never silently.

Origin: strategic deliberation session 2026-08-27 (Eduardo + Claude, as
peer founder/architects). This doc captures the conclusions; the reasoning
lives in that session and in `founder-roadmap.md` / `milestones.md`.

---

## The heart

> Applying to a job is a task of **high cognitive load** — repetitive,
> demoralizing, blank-page after blank-page. **Jobot carries that load.**

Everything else — score, tailoring, autofill, culture-fit answers — is a
*projection* of one promise: **that you apply more, better, and without
burning out.** If a decision doesn't lower cognitive load or improve
outcome, it isn't jobot.

## The core reframe: episodic → continuous

- **Job search is EPISODIC** — you leave when you get hired. A tool that
  succeeds destroys its own retention. Success = churn.
- **A career is CONTINUOUS** — it never ends.

So jobot is **not** a job-search tool. It's the **digital persona of your
career**. The job search is the *entry wedge* (max urgency, max
willingness to pay); the persona is what **retains after the hire**. This
is what kills the retention paradox.

"Application helper" is a feature LinkedIn/ChatGPT absorb in 12 months.
"Your portable, AI-native professional self" is a company.

## The central asset: the candidate model

The moat is **not** tailoring text (that commoditizes as everyone gets AI
— a Red Queen race). The moat is a **rich, tone-aware, story-aware model
of the person** that can answer *novel* questions in their voice ("why
should we hire you?", culture fit), grounded in `company × candidate
tone/history`. The résumé is just one projection of it. Deepens ADR-013's
persona from "résumé-derived" to **narrated career self** ("tell me your
career story" → infer tone, trajectory, projections).

## The gap is monetized three times

We already compute `matched/gaps`. **The distance between who you are and
the job you want is the product** — sold three times, at three horizons:

| Close the gap… | Monetizes | Model | Retention |
|---|---|---|---|
| On paper (tailoring, autofill, agent) | Episode urgency | Freemium → paid volume/agent | Low |
| For real (skill-gap → courses) | Real skill gap | **Rev-share w/ Udemy/Coursera/coaching** — we're their qualified-lead funnel | Medium |
| Over time (tracking the gap) | Market worth, passive matching | **Subscription that survives employment** | **High** |

Later, guarded: aggregate outcome data → market intelligence (governance-gated).

## North Star metric — a two-level hierarchy

**Eternal (never changes — the mission):**
> **Career advancement delivered per hour of user effort.**

Denominator (cognitive load) is constant for the life of the company;
the numerator's *meaning* evolves by phase (interview today → raise /
better role later).

**Per-phase driver** (the proxy we can move now): see `milestones.md`.
One north star with several phase drivers — never several north stars.

## Non-negotiable: we are on the candidate's side

The moment we take money from an employer/recruiter to influence what the
candidate sees, we betray the user. jobot is **paid by, or aligned with,
the candidate — never against them** (candidate, or partners who benefit
the candidate: education, coaching). Codified in
`docs/governance/GOV-003-candidate-alignment.md`. Reinforces the existing
architecture non-goal "no recruiter/employer surface."

## Deliberate reframes captured (so we don't relitigate)

- **ICP is not a demographic.** "Immigrant in a second language" is *one*
  persona, not the wedge. Segment by **moment / job-to-be-done** (active
  search), which cuts across local / immigrant / 2nd-gen / switcher /
  new-grad. Persona segmentation is its own **research workstream**, fed
  by real data — not decided by hand today.
- **We optimize "apply better", then "apply more at constant quality"** —
  two growth vectors, not "apply more." Cold ATS applications are the
  lowest-yield channel; the network/referral layer (Phase 4) attacks the
  real one.
- **We must optimize to pass AI/ATS screening, not to "sound good"** —
  the first reader is a machine — but **without fabricating** (honesty
  lives in the contract layer, per architecture non-negotiable #1/#2).

## When to revisit

Rewrite this doc (not silently amend) when the episodic→continuous thesis,
the three-arc revenue model, or the eternal north star changes. Each such
change gets its own ADR.
