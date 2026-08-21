# ADR-005: Quality lives in contracts, not user-facing escape hatches

Date: 2026-08-20
Status: Accepted

## Context
The AI resume summary produced a hallucination: "sudden pivot to art
gallery work feels totally random and unconvincing" — for a resume
(Sara's) with zero art or gallery content. Initial fix was a
user-facing "Regenerate" button on the summary card so the user
could bust the cached hallucination and re-ask. The user pushed back
hard: _"a regenerate btn... should be something we get from other
prompts, using pydantic to get the data. porque estamos abriendo
espacios donde el usuario puede regenerar tantas veces que se vuelve
peligroso"_. Then generalized the principle: _"make systems more
simple, not adding complexities."_

## Decision
For any AI-generated output surfaced to the user, quality gates live
in the **contract layer**:

- **Pydantic response models** validate shape at the LLM/service
  boundary. Malformed responses raise, don't render.
- **Grounding checks** verify that specific claims can be
  substring-matched against the source (e.g. resume text). The AI
  summary now requires a `first_impression_evidence` list and
  rejects any specific claim whose evidence isn't verbatim in the
  resume. See `_validate_grounded` in `ui_web/routes/profile.py`.
- **One silent server-side retry** on failure. If the retry also
  fails validation → return None → **no summary renders**. Silence
  beats a lie.
- **No user-facing "Regenerate" / "Retry" affordances.** Ever.

## Alternatives considered
- **User-facing regenerate button** (shipped and reverted). Rejected
  because it (a) normalises distrust of the output, (b) invites
  quota-burning spam clicks, and (c) papers over the real problem
  (an ungrounded prompt) instead of fixing it.
- **Swap models for the same task.** Doesn't address the root cause
  — hallucinations aren't provider-specific.
- **Show the summary anyway with a warning banner.** Rejected — a
  lie with a warning is still a lie the user has to bat away.

## Consequences
- Simpler UI: fewer knobs to explain and maintain. Aligns with
  vision non-negotiable #2.
- Users cannot force-retry an ungrounded output. If it fails twice
  silently, they see no summary. This is a deliberate trade-off:
  **better silence than a hallucination**.
- Contract-layer validators become **load-bearing infrastructure** —
  they must be tested. See `tests/test_ai_summary_grounding.py`
  (9 fixtures locking the invariant).
- This sets **precedent for every future AI-generated surface**: the
  next AI feature that ships should follow the same pattern
  (Pydantic model + grounding check + silent retry + null render on
  failure), not layer on a new "Regenerate" button.
- Operator-level cache invalidation is still possible (documented in
  `profile.py` comment where the deleted endpoint used to live) —
  that's an incident response tool, not a user affordance.

## Relates to
- Memory: `feedback_simplicity_over_escape_hatches.md` (same
  principle, generalized past the specific case).
- Vision non-negotiable #2 ("Quality lives in contracts, not in
  escape hatches").
