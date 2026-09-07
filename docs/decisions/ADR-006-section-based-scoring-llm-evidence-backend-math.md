# ADR-006: Section-based scoring — LLM returns evidence, backend owns the math

Date: 2026-08-21
Status: Superseded by [ADR-015](ADR-015-archive-section-scoring-single-value.md)
Relates to: REQ-004

## Context
Today `core/matching/semantic_score.py` asks the LLM for a single 0–100
score + one-sentence reasoning per job. The number is non-deterministic:
re-scoring the same (resume, job) pair on different runs produces
materially different scores. Users see the number and — because there's
no structure behind it — treat it as noise. Hard requirements (mandatory
cert, work auth, minimum years) get folded into the same number, so a
candidate scoring 88 while missing a mandatory license looks the same
as one who genuinely fits. We're also about to swap the prompt
(ADR-007), which will invalidate every cached score — we need a way
to do that without destroying history.

## Decision
- LLM output becomes **per-section evidence**, not a final score. Five
  sections with fixed weights owned in code:
  - Experience & Achievements (30%)
  - Skills & Tools (25%)
  - Role & Responsibility Alignment (20%)
  - Industry / Domain Alignment (15%)
  - Education & Certifications (10%)
- For each section the LLM returns `{score, matched, gaps, reasoning}`.
  It also returns `hard_requirements: [{name, status, evidence}]` where
  `status ∈ {met, partial, missing, unknown}` — **separate from the
  weighted sections**, never folded into the average.
- **Backend** computes `final_score = Σ(section_score × weight)` and
  maps to the existing verdict bands (85+/65+/40+/<40). LLM never
  returns the final number.
- `job_scores` gains `sections JSON`, `hard_requirements JSON`,
  `prompt_version TEXT`, `scoring_version TEXT`. A cached row is served
  only when *both* versions match the currently active values;
  otherwise recompute. Old rows are retained for history/audit.
- UI is not required to change in this ADR — the richer data is stored
  and available for later surfaces (per REQ-004's explicit "no card
  redesign" scope).

## Alternatives considered
- **Keep LLM-owned final score, add prompt anchors.** Tried in spirit
  by the current rubric block; still non-deterministic in practice.
  Rejected — the fix isn't a better prompt, it's removing the LLM from
  the arithmetic.
- **Three sections instead of five.** Simpler, cheaper tokens. Rejected
  — collapses Role↔Industry and Skills↔Experience, which REQ-004
  explicitly wants distinguishable.
- **Add Location / Salary / Work-arrangement as scored sections.**
  Rejected — REQ-004 says these stay as separate compatibility signals,
  not capability fit.
- **Model-picked or config-driven weights.** Rejected — reintroduces
  variance we just removed.
- **Delete cached rows on version bump.** Rejected — loses audit trail
  and re-scores everything at once, spiking Gemini free-tier quota.
  Logical invalidation (version mismatch → recompute lazily) is safer.

## Consequences
- Scoring becomes **stable across runs** for the same input — the
  outcome REQ-004 exists to buy.
- `job_scores` migration required: additive columns + JSON blobs. Old
  rows survive; reads that hit an old row see a version mismatch and
  recompute.
- Prompt gets longer (5-section rubric) → more tokens per scoring call.
  Fits within current per-identity daily caps (`core/llm/usage.py`) at
  4-user load; worth watching if user count grows.
- Hard requirements are now a **first-class signal**, queryable
  independently of the score. Any future UI can highlight a Missing
  hard req even when the weighted score is high. Non-destructive:
  no UI must consume it today.
- Contract-layer testing surface expands: per-section score-stability
  fixtures and hard-req classification fixtures. Fits the
  quality-in-contracts pattern from ADR-005.
- `scoring_version` becomes the lever for future weight changes —
  bumping it invalidates cache without touching prompt or data.
  `prompt_version` is bumped independently when instructions change
  (see ADR-007).
