# RESEARCH-PLAN-scoring-tech-landscape — NA taxonomies + industrial matching architectures for jobot scoring v2

Date: 2026-08-28
Status: **Launched** (explicit go from Eduardo — "im back, dale").
Mode: deep (2 pillars)
Feeds: REQ-016, ADR-016, ADR-017 (JD-language as source of truth), GOV, RESEARCH-market-thesis (iteration 3)

## The question
Before we build the lite scoring engine (REQ-016), what does the *industrial
and North-American* state of the art teach us — so we modernize instead of
reinventing — about (a) which skills taxonomy/benchmark to standardize on for
an ES-LatAm + EN/FR-Canada market, and (b) which parts of a big-tech job-match
architecture (LinkedIn JUDE) are worth borrowing at jobot's scale?

## Pillars (2)
1. **NA skills taxonomies & matching benchmarks** — Why did iteration 2 surface
   only TalentCLEF? Map the real landscape: O*NET (US), ESCO (EU/multiling),
   and NA-oriented skill-extraction/matching models & datasets (SkillSpan,
   JobBERT / JobBERT-de, Kompetencer, DECORTE cross-lingual work, TalentCLEF
   2024/2025 tasks, Doc2Skill, etc.). Which is the right *monolingual per-market*
   vocabulary for (i) LatAm Spanish and (ii) Canada EN/FR? O*NET vs ESCO coverage
   for Spanish + French. Benchmarks we can actually test against.
2. **Industrial matching architecture (LinkedIn JUDE + peers)** — Read the JUDE
   engineering post (LLM-based representation learning for LinkedIn job recs).
   Extract: representation learning / embedding approach, two-tower vs
   cross-encoder, freshness/nearline serving, distillation, how they handle
   text at scale. Then judge honestly what maps to jobot (single-user, local,
   deterministic, no-API-hot-path per ADR-016) and what is scale-only machinery
   we must NOT copy. Cross-check against ConFit / Resume2Vec already cited.

## Guardrails
- Model: Sonnet sub-agents, one per pillar (2 total).
- Scope: bound to the two pillars above; no wandering into product/psychology
  (already covered iterations 1–2). Search primarily in English.
- Language decision is ALREADY made (context, not a research question):
  JD-language = source of truth, detected over the JD's "meat" (requirements/
  responsibilities), not boilerplate; resume in another language = honest gap
  (option A); ESCO/taxonomy used MONOLINGUALLY per market language. Research
  informs *which taxonomy* and *how detection/extraction is done in practice*,
  not whether to be bilingual.
- Sources: every citation verified (OpenAlex/Crossref) or flagged ⚠. The JUDE
  post is an industry blog (not peer-reviewed) — flag as ⚠ engineering-blog,
  corroborate claims against peer-reviewed work where possible.
- Credit budget: 2 sub-agents + 1 consolidation pass. Hard cap.

## Expected output
One `RESEARCH-scoring-tech-landscape.md` memo (~1–2 pages) with an Implications
table where every row hooks to REQ-016 / ADR-016 / ADR-017 / GOV, plus a
decisions-with-Eduardo section. Reviewed high-level before anything becomes a
REQ/ADR edit.
