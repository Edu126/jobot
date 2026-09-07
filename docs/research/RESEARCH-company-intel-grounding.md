# Research — company-intel grounding source for Prep

Date: 2026-09-03
Status: Complete. Decision recorded in ADR-029; governance in GOV-007.
Trigger: On -edu, company outlook returned the "no intel" fallback for a REAL
company (BDN construction). Evidence-first diagnosis (SSH into -edu) showed the
grounded hop failing with **`429 RESOURCE_EXHAUSTED`** — not "company not found".

## The problem, framed

Prep's company outlook (ADR-027) needs a **live, sourced briefing** (culture /
tone · strategic focus · recent news + citations) at **~$0**, **reliably**, on
the **candidate's side**. It was built on Gemini's *Grounding with Google
Search* tool. Two real failures surfaced:

1. **Grounding quota is fragile on the free (no-billing) tier** — the ADR-027
   gotcha, made real: a 429 on the grounded call ⇒ `get_or_generate` returns
   None ⇒ the honest fallback fires for *every* company, not just obscure ones.
2. **Self-inflicted starvation:** `fetch_company_context` calls `DEFAULT_MODEL`
   (`gemini-3.5-flash-lite`) directly — which is *also the scoring chain's
   primary model* — so a day of scoring/testing burns the quota the outlook
   needs. It also bypasses the fallback chain, so there's no second model.

**Key reframe:** "company intel" is two things with different best sources —
**stable facts** (what they do, culture, focus) and **recent news** (needs live
search). And POC volume is tiny (dozens of companies/month, cached forever), so
**cost is nearly irrelevant; reliability + decoupling from the grounding quota
is what matters.**

## Options (verified pricing/free-tier, Sep 2026)

| Option | Cost @ POC | Reliability | Quality/sources | Effort | External hop |
|---|---|---|---|---|---|
| Gemini grounding (incumbent) | $0 but **quota-fragile** | ❌ 429s, shares scoring model | Good, cited | — | existing |
| **Tavily → Gemini structuring** | **$0** (1,000/mo free, no card) | ✅ decouples from grounding | Good | Low (swap hop-1 only) | +1 (Tavily) |
| Perplexity Sonar (1 call) | ~$0.005–0.012/req = cents/mo | ✅ | **Best** (search+cite is its product); structured output | Low–med | +1 (card + prepaid) |
| Wikipedia / Wikidata | $0 (50k/mo, no key) | ✅ | Known companies only; **no news** | Med | +1 (Wikimedia) |
| Enable Gemini billing | 5,000 grounding/mo free | ✅ | = today | none | existing (needs card) |

**Architectural pivot that dissolves the failure:** swapping only the *search*
hop (Tavily/Perplexity) keeps the *structuring* hop as a **normal Gemini
`generate_content` call** — which draws the **abundant** generate_content quota,
NOT the fragile grounding quota. So the incumbent code (hop-2 + `company_outlook`
cache, ADR-027) is reused almost verbatim; only hop-1's source changes.

## Recommendation

**Tavily for the search hop → keep Gemini for structuring.** Rationale:
- Genuinely **$0** (1,000 free searches/month ≫ our need) and **no credit card**
  — lowest-friction reliable option for a POC.
- **Decouples from the grounding quota** that caused the failure; structuring is
  normal generate_content.
- **Minimal change**: only hop-1's source swaps; hop-2 + cache + prompt stay.
  The `GeminiClient` abstraction + ADR-004 already anticipated a provider swap.
- Perplexity Sonar is the better *long-term* tool (one call, best sourced
  quality) — documented as the upgrade path if intel quality/coverage becomes a
  priority and the card/credits friction is acceptable.
- Wikipedia is a $0 **supplement** for stable facets later, not a standalone
  (fails small companies; no news).

**Do regardless (free quick-win):** stop `fetch_company_context` from sharing
the scoring primary model — the self-starvation in failure #2.

## Action hooks

- **ADR-029** — adopt Tavily as the company-intel search source; hop-2 (Gemini
  structuring) + `company_outlook` cache retained; partially supersedes ADR-027's
  hop-1. Perplexity noted as the upgrade path.
- **GOV-007** — the Tavily external hop (company name + role leave to Tavily).
- **REQ-023** — Phase B.3 note: intel source swapped; fallback stays the honest
  default when a lookup yields nothing (or the key is absent).

## Sources

- [Perplexity Sonar API pricing 2026 (CloudZero)](https://www.cloudzero.com/blog/perplexity-api-pricing/) ·
  [pricepertoken](https://pricepertoken.com/pricing-page/model/perplexity-sonar)
- [Tavily free tier — 1,000 credits/mo (FreeTier.co)](https://freetier.co/directory/products/tavily) ·
  [Tavily pricing (coldiq)](https://coldiq.com/blog/tavily-pricing)
- [Brave Search API free tier killed for new users, Feb 2026 (implicator.ai)](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/)
- [Wikimedia Enterprise free API — 50k/mo, structured contents](https://enterprise.wikimedia.com/blog/enhanced-free-api/)
- [Gemini API pricing — grounding free allowance](https://ai.google.dev/gemini-api/docs/pricing)
