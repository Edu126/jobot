# ADR-021: Gap enhancement reuses score-time gaps + one light classify/suggest call

Date: 2026-09-01
Status: Accepted
Relates to: REQ-018 (gap enhancement on-paper), REQ-016 (matched/gaps),
GOV-005 (enhance ≠ fabricate), ADR-008 (prompt/cache conventions)

## Context

REQ-018 turns the existing `gaps` list into concrete on-paper next actions.
We already compute `matched/gaps` at score time (REQ-016, `semantic_score.py`).
The open question was where the enhancement signal comes from: recompute the
gap analysis fresh, or reuse what scoring already produced. Constraints that
are real now: Gemini credits are scarce and quotas are per-day (ADR-019/020,
`gemini_model_state`); scoring is already the expensive call; the honesty line
is non-negotiable (GOV-005); cache must key on every varying dimension
including language (ADR-008 rule 3, standing feedback).

## Decision

**Reuse the score-time `gaps` as the input** — no second gap analysis. On top
of them, make **one light, dedicated LLM call** that, per gap, classifies it as
**wording/visibility** (the user has it; the JD's language isn't on the page →
suggest the honest rewording the ranker rewards) vs **real** (the user lacks it
→ say so plainly, no fabrication, no course pitch here). Output is per-gap:
`{gap, kind: wording|real, suggestion?}`. The call is grounded in the résumé
text the user already affirmed (GOV-005: surface truths, never invent).

Cache the enhancement result keyed on **`(job_id, résumé-text-hash, lang)`** —
same résumé-hash key the score cache uses (ADR-019), plus `lang` per ADR-008
rule 3. Enhancement is lazy: generated when the user opens the detail view,
not at score time (keeps scoring hot path unchanged; many scored jobs are
never opened). Register the new call site in `llm-surface.md` (ADR-008).

## Alternatives considered

- **Recompute gap analysis fresh:** rejected — duplicates the expensive scoring
  work, burns scarce quota, and risks the enhancement gaps disagreeing with the
  gaps we already showed the user.
- **No LLM call, template the gaps directly:** rejected — can't honestly tell a
  wording gap from a real gap, which is the whole value; would either over-claim
  (fabrication risk, GOV-005) or be generic.
- **Generate at score time for every job:** rejected — pays for enhancement on
  jobs the user never opens; scoring hot path must stay lean.

## Consequences

- One new Gemini call site (per opened job, cached) — modest, lazy, quota-aware.
  Must be added to `llm-surface.md` and follow ADR-008 (JSON out, language
  instruction).
- Enhancement is only as good as the score-time `gaps`; a bad gap list yields a
  bad suggestion. Acceptable — improving gaps is REQ-016's job, and coupling
  keeps the two views consistent (a feature, not a bug).
- The `wording` vs `real` split is an LLM judgment; borderline cases will
  misclassify. GOV-005 makes the safe failure mode explicit: when unsure, treat
  as `real` and state it honestly rather than suggest an unearned rewording.
- The "close it for real" (courses) path is deliberately absent; when Phase 3
  adds it, `kind: real` is the natural hook — a later ADR, governance-gated.
</content>
