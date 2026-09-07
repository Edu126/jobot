# ADR-027: Company outlook — persist it once, share it between Tailor and Prep

Date: 2026-09-03
Status: Accepted — **hop-1 (the Gemini grounded search) superseded by
[ADR-029](ADR-029-tavily-search-for-company-intel.md)** (Tavily); the
**user-facing "Refresh news intel" affordance superseded by
[ADR-031](ADR-031-refresh-news-gated-not-user-facing.md)** (gated to the
fallback, cost). The structured shape, cache, and grounded-or-none rules here
still stand.
Relates to: REQ-023 (Prep slice 1 — company outlook), ADR-008 (prompt/cache
conventions), GOV-005 (candidate-side employer risk allowed), REQ-017
(land-it stage)

## Context

Prep slice 1 needs a company outlook. `core/llm/company_research.py`
(`fetch_company_context`) already produces one via a Gemini **GoogleSearch**
grounded call — but it is **not persisted**: it re-runs on every Tailor opt-in
and would re-run again in Prep. Constraints real now: the grounded-search call
is comparatively expensive and Gemini quota is scarce (ADR-019/020); per-user
SQLite; ADR-008 rule 3 says cache every varying dimension. Standing tech-debt
note: this call skips `language_instruction` (ADR-008 rule 2) and returns
plain text, not JSON (rule 1).

## Decision

Add a **`company_outlook`** cache table keyed on **(company_norm, role_title,
lang, prompt_version)**, storing a **structured JSON** briefing —
`{culture_tone, strategic_focus, recent_news: [{headline, date, url}],
sources: [url], verified_at}` (the Prep mockup's 3-facet + news panel).
**Tailor and Prep both read/write it** — one briefing, two consumers; re-fetch
only on miss, `prompt_version` bump, or a user **"Refresh news intel"** (below).
`company_norm` is a lowercase/trim normalization for hit rate.

The structured shape is built **two-hop** (revised 2026-09-03 after the Prep
mockup): **hop 1** = the existing GoogleSearch grounded call (plain text +
`sources[]`) — rule 1 (JSON) stays **waived** here, the tool can't do
`response_mime_type=json`; **hop 2** = a cheap JSON-mode call that splits hop 1's
text into the facets — rule 1 **satisfied**. Both hops apply
`language_instruction` (rule 2, fixing the standing tech-debt) and keep the "if
you can't find solid info, say so — do not invent" line (GOV-005: candidate-side
outlook allowed, fabrication not). Register both in `llm-surface.md`.

**User-facing "Refresh news intel" is the ONE sanctioned regenerate** in the
Prep kit — permitted because it re-pulls *live data that ages*, not because the
user distrusts the output (contrast the Q&A bank's banned regenerate, ADR-028).
It re-runs the two-hop for that (company, role, lang) and overwrites the row.

## Alternatives considered

- **Keep recomputing per use (no cache):** rejected — burns scarce grounded-
  search quota; Prep would re-pay what Tailor just fetched.
- **Cache on company only, drop role:** rejected — the briefing focuses on the
  role when provided, so it varies by role; ADR-008 rule 3 requires keying it.
- **Force JSON on the grounded call to satisfy rule 1:** rejected — GoogleSearch
  can't set the JSON mime type; the two-hop (grounded text → JSON structuring)
  gets clean facets without faking compliance. One-hop prompt-and-parse of
  markdown was rejected as too fragile (breaks when the model reformats).

## Consequences

- One new table and cache key. `company_norm` is naive, so "Acme Inc" vs
  "Acme" miss — acceptable, worst case a re-fetch.
- Role in the key lowers cross-role hit rate at the same company — correctness
  over reuse, accepted.
- Fixes the standing tech-debt note (rule 2) and makes the rule-1 exception
  explicit rather than silent. Now **two** calls per (company, role, lang)
  miss (grounded + structuring) — more quota than before, but cached and
  shared across Tailor + Prep, so paid once.
- **Grounding quota (verified 2026-09-03, `ai.google.dev/gemini-api/docs/pricing`):**
  only **hop 1** counts against Google Search grounding; hop 2 is a normal
  `generate_content` call on the fallback chain. Free tier = **5,000 grounded
  searches/month** (then $14/1k); paid tier (Gemini 2.5 Flash/-Lite) =
  **1,500/day** (then $35/1k). With per-`(company,role,lang)` caching and ~5
  users, distinct companies/month is in the dozens — far under the ceiling.
  Gotcha: on a *no-billing* free account, grounding has been reported to fall
  against the base `generate_content` daily quota instead of the 5,000/mo
  bucket — check the project's AI Studio Quotas page for the real assigned
  limit. If it ever bites, the ADR-004 swap to a dedicated search API
  (Brave/Tavily → normal Gemini) is plan B.
- The hop-2 structuring can misparse a vague briefing (e.g. no clear news) —
  acceptable, empty facets render as "nothing found," never invented.
- **Freshness:** company news ages. Resolved via the user "Refresh news intel"
  affordance (the sanctioned live-data exception to non-negotiable #2, distinct
  from the banned Q&A regenerate). No automatic TTL in MVP; add one later if the
  manual refresh proves insufficient.
