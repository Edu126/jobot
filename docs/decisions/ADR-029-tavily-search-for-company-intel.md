# ADR-029: Tavily for the company-intel search hop; Gemini keeps structuring

Date: 2026-09-03
Status: Accepted
Relates to: REQ-023 (Prep), ADR-027 (company outlook — hop-1 partially
superseded here), ADR-004 (multi-provider swap point), GOV-007 (Tavily hop),
`docs/research/RESEARCH-company-intel-grounding.md`

## Context

ADR-027 built the company outlook two-hop on Gemini's *Grounding with Google
Search*. On -edu it failed for a **real** company with `429 RESOURCE_EXHAUSTED`
(SSH-diagnosed): the free (no-billing) tier's grounding quota is fragile, and
`fetch_company_context` uses the scoring chain's **primary** model directly, so
scoring/testing starves it. POC volume is tiny and cached forever, so cost is
near-irrelevant; **reliability + decoupling from the grounding quota** is the
real constraint (see the research memo for the verified option comparison).

The pivotal observation: swapping only the **search** hop leaves the
**structuring** hop as a normal Gemini `generate_content` call — which draws the
**abundant** generate_content quota, not the fragile grounding one.

## Decision

Adopt **Tavily** as the company-intel **search** source (hop 1). Its 1,000
searches/month free tier (no credit card) far exceeds POC need. **Hop 2 (Gemini
JSON structuring) and the `company_outlook` cache are retained unchanged** — Tavily
results replace the grounded briefing as hop-2's input. This **partially
supersedes ADR-027** (only its hop-1 source; the structured shape, cache key,
`language_instruction`, and grounded-or-none behaviour stand).

Also (independent quick-win): the intel search no longer rides the scoring
primary model, so scoring can't starve it.

New env var `TAVILY_API_KEY`; absent key ⇒ outlook returns None ⇒ the honest
fallback (unchanged). Register the surface in `llm-surface.md` (hop-1 is now a
non-Gemini HTTP call; hop-2 stays a Gemini site).

## Alternatives considered

- **Perplexity Sonar** (one call, search+cite+structure): best long-term quality
  and simplest pipeline, but needs a card + prepaid credits. **Documented upgrade
  path**, not adopted now (POC friction).
- **Wikipedia/Wikidata** ($0, 50k/mo): great for stable facets but no recent news
  and fails small companies — a future **supplement**, not a standalone.
- **Enable Gemini billing** (5,000 grounding/mo): zero code, but a card just to
  avoid changing one hop when Tavily is $0 and no-card.
- **Keep Gemini grounding, just isolate the model**: reduces starvation but the
  free-tier grounding quota stays fragile — doesn't fix the root cause.

## Consequences

- One new external dependency (Tavily) + `GOV-007` for the hop. The intel path
  now spans two providers (Tavily search → Gemini structure); the fallback
  covers any failure of either.
- $0 at POC; if we ever exceed 1,000 lookups/month (unlikely soon), revisit
  (Perplexity or paid Tavily).
- Quality shifts from Gemini's own grounded synthesis to "Tavily results →
  Gemini structuring" — the model now organizes fetched snippets rather than
  searching itself. Acceptable; hop-2 already forbids inventing facts (GOV-005).
- ADR-027 is only partially superseded; its cache/shape/honesty rules remain the
  source of truth for the outlook's *output*.
