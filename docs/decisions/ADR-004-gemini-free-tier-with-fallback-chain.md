# ADR-004: Gemini free tier with fallback chain as the POC LLM

Date: ~2026-07 (documented retroactively 2026-08-21)
Status: Accepted (POC) — multi-provider architecture planned
post-validation, without affecting quality or price.

## Context
POC phase. Budget target: ~$0. LLM is used for scoring, resume
tailoring, resume re-parse, AI summary, BI pulse authoring, search
suggestions, company research, and URL job extraction — real load.
Free-tier limits (500 req/day peak on `gemini-3.5-flash-lite`,
20/day on `gemini-2.5-flash`) are compatible with 4 users at
observed usage.

## Decision
Use Google Gemini via the `google-genai` SDK. Wrap in a
`GeminiClient` that tries a fallback chain
(`gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` →
`gemini-2.5-flash`) — when one hits 429, the client short-circuits
past it for the rest of the day and tries the next. Per-identity
daily-cap accounting (`core/llm/usage.py`) prevents any single user
from starving the others (or from a cost-bomb attacker running us
dry, once we exit the pure-per-user architecture).

## Alternatives considered
- **OpenAI GPT-4o-mini.** Stronger function calling, larger
  ecosystem. Rejected: no meaningful free tier — pay-per-token from
  request one.
- **Anthropic Claude Haiku.** Better prose quality (relevant for
  cover letters). Rejected: same — no free tier fit for the POC.
- **Local llama.cpp.** Zero cost forever. Rejected: ops overhead
  (model files, GPU sizing) not justified during POC on Fly hobby
  plan.

## Consequences
- Zero LLM cost during POC.
- **Locked into Google's rate limits + free-tier quirks.** The
  fallback chain + per-identity cap softens this but doesn't remove
  the dependency.
- The `GeminiClient` abstraction gives us **a clean swap-in point** for
  the post-POC multi-provider architecture — the LLM interface (a
  `generate_json(prompt) -> dict` method) is provider-agnostic.
- Quality is dependent on Google's continued willingness to offer a
  free tier at these limits. If they pull it, migration becomes
  urgent, not planned.
- The prompt-level LatAm Spanish clause (`language_instruction("es")`
  in `core/settings.py`) works across providers by design —
  survives the eventual swap.
- Two well-hardened prompts (`core/matching/semantic_score.py` and
  `core/jobs/from_url.py`) set the pattern that any future provider
  must respect: numeric rubric anchors + explicit false-positive
  lists for scoring; sentinel fence + schema allowlist for extraction.
