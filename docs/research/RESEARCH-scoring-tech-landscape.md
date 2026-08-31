# RESEARCH-scoring-tech-landscape — NA taxonomies + industrial matching architectures for jobot scoring v2

Date: 2026-08-28
Status: Draft — reviewed high-level with Eduardo pending
Feeds: REQ-016, ADR-016, ADR-017 (JD-language source of truth), GOV, RESEARCH-market-thesis (iteration 3)
Mode: deep (2 pillars, 2 Sonnet sub-agents + consolidation)

## TL;DR
- **ESCO beats O*NET for our markets, decisively.** ESCO has full human-translated
  Spanish + French skill labels (13,890 skills, downloadable CSV per language,
  each with a stable URI); O*NET's Spanish is partial and its skill set is *not*
  what any modern pre-trained model targets. TalentCLEF (the field benchmark) is
  built entirely on ESCO. → confirms the monolingual-ESCO direction; rejects O*NET.
- **Why iteration 2 only saw TalentCLEF:** it *is* the primary shared benchmark,
  and it's ESCO-based. The rest of the landscape (SkillSpan, ESCOXLM-R, NNOSE,
  DECORTE) are datasets/models, not benchmarks — all ESCO-anchored, mostly English
  with multilingual backbones covering es/fr.
- **Language detection has a concrete answer:** `fastText lid.176` at the
  *paragraph* level (not document) — catches JDs with EN corporate boilerplate but
  ES "meat." Directly implements the nuance Eduardo raised.
- **JUDE (LinkedIn) validates the upgrade path *and* tells us what to reject.**
  Borrow: precomputed offline embeddings + local cosine (replaces TF-IDF), and the
  retrieve-then-rerank separation. Reject: the entire serving stack (Kafka/Brooklin
  nearline, IVFPQ ANN, hash-daemon, A/B infra) — scale-only, active harm to copy.
- **The one real decision for Eduardo:** how far to modernize *now* — ESCO-vocab
  filter only (cheap, fixes the pollution the quick test exposed) vs. also swapping
  TF-IDF → local sentence-embeddings (better signal, +dependency).

## Findings

### Pillar 1 — NA taxonomies & benchmarks
- **ESCO dominates modern ML skill-matching; O*NET is secondary** → Gascó Fabregat
  et al. 2025, *Overview of TalentCLEF 2025* (DOI 10.1007/978-3-032-04354-2_24, ✓
  OpenAlex W4413922034) → "Task B … built on top of ESCO job titles and skills";
  76 teams, 280+ submissions → **high**.
- **O*NET is used as a lookup/grounding KB, not the annotation schema** → ScienceDirect
  2025, *job matching … using transformers and the O*NET database* (DOI unverified via
  API ⚠, URL live) → "extract information matched against O*NET entities" → **med**.
- **SkillSpan is the canonical English skill-span NER dataset; maps to ESCO** → Zhang
  et al. 2022 (DOI 10.18653/v1/2022.naacl-main.366, ✓ W4225106321) → 265 postings,
  12.5K spans; JobBERT domain-adapts BERT to it → **high**.
- **ESCOXLM-R is the best multilingual skill-extraction backbone; covers es + fr** →
  Zhang et al. 2023 (DOI 10.18653/v1/2023.acl-long.662, ✓ W4385572628) → XLM-R
  further-pretrained on ESCO in 27 languages, +3.7 F1 over SOTA → **high**.
- **ESCO Spanish is complete; O*NET Spanish is partial** → IADB *Skills Taxonomy for
  LAC* (⚠ grey lit) + ESCO official site (✓) → full es labels for all 13,890 skills;
  LatAm maps to ISCO-08, which ESCO aligns to → **high** on the language fact,
  **med** on LAC deployment.
- **ESCO downloadable as monolingual CSV per language, with URIs (es, fr, en)** →
  ESCO v1.2.1 download portal (✓ official) → "CSV files … are mono-lingual, any
  ESCO language can be selected" → **high**. This is exactly the monolingual-per-market
  vocabulary ADR-017 needs.
- **NNOSE: kNN over ESCO embeddings beats fine-tuned classifiers, no retrain on
  taxonomy update** → Clavié et al. 2024 (DOI 10.18653/v1/2024.eacl-long.35, ✓
  W4411630218) → arXiv:2401.17092 → **high**. The retrieval-style skill extraction
  that fits "no retraining" constraints.
- **Language detection: fastText lid.176, paragraph-level, for mixed-language JDs**
  → fast-langdetect docs + practitioner consensus (⚠ non-peer-reviewed); GlotLID
  (Kargaran et al. 2023, DOI 10.18653/v1/2023.findings-emnlp.410, ✓ W4389518894) is
  the rigorous alternative but overkill for es/fr/en → ~95% acc, 80× faster than
  langdetect; per-paragraph top-k → **med** (practitioner), **high** (fastText suffices).

### Pillar 2 — Industrial matching architecture (JUDE + peers)
- **JUDE = two-tower LLM encoders (member / job), compared via ANN at serving; not
  cross-attention** → LinkedIn Eng blog 2024 (✓ primary, engineering-blog) + ZenML
  write-up → "one LLM powers two specialized towers" → **high**.
- **Cross-encoders are more accurate but rejected at scale; LinkedIn distills a 7B
  cross-encoder into the bi-encoder, closing ~50% of the gap** → same blog +
  secondary → **high**. Confirms: cross-encoder = quality ceiling, bi-encoder =
  what you actually serve.
- **Freshness via nearline streaming (Kafka/Brooklin → Samza), ~270ms, 200+ QPS** →
  blog + Datanami on Brooklin (✓) → **high**. Pure scale machinery.
- **MD5-hash change detection skips re-embedding unchanged text (~3–6× fewer LLM
  calls)** → blog via ZenML (✓) → **high**. The *idea* (don't recompute unchanged
  embeddings) is cheap and worth keeping; the daemon around it is not.
- **ANN serving via IVFPQ (Zelda)** → blog (✓) → exact cosine over a few hundred
  vectors is faster than IVFPQ at our size → **high** (reject).
- **ConFit 2024: contrastive (InfoNCE) fine-tuning meaningfully beats plain cosine
  for person–job fit** → Yu, Zhang, Yu, ACM RecSys 2024 (DOI 10.1145/3640457.3688108,
  ✓ peer-reviewed) → **high**.
- **Resume2Vec 2025: dedicated resume embeddings beat TF-IDF for ATS/matching** →
  DOI 10.3390/electronics14040794 (✓ peer-reviewed) → **high**.
- **conSultantBERT 2021 / CareerBERT 2023: Siamese Sentence-BERT bi-encoders give
  sharper geometry than TF-IDF, meaningful cosine without a cross-encoder** →
  arXiv:2109.06501 (⚠ preprint), DOI 10.48550/arxiv.2310.15636 (⚠ preprint) → **med**.
- **JUDE self-reported impact: +2.07% qualified applies, −5.13% dismiss-to-apply**
  → blog (⚠ self-reported, no audit) → **med**.

## Tensions / open questions
- **Determinism + no-API-hot-path vs embeddings (ADR-016).** *Resolved:* embeddings
  are computed **offline at job-ingest** and cached with the job; runtime is numpy
  cosine — deterministic, zero API in the hot path. Consistent with ADR-016. The
  cost is a new local-model dependency (~80MB sentence-transformer) and CPU at ingest.
- **ESCO is EU-built.** Spanish/French labels are complete, but LatAm-specific slang
  or Canada-specific French terms may be under-covered (med confidence). Mitigation:
  keep the domain-hint fallback for terms ESCO misses; monitor via the outcome loop.
- **How heavy a skill-extractor?** ESCOXLM-R/NNOSE is a real model; the current
  engine just picks top-TF-IDF terms. REQ-016 said "embeddings only if coverage
  proves insufficient" — the quick test showed coverage *is* polluted, so a lighter
  first step (ESCO vocabulary as an allow-list filter) may fix it without the model.

## Implications for jobot   ← the bridge to the product
| Finding | So what for jobot | Action hook |
|---|---|---|
| ESCO > O*NET for es/fr; downloadable monolingual CSV+URI | Standardize on ESCO per-market vocab (es, fr, en); drop O*NET | ADR-017 + REQ-016: ESCO monolingual vocab |
| ESCO vocab is an allow-list of *real* skills | Filter JD skill-terms through ESCO → kills company-name/stopword pollution seen in quick test | REQ-016: skill extraction = ESCO-filtered |
| fastText lid.176, paragraph-level | Detect JD language on the "meat," not boilerplate | ADR-017: language detection method |
| JUDE: precomputed embeddings + local cosine | Optional upgrade: TF-IDF → offline sentence-embeddings, cosine at runtime; still no-API-hot-path | REQ-016: delta/similarity engine (decision below) |
| JUDE: retrieve-then-rerank separation | Make explicit: embedding cosine = retrieval, ESCO coverage bucket = re-rank | REQ-016: engine shape |
| JUDE serving stack (Kafka/IVFPQ/A-B/daemon) | Explicitly REJECT — scale-only, harmful to copy | ADR: non-goals note |
| MD5-hash skip-recompute *idea* | Cache embedding keyed on JD text hash; recompute only on change | REQ-016: cache key (ties feedback_cache_key_all_dimensions) |
| ConFit/Resume2Vec: contrastive > cosine | Aspirational ceiling; needs training data → defer to outcome-loop | GOV/backlog: fine-tune when data exists |
| ESCO EU-centric, LatAm gaps possible | Keep domain-hint fallback; flag potential under-coverage | GOV: bias/coverage note |

## Empirical validation (2026-08-28, ESCO public API, real fixture terms)
Cross-reference requested by Eduardo before committing — results reshaped the vocab design:
- **English incl. `en-us` is a first-class ESCO label variant** (concept labels
  present in 28 langs: en, en-us, es, fr, pt…). NA English coverage: confirmed.
- **Spanish is `es` (Spain) only — no LatAm (`es-419`) variant.** Universal
  competences match exactly (`gestión de proyectos`, `logística`); risk is limited
  to LatAm-specific slang → fallback, not blocking. `pt` = Portugal.
- **ESCO covers *competences* well but NOT all *tools*:** `autocad` ✅ present, but
  `power bi` → "software de edición de audio" ❌, `revit` → "document restoration" ❌,
  `quantity takeoff` → "decide quantity of explosives" ❌. The exact tool terms
  AEC/BI users act on are missing/inconsistent.
- **ESCO search is fuzzy and never returns empty** — an out-of-vocab term yields its
  nearest neighbour (garbage). Naive top-1 would inject *false* skills → must match on
  exact/normalized labels with a threshold, or use the downloaded CSV for exact lookup.
- **Consequence:** the skills vocabulary must be **ESCO competences (exact-label,
  per market incl. `en-us`) + the existing `DOMAIN_HINTS` tools list** (Power BI,
  Revit, Navisworks…) — ESCO alone is insufficient for tooling. Still option (A),
  no embeddings; just correctly specified.

## Decisions to make here (with Eduardo)
1. **Confirm ESCO (monolingual per market) as the skills vocabulary, O*NET dropped.**
   Research says yes decisively. → becomes ADR-017 + REQ-016 edit.
2. **How far to modernize the engine now** (credit + complexity call, yours):
   - **(A) ESCO-vocab filter only** — keep TF-IDF cosine for the delta, add ESCO
     allow-list to fix the coverage/gap pollution. Cheapest; matches REQ-016's
     "embeddings only if coverage insufficient." No new model dependency.
   - **(B) Also swap TF-IDF → local sentence-embeddings** (offline at ingest, cosine
     at runtime). Better semantic signal (developer≈programmer), still no-API-hot-path;
     +~80MB model dep, ~1–2 days. A and B are additive, not exclusive — question is
     sequencing.
3. **Language detector dependency:** confirm `fastText lid.176` (via
   `fasttext-langdetect`) as the paragraph-level detector for ADR-017.
