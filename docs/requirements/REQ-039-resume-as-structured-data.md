# REQ-039: Resume-as-structured-data — templates + breakdown score

Date: 2026-09-15
Status: Proposed (phased; not built)
Relates to: ADR-045 (the decision), EXP-001 (score is trustworthy), the
fit_story work (first slice of the breakdown), ADR-005 (fidelity in the
contract layer)

## The ask (Eduardo, 2026-09-15)

Represent the resumes Jobot GENERATES as **structured data** (JSON-Resume-style
entries: `work[] {company, role, dates, highlights[]}`, `skills[]`,
`education[]`), so we can:
1. render **several visual templates** from one source — today every resume
   looks the same; and
2. show a **breakdown score** (per dimension: skills coverage, experience
   relevance, seniority, credentials) instead of one opaque number.

## The need underneath

Today the resume is a flat `sections → list-of-strings` blob (parser → rewrite →
writer all speak it). That model **blocks both asks**: a template can't re-lay-out
entries it can't see as entries, and you can't score dimensions separately over
flat text. EXP-001 proved the single 0-100 score is *accurate* (tracks a
recruiter, ρ 0.75-0.86) — so the breakdown is NOT about accuracy; it's about
**transparency** (show the *why* per dimension) and it's the **enabler for
templates**. Both goals are the same architectural bet.

## Phased plan — validate each phase before committing the next

- **Phase 0 — spike (generation side only).** The tailor LLM already rewrites the
  resume; change its OUTPUT schema to emit structured `work[]/highlights[]`
  instead of flat strings. No new parser. Gate: fidelity — the adversarial
  harness confirms no role/employer/degree is dropped (the ADR-005 collapse risk).
- **Phase 1 — templates.** Render 2-3 distinct templates (classic 1-col, modern
  2-col, compact) from the structured tailored data. Gate: all pass the ATS
  heuristic; visibly different.
- **Phase 2 — breakdown score.** Compute per-dimension scores over the structured
  resume + JD. Gate: harness check — does the breakdown track the recruiter as
  well as the single score, and read as more explainable? fit_story
  (domain+seniority) folds in here.
- **Phase 3 — structured PARSING of uploads (deferred, risky).** Extract
  structure from uploaded docx/pdf. Only if Phases 0-2 pay off.

## Non-goals (v1)

- Adopting the jsonresume.org schema literally (rigid, 2014) — use its *pattern*,
  our own schema tuned for tailoring + scoring + ATS.
- Re-parsing uploaded resumes into structure (that's Phase 3, deferred).
- Selling the breakdown as "more accurate" — it's transparency + templates.
