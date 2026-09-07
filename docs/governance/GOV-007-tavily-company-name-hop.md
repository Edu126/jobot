# GOV-007: The Tavily hop — company name/role leave to a search provider

Date: 2026-09-03
Relates to: ADR-029 (Tavily search source), REQ-023 (Prep), ADR-027 (outlook),
GOV-001 (résumé text → Gemini), GOV-005 (enhance ≠ fabricate)

> Written before the Tavily integration ships. Prep's company outlook adds one
> new external hop; this is the note for what leaves the system on it.

## Data involved

Only the **company name** and (optionally) the **role title** the user is
interviewing for — plus jobot's Tavily API key. **No candidate PII, no résumé
text, no user identity** goes to Tavily. The company/role are low-sensitivity
(employer-side facts), though the *pairing* leaks that *someone* is prepping for
that role at that company. The returned search snippets are public web content.

## Who can access it

Tavily (the search provider) receives the query; jobot's server makes the call;
Gemini then receives the returned snippets to structure (same GOV-001 path).
**No employer/recruiter surface** — reinforces GOV-003.

## Where it lives and where it travels

New outbound hop: jobot server → **Tavily API** (company + role as the query).
Tavily's results (public snippets + URLs) come back, get structured by Gemini
(GOV-001), and are cached in `company_outlook` (local SQLite). The query is not
persisted beyond Tavily's own logging (their policy governs that).

## Risk accepted

- **A search provider sees which companies/roles our users target.** Low
  sensitivity (no PII, no identity), and it's the minimum needed to fetch public
  company info. Accepted for the POC. If we ever attach user identity to the
  query, revisit.
- **Snippets are untrusted web content** fed to an LLM → prompt-injection
  surface. Mitigation: hop-2's structuring prompt treats snippets as inert data
  and forbids inventing facts (GOV-005), same discipline as `from_url` (site #4).
- **Key absence / provider outage** degrades gracefully to the honest "no intel"
  fallback — no fabrication, no crash.

## Revisit when

- We switch provider (e.g. Perplexity — its own note, more data in the hop) or
  add a résumé-aware query (would put candidate data in the hop).
- Multi-user / shared infra (aggregated query patterns across users change the
  exposure).
- First paying user, or a provider ToS/data-retention change.
