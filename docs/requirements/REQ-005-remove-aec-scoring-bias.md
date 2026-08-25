# REQ-005: Remove domain-specific / AEC scoring bias

Date: 2026-08-21
Source: User (product spec, verbatim in chat)
Status: Open

## What they asked for

Strip the hardcoded AEC recruiter persona from the scoring system.
Scoring must not assume the candidate works in AEC or any specific
industry. Remove AEC framing from the scoring prompt, prompt constants,
scoring docs/comments, and default test assumptions. AEC-specific
examples stay only when the fixture is explicitly an AEC candidate or
AEC job.

Candidate context in the prompt must come from the actual resume
(primary role/domain, experience, skills, education, seniority, career
context — use existing `role_label` where available). Job context must
be interpreted independently by the model (role, responsibilities,
required skills, industry, seniority, education, hard vs soft reqs).
Do not assume candidate and job share an industry.

Scorer must reward transferable experience, recognize semantic
equivalents (not just keywords), distinguish skill gap from missing
keyword, distinguish industry mismatch from role mismatch.

**Ship-time regression coverage** (revised — see rationale below):
- 1 AEC fixture (real, from existing AEC user) — no-regression proof.
- 1 real non-AEC fixture (Sara or Melissa's resume) — proves the bias
  isn't just relocated.
- 1 constructed career-switcher fixture built from *real* experience
  histories — proves transferable-experience logic.

Each fixture must carry a **qualitative assertion** (expected verdict
band + relative section-score relationships + one-line "what this
proves"), not just an expected number.

**Runtime guard-rail** (contract-layer, ADR-005 pattern):
grounding-check every per-section `matched` / `gaps` / evidence
against the resume before persisting. Failing case → silent retry →
if still failing, log as bias-suspect and skip caching.

**Ongoing coverage backfill**: each new user from an uncovered domain
becomes fixture #N+1 as soon as their first flagged case surfaces.
Tracked on Notion (see Related).

## What they actually need

Prompts must be **powerful, non-biased, applicable across users, and
templated to align with each request**. Currently the scoring prompt
(`core/matching/semantic_score.py:234`) opens with
*"You are an expert AEC recruiter"* and the rewrite prompt
(`core/llm/prompts.py:59`) hardcodes *"AEC/construction roles"* — so
every non-AEC user is scored/rewritten through the wrong lens by
default. The fix is not "delete AEC" but "make the persona a template
slot driven by the candidate's actual resume context (role_label,
domain, seniority) and the job's actual context," so the same prompt
works for a Sales candidate, a BI candidate, or an AEC candidate
without any of them being privileged.

## How we'll know it worked

- A Sales, BI, or tech candidate scored against a job in their own
  domain lands in a defensible band (not artificially low from AEC
  framing, not artificially high from keyword overlap).
- A career-switcher with strong transferable experience but no direct
  industry history scores higher than a same-industry candidate with
  weak relevant experience.
- `grep -ri aec docs/ ui_web/ core/` returns only test fixtures
  explicitly labelled AEC.

## Related

- REQ-004 (paired — section rework and debias ship together).
- ADR-007 (domain-neutral persona from resume context).
- ADR-006 (scoring architecture split; provides the version lever
  ADR-007 uses to invalidate AEC-biased cached scores).
- Regression suite expansion across 5 domain fixtures.
