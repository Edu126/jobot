# RESEARCH-PLAN-resume-as-data — how does the industry represent a résumé as data, and score it per dimension?

Date: 2026-09-16
Status: **Planned — launched same day** (Eduardo asked for the framing pass on REQ-039).
Mode: deep
Feeds: [REQ-039](../requirements/REQ-039-resume-as-structured-data.md),
[ADR-045](../decisions/ADR-045-structured-resume-generation-side-first.md),
[REQ-037](../requirements/REQ-037-scoring-gap-hygiene-and-off-lane-overscoring.md),
[REQ-022](../requirements/REQ-022-structured-profile-parse.md)

## The question

REQ-039/ADR-045 bet that a structured résumé model unlocks both multiple
templates and a per-dimension breakdown score. Before we build it: what shape
does the industry actually use, what makes per-dimension scoring *stable*
(we already failed once — ADR-006 → ADR-015), and can a generated bullet be
proven to trace back to a real claim?

**The decision this unblocks:** whether ADR-045's phase order (generation-side
structure first, parsing deferred to Phase 3) is the right bet, or whether the
stable-scoring requirement forces a different sequence.

## Pillars (4)

1. **Schemas & entity models + the layout reality.** JSON Resume, HR-Open
   Standards (HR-XML), Europass EDCI, schema.org; how commercial parsers
   (Textkernel/Sovren, Affinda, Daxtra, HireAbility) model entities —
   especially skills carrying proficiency / recency / evidence links rather
   than a flat list. Folded in: do real ATS/parsers reward or punish
   multi-column templates (is "several templates" a user win or a trap)?
2. **Skill taxonomies as the join key.** ESCO, O*NET, Lightcast/EMSI Open
   Skills. Core question: is normalizing both résumé and JD to a shared
   taxonomy the thing that makes per-dimension scoring reproducible — i.e.
   is the determinism we want a *taxonomy* problem rather than a *prompt*
   problem?
3. **Per-dimension scoring in practice + the trust question.** Requirement
   coverage, seniority / years-of-experience modeling, recency weighting and
   decay. Plus the explainability evidence: does a breakdown actually raise
   user trust versus one number, or does it expose more surface to disagree
   with? (REQ-039 sells the breakdown as transparency — that claim deserves
   outside evidence.)
4. **Grounding & provenance for generated résumé content.** Attribution,
   span-level citation, NLI/entailment faithfulness checks. Our pipeline has
   NO grounding on tailored output today (`ai_summary` has one; `rewrite.py`
   does not). What is the cheap, reliable pattern?

## Guardrails

- Model: Sonnet sub-agents, one per pillar, tightly scoped, parallel.
- Scope: each pillar answers its own question + "what it means for jobot" +
  3 testable implications. No wandering into recruiting-market sizing.
- Sources: every citation verified via OpenAlex/Crossref or flagged `⚠`.
- Constraints every pillar must respect when recommending: solo maintainer,
  Gemini free tier, SQLite, HTMX no-build, ~4 real users, honesty-is-the-
  product, and ADR-019 (Gemini drifts ±3–10 at temp 0 — no recommendation may
  assume LLM determinism).
- Credit budget: 4 pillar agents + 1 consolidator. No re-runs without cause.

## Expected output

One `RESEARCH-resume-as-data.md` memo with an Implications table and a
decisions section, reviewed high-level with Eduardo before anything becomes a
REQ/ADR amendment.
