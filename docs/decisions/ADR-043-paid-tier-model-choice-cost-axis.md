# ADR-043: On the paid tier, choose the primary model by cost, gated on a quality eval

Date: 2026-09-09
Status: Accepted (criterion + plan). The actual switch is conditional on the
REQ-038 eval passing. Amends the model-selection rationale of
[ADR-004](ADR-004-gemini-free-tier-with-fallback-chain.md) (free-tier daily
quota → paid-tier cost). ADR-004 otherwise stands: still Gemini, still the
provider-agnostic `GeminiClient`, still the fallback chain.

## Context

We are off the free tier. ADR-004 picked `gemini-3.5-flash-lite` as primary for
its 500/day quota — moot now. Real usage (jobbotv2-hermana, ~3 weeks) is 100% on
that model; the fallback never fired. Its paid output price ($2.50/1M) equals
full 2.5 Flash and is 6× `gemini-2.5-flash-lite`. Output drives ~70% of cost.
See [[project_llm_cost_baseline]].

## Decision

On the paid tier, **cost is the primary model-selection axis**, not quota.
Adopt `gemini-2.5-flash-lite` as primary **iff** it clears the REQ-038 quality
gate (score correctness, gap honesty, tailor fidelity on real fixtures, N× for
drift). Until then `gemini-3.5-flash-lite` stays primary and becomes the quality
reference. The fallback chain stays for resilience only, not quota.

## Alternatives considered

- **`gemini-3.1-flash-lite`** (out $1.50/1M, −33%). Middle ground; the fallback
  candidate if 2.5-lite fails the gate but we still want a cut.
- **Keep `3.5-flash-lite`.** Zero risk, ~5× the cost. Default if the eval fails.
- **Context caching the résumé.** Rejected at this volume — storage cost
  ($1/1M tok·hr on 3.5-lite) outweighs cents of savings.
- **Switch provider now** (Claude/OpenAI). Out of scope; ADR-004's multi-provider
  plan is separate and this decision doesn't block it.

## Consequences

- If it passes: ~4.7× cost cut (Mehran ~$2.15→~$0.46/mo) with no user-visible
  change; verified in the next `gemini_usage` pull.
- Per-model price now matters operationally → the pulse should show $ per
  identity/day (tokens × a per-model price dict). Small follow-up task.
- Reversible: primary model is one constant in `DEFAULT_MODEL_CHAIN`; a
  regression is a one-line revert.
- Discipline: no per-model prompt forking (ADR-008). If 2.5-lite only passes
  with a bespoke prompt, that counts as failing the gate.
