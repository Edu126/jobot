# ADR-013: Persona data source — shared, core-owned resume profile

Date: 2026-08-26
Status: Accepted
Relates to: ADR-007 (persona-from-resume-context — this ADR fills in
where the persona data actually comes from), ADR-006 (versioning lever
this reuses), REQ-004, REQ-005

## Context

ADR-007 says the scoring persona is filled from `role_label` ("existing
on the resume model"), a primary domain, and seniority ("existing
signal"). Reading the code before implementing turned up two gaps:

- `role_label` is not on the resume model. It lives in
  `resume_ai_summary`, produced by one lazy Gemini call
  (`ui_web/routes/profile.py::_maybe_generate_ai_summary`) triggered
  only when the user opens Profile, cached per `(resume_id,
  output_language)`. A user who searches jobs before ever visiting
  Profile has no `role_label` yet.
- `domain` and `seniority` don't exist anywhere as data — only as prose
  inside prompts. There is no signal to plug into the persona template.

Also, `_maybe_generate_ai_summary` lives in `ui_web/routes/`.
`core/matching/semantic_score.py` lives in `core/`. Having scoring call
into a `ui_web` route handler would be a reversed dependency — `core/`
is supposed to be usable without the web layer.

## Decision

Turn the resume's LLM-derived profile into a **shared, core-owned
artifact** instead of a Profile-page-only side effect.

- Move the generation + fetch logic (prompt, `_ResumeSummaryLLM`
  Pydantic model, grounding check, retry-once, cache read/write) from
  `ui_web/routes/profile.py` into `core/resume/ai_summary.py`. Profile's
  route becomes a thin caller.
- Extend the prompt and `_ResumeSummaryLLM` to also return `domain`
  (primary industry/field, short phrase) and `seniority` (junior / mid /
  senior / lead, one word) alongside the existing `role_label`,
  `first_impression`, and `section_suggestions`. Same call, same
  grounding contract, same cache row — `resume_ai_summary` gains two
  columns (additive migration, same pattern as prior schema bumps).
- `core.matching.semantic_score.score_jobs` calls the shared fetch-or-
  generate function before building the prompt. If the profile isn't
  cached yet (first-ever scoring, no Profile visit), it generates it
  once, same as Profile's lazy trigger does today.
- If generation fails (no API key, ungrounded, quota exhausted), scoring
  proceeds with a generic neutral persona line ("an experienced
  professional candidate") instead of blocking. Scoring must never hang
  or fail because the persona side-call failed — same silent-failure
  posture as ADR-005.
- `domain`/`seniority` are descriptive input to the prompt only, not
  user-facing strings — they don't need to match `get_reasoning_language()`;
  whatever language they were generated in is fine.

## Alternatives considered

- **Code-only heuristic (keyword/date-range based), no LLM, no shared
  module.** Zero extra cost, zero layering change. Rejected: coarser
  signal, and it sidesteps ADR-007's actual intent — a persona informed
  by the same 2–5 word field judgment already proven to work for
  `role_label`, not a bag of matched keywords.
- **Let `semantic_score.py` import directly from
  `ui_web/routes/profile.py`.** Rejected — inverts the core/ui_web
  dependency direction; makes `core/` untestable without the web app
  wired up.
- **Separate LLM call just for scoring's persona, decoupled from
  `resume_ai_summary`.** Rejected — doubles Gemini calls per resume for
  data that's the same judgment (role/domain/seniority from the same
  resume text), and creates two independent caches that can disagree.

## Consequences

- `resume_ai_summary` migration: additive `domain TEXT`, `seniority
  TEXT` columns. Old rows read back with empty strings until
  regenerated — no data loss, no forced rebuild.
- `core/resume/ai_summary.py` becomes shared infrastructure: both the
  Profile fragment and scoring depend on it. A prompt change there now
  affects two surfaces — worth a comment at the top of the file.
- First-ever scoring call for a resume that skipped Profile costs one
  extra Gemini call (persona generation) before the batch call. Cached
  after that. Negligible at 4-user free-tier load; worth watching if
  user count grows enough to matter.
- Scoring quality now depends on this profile call succeeding at least
  once per resume. The generic fallback keeps scoring available, but
  loses the domain-neutral benefit ADR-007 is for until the profile
  call succeeds.
- `ui_web/routes/profile.py` shrinks to route glue; the actual contract
  (Pydantic + grounding) becomes testable from `core/` without spinning
  up FastAPI.
