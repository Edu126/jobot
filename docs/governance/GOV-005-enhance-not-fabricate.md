# GOV-005: Enhance, not fabricate — the honesty guardrail for the "land it" stage

Date: 2026-09-01
Relates to: REQ-017 (post-apply stage), REQ-018 (gap enhancement),
GOV-003 (candidate alignment), product vision non-negotiable #1/#2

> Written **before** any REQ-017 feature ships (per Eduardo's decision
> 2026-09-01, decision (d)). Applies to the whole "land it" stage — both the
> Cluster A gap/profile features building now and the Cluster B interview /
> assessment features deferred for later. This is the line the stage must not
> cross.

## Data involved

Candidate-authored career data: résumé/profile text, self-described skills and
experience, and (later, Cluster B) practice answers to interview / assessment
questions. Sensitive because it is the person's professional identity and,
downstream, what they present to an employer.

## Who can access it

The candidate (their own data) and the Gemini call sites that generate
suggestions (see `docs/architecture/llm-surface.md`). No employer/recruiter
surface — reinforces GOV-003 and the architecture non-goal.

## Where it lives and where it travels

Same path as existing artifacts: local SQLite + the résumé text already sent to
Google Gemini under GOV-001. No new external hop introduced by the honesty
rule itself. (LinkedIn eval input governance is a *separate* call — this stage
uses **paste**, not scrape; decision (c) 2026-09-01 — so no LinkedIn ToS hop.)

## Risk accepted — and the line we will NOT cross

The real risk of a "land it" stage is not data leakage; it is **jobot helping
the candidate misrepresent themselves**, which detonates non-negotiable #1/#2
(honesty in the contract layer) and the candidate's own credibility/legal
standing.

The rule, binding on every feature in this stage:

- **Enhance = surface and reword what is TRUE.** Aflorar una skill real,
  reformularla en el lenguaje que el ranker premia, hacer visible experiencia
  que ya existe. **On-side.**
- **Fabricate = assert something the candidate does not have.** Inventar una
  skill, un título, una responsabilidad. **Banned.** No feature may generate,
  suggest, or auto-fill a claim the candidate hasn't affirmed as true.
- **Practice ≠ cheat (Cluster B, forward-looking).** Coaching, rehearsal,
  mock questions, and reasoning practice are on-side. Anything that supplies
  live answers to a real assessment, or coaches the user to defeat an
  integrity check, is **banned** — it's "beat the ATS" in a new costume.
- **Candidate-side employer risk IS allowed.** Telling the candidate about an
  employer's risk/outlook (company outlook, layoffs, reviews) is on the
  candidate's side and LinkedIn-can't-build — explicitly permitted.

We accept that this narrows what we can build (no "auto-invent a matching
skill" shortcut). That narrowing is the product.

## Revisit when

The first Cluster B feature (interview prep / assessment practice) is scoped —
re-read this note and, if the feature touches a real/live assessment, write its
own ADR against this line before building. Also revisit if we ever add a
LinkedIn *scrape* path (would need its own ToS/data-governance note).
</content>
</invoke>
