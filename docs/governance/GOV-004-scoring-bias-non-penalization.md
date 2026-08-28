# GOV-004: Scoring must not encode hiring bias

Date: 2026-08-27
Status: Accepted
Relates: REQ-016, ADR-016, GOV-003, RESEARCH-market-thesis

## The concern

Research on AI hiring tools (RESEARCH-market-thesis, iteration 2) documents
real, litigated bias: LLM resume rankers preferred white-associated names
85.1% of the time (Wilson & Caliskan, AIES 2024); Mobley v. Workday alleges
discrimination via proxies like **career gaps**; enrichment pipelines degrade
for **non-English profiles**. jobot serves multilingual users and must not
reproduce these harms in its own scoring or coaching.

## The rules

- **Never penalize career gaps** as a negative signal in fit scoring or
  coaching logic.
- **No demographic proxies** (name, age cues, gaps, school prestige) in
  scoring features.
- **Language-risk transparency:** when a user's profile/resume is not in the
  posting's language, flag that jobot's estimate may *understate* their real
  recruiter score — do not silently lower it.
- **Explainability + versioning:** log the scoring version and the top
  rationale per analysis run, so any score can be inspected.

## Why it's governance

The candidate trusts jobot as *their* agent (GOV-003). A biased score that
quietly disadvantages them betrays that trust and imports the exact harm the
product exists to counter. Any new scoring feature is checked against this note.
