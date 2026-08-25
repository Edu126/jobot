# ADR-007: Domain-neutral scoring via persona-from-resume-context

Date: 2026-08-21
Status: Accepted
Relates to: REQ-005 (also enables REQ-004's cache invalidation via
`prompt_version` bump)

## Context
Two LLM prompts hardcode an AEC recruiter persona:

- `core/matching/semantic_score.py:234` — *"You are an expert AEC
  (architecture / engineering / construction) recruiter…"*
- `core/llm/prompts.py:59` — *"expert resume editor for the Canadian
  job market, especially AEC/construction roles (BIM, Estimating,
  Project Coordination)…"*

Both were tuned when jobot served one AEC candidate (the user's
boyfriend, per `core/jobs/saved_searches.py:3`). Onboarding a Sales,
BI, or tech candidate today means every scoring call and every resume
rewrite runs through the wrong lens by default — the model reaches for
AEC framing, AEC keywords, and AEC seniority calibration, then
mis-scores or mis-tailors accordingly. Deleting the persona hurts
quality: a persona-anchored prompt reasons better than a generic one.
The fix is templating the persona from the candidate's own resume,
not removing it.

## Decision
- **Persona becomes a template slot** filled from candidate context
  the parser already produces:
  - `role_label` (existing on the resume model — the 2-5 word
    field/role guess, e.g. `"BI / Analytics Engineer"`).
  - Primary domain / industry (derived from experience section).
  - Seniority (existing signal).
- Scoring prompt opens with something like: *"You are an expert
  recruiter evaluating job postings for a {role_label} candidate with
  {seniority} experience in {domain}. The job may or may not be in
  the same industry — assess transferable experience explicitly."*
- The **job side stays LLM-inferred**: role, responsibilities, required
  skills, industry, seniority, hard vs soft reqs — all read from the
  JD by the model. **No assumption that candidate and job share an
  industry.**
- Same treatment for the resume-rewrite prompt (`prompts.py:59`) —
  the persona is derived from the resume being rewritten.
- Existing AEC-specific false-positive examples in the scoring prompt
  (Driver license / AutoCAD / Autodesk suite / Bilingual / BASc) are
  **kept as generic pattern examples** for "check for synonyms before
  flagging a gap" — they teach the shape of the check, not an
  industry.
- On landing: bump `prompt_version` (from ADR-006) → all cached AEC-
  biased scores logically invalidate on next read. History rows
  preserved.

## Alternatives considered
- **Multiple prompts, one per industry cluster.** Rejected — every new
  user domain needs a new prompt, doesn't scale, still biased inside
  each cluster.
- **Delete the persona entirely, use a generic "evaluator" voice.**
  Rejected — measurably weaker reasoning in early spot checks with
  similar prompts elsewhere; persona-anchored prompts hold context
  better.
- **Let the LLM pick its own persona from the resume.** Rejected —
  reintroduces exactly the non-determinism ADR-006 was written to
  remove. Persona must be deterministic input, not model output.
- **Ship a per-user persona override in settings.** Rejected — user-
  facing escape hatch (violates ADR-005). The resume is already the
  source of truth; ask it, don't ask the user.

## Consequences
- Same prompt now works for AEC, Sales, BI, tech, and career-switchers
  without any of them being privileged. Enables the growth REQ-005 is
  about.
- **`role_label` becomes load-bearing scoring input**, not just a
  display string. Parser quality now affects scoring quality — worth
  a grounding check (ADR-005 pattern) on `role_label` before it flows
  into the scoring prompt. Follow-up work, not blocking this ADR.
- Regression coverage must expand across the domains REQ-005 lists
  (AEC / Sales / BI / Tech / career-switcher) with the case matrix
  from that REQ (direct experience, transferable, keyword-only,
  different-title-same-scope).
- **Out of scope for this ADR** but flagged: `core/jobs/saved_searches.py`,
  `core/matching/tfidf_match.py` domain-aware extras, and the
  `core/db.py:333` seed-defaults comment all carry AEC assumptions.
  Those are search / matching / seed concerns, not evaluation prompts;
  they get their own slice under **REQ-006**, which is where REQ-005's
  grep success criterion actually gets satisfied.
- `prompt_version` bump doubles as the cache-invalidation lever from
  ADR-006 — this ADR is the first real-world test of that mechanism.
- LatAm Spanish clause via `language_instruction(...)` is unaffected —
  it's language, not domain persona; keeps working across all users.

## Relates to
- ADR-005 (persona-from-user-settings would violate the
  quality-in-contracts principle; this ADR takes the same stance).
- ADR-006 (paired — this ADR consumes ADR-006's versioning to ship
  safely).
- Memory: `feedback_simplicity_over_escape_hatches.md`.
