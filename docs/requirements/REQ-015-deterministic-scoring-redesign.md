# REQ-015: Deterministic scoring redesign (research-fed)

Date: 2026-08-27
Source: Eduardo (product architect)
Status: Backlog — not started

## What they asked for

After archiving section-based scoring back to a single LLM value
([ADR-015](../decisions/ADR-015-archive-section-scoring-single-value.md)),
design the *proper* scoring model. In the user's words: we need a score
that doesn't change run-to-run (the LLM is non-deterministic), so define a
calculation method the AI feeds rather than a number it invents — while
still showing one overall score and keeping matched/gaps in the detail.

## What they actually need

Stability and trust in the fit score, at low LLM cost, in this stack
(Gemini JSON calls, SQLite cache, no build step, ~4 users), without the
silent-drop failure mode that sank REQ-004/005.

## Input research

`docs/research/RESEARCH-scoring-approaches.md` (agent-produced 2026-08-27)
evaluates single-LLM, LLM-extract-facts→deterministic-formula, embeddings,
hybrid, rubric/anchored, and hard-requirement gating. Its recommendation:
LLM emits a 4-label classification (strong/partial/weak/no match) per
signal → backend maps labels to fixed anchor scores and averages
deterministically; set `temperature=0`; reuse the versioned-cache lever;
surface hard-requirement gating in the UI. Embeddings/hybrid deferred as
over-engineered at this scale.

## How we'll know it worked

Re-scoring the same job+resume yields the same number; no result is ever
silently dropped; cost stays within free tier.

## Related

ADR-015 (archived the interim), ADR-013 (persona), ADR-008 (prompt/LLM
surface conventions). Will need its own ADR when the approach is chosen.
