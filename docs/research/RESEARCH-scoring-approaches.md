# Scoring Approaches Research — Résumé ↔ Job Matching

Date: 2026-08-27
Author: Research pass grounded in the current codebase (Sprint 7 state)
Status: Pre-requirement — feeds the next scoring REQ

---

## Problem Statement

Jobot needs a résumé-to-job fit score that is **stable** (same input → same output across runs), **explainable** (the UI surfaces matched skills and gaps, not just a number), and **cheap** (Gemini free tier at ~500 req/day, batched 5-at-a-time, SQLite cache as the cost shock absorber). The section-based approach shipped in Sprint 7 (ADR-006) was the right architectural direction — LLM returns per-section evidence, backend owns the math — but it hit two failure modes under the grounding guard-rail (REQ-005): the `require_all=False` relaxation needed for matched-term summaries was correct, but the overall guard-rail was still dropping scored results silently at rate. Additionally, section-score LLM variance remains non-zero even at temperature 0.4; the model still exercises judgment inside each section's 0-100 range rather than classifying into a small label set. The question for the next REQ is: **which changes to the scoring contract would buy the most stability per unit of implementation cost, given the hard constraints below?**

Hard constraints that every recommendation must respect:
- Stack: Python + FastAPI + Jinja2 + HTMX + Alpine, SQLite, Fly.io. No build step, no heavy ML infra.
- LLM: Google Gemini, batched JSON calls, free tier (500 req/day per model, 3-model fallback chain). Cost is the binding constraint.
- 4 real users today. Solo maintainer + AI pair. Implementation budget is tight.
- Explainability is a product requirement: the UI shows matched / gaps chips on every job card.
- "Never silently drop" is first-class: a result that can't be trusted must be logged and skipped, not silently cached wrong (ADR-005).

---

## Comparison Table

| Approach | Determinism | LLM Cost | Impl Complexity | Failure Modes | Explainability | Fit-to-Model |
|---|---|---|---|---|---|---|
| 1. Single LLM overall score (current baseline pre-Sprint 7) | Low — LLM picks a number | Low (1 number out) | None (reverting to) | Score lottery run-to-run; no structure to audit | Poor — no matched/gaps | Baseline only |
| 2. LLM extracts met/partial/missing labels → deterministic formula | **High** — labels from a small enum, math is deterministic | Low-Medium (more tokens for evidence) | Medium — extend existing section schema | Label boundary ambiguity (met vs partial); grounding guard-rail still needed | **Excellent** — evidence is the explanation | **Strong** |
| 3. Embeddings + cosine similarity | **Highest** — pure math, no LLM at inference time | Zero (local model) or Low (API) | High — new dependency or API contract; no matched/gaps without extra step | No explainability without a second extraction pass; cosine similarity is a bag-of-words proxy | Poor without post-processing | Weak standalone |
| 4. Hybrid: TF-IDF + embedding + LLM re-rank | High for ranking; LLM re-rank reintroduces variance | Medium-High | High — multiple pipelines to maintain | Complexity multiplies failure modes; hard to debug when ranks disagree | Medium — TF-IDF misses give gaps; LLM re-rank can override them confusingly | Weak — overkill for 4 users |
| 5. Rubric/anchored LLM scoring (temp=0, few-shot anchors, fixed rubric) | Medium — temperature 0 narrows but doesn't eliminate variance; Gemini does not expose a seed param | Low (same token count as today) | Low — prompt-only change | "Temperature 0" on Gemini flash models still exhibits run-to-run variation on numeric outputs; anchors help but don't solve | Good — matches/gaps preserved | Medium |
| 6. Hard-requirement gating layered on any scorer | **Highest for knockout decisions** — deterministic binary | Zero (no extra LLM call) | Low — already partially implemented in section schema | Gating requires reliable extraction; still needs a scoring signal underneath | Excellent for hard-req surface | **Complementary, not standalone** |

---

## Per-Approach Deep Dive

### Approach 1: Single LLM Overall Score (Pre-Sprint 7 Baseline)

**How it works.** One prompt asks Gemini: "Rate this résumé against this job, 0-100." The number is whatever the model feels like that day.

**Determinism.** None. Even at temperature 0.4 (current setting), the model's calibration of "what 72 means for a Sales job" shifts between calls. The same pair re-scored 10 minutes later can differ by 10-15 points. This is the root problem ADR-006 was filed to fix.

**LLM cost.** Lowest — shortest prompt, single output field. But the savings are illusory: non-deterministic results mean cache hits are less valuable (you can't trust that a cached 72 and a fresh 72 mean the same thing).

**Failure modes.** Score lottery. No structure to audit. Hard requirements are invisible. Bias cannot be detected or logged. The grounding guard-rail from REQ-005 cannot be applied because there are no evidence strings to check.

**Verdict: rejected baseline.** We are actively reverting section-based scoring to this today as a stability fix, but it is not the long-term answer. Returning to it buys short-term relief at the cost of every quality property the product vision requires.

---

### Approach 2: LLM Extracts Structured Labels → Deterministic Formula ("Direction A")

**How it works.** Instead of asking the LLM for a 0-100 per section (which it has to "make up"), the prompt asks it to classify each dimension into a small, bounded label set — e.g., `strong_match | partial_match | weak_match | no_match` (4 values, not 100). The backend maps labels to fixed numeric weights and computes the score deterministically. This is a refinement of the ADR-006 approach, not a replacement of it.

Example mapping:
```
strong_match  → 90   partial_match → 65
weak_match    → 35   no_match      → 10
```

The LLM's job changes from "give me a number" to "classify this dimension and give me 1-3 evidence phrases." Classification against 4 labels is far more stable than free-ranging numeric estimation: the decision boundary between `strong_match` and `partial_match` is a semantic judgment the model makes reliably; the decision boundary between 82 and 74 is not.

**Determinism.** High. The final score is arithmetic over enum labels. The only variance is in which label the LLM picks (and this can be further anchored with few-shot examples per label). The matched/gaps extraction is still free-text, but it doesn't affect the score — it only feeds the UI chips, which are already validated by the grounding guard-rail.

**LLM cost.** Comparable to today's section-based prompt. The output schema changes shape but not volume: instead of `{"score": 82, "matched": [...], "gaps": [...]}`, it becomes `{"match_level": "strong_match", "matched": [...], "gaps": [...]}`. Token delta is near zero.

**Implementation complexity.** Medium. The existing `_parse_sections` and `_final_score` functions need to be rewritten to consume labels instead of raw integers. The prompt changes its instruction for section scoring. The grounding guard-rail and retry logic are unchanged. The cache schema gains a `scoring_version` bump (the existing version lever from ADR-006 handles this cleanly). Estimated: 2-3 days.

**Failure modes.** The main risk is label boundary ambiguity: the model might classify something as `partial_match` when a human would say `strong_match`, but this is a calibration problem, not a non-determinism problem. A miscalibrated label gives a consistent wrong score; a non-deterministic number gives a different wrong score every time. Miscalibration is diagnosable with a few test fixtures and correctable with few-shot examples in the prompt.

**Calibration across domains.** The label approach is inherently domain-neutral: "does this résumé strongly match the Skills section of this JD" is a question the LLM can answer independently of whether the domain is AEC, Sales, or BI. The domain-neutral persona from ADR-007/ADR-013 is preserved unchanged.

**Explainability.** Excellent. `matched` and `gaps` are still first-class fields per section, still validated by the grounding guard-rail. The hard-requirements list is unchanged. The UI surface (chips on cards, section detail view in the future) maps directly to this structure.

**Verdict: primary recommendation.**

---

### Approach 3: Embeddings + Cosine Similarity

**How it works.** Embed the résumé and each JD with a sentence-transformer or an embeddings API. Score = cosine similarity, rescaled. The existing `tfidf_match.py` does this with TF-IDF vectors; the embeddings version uses a dense vector instead of a sparse bag-of-words.

**Determinism.** Highest possible — pure linear algebra, no model sampling, no temperature. The same text always gives the same embedding (assuming deterministic model weights, which is true for local models and for API models with version pinning).

**LLM cost.** For a local model: zero inference cost per scoring call. For an embeddings API (e.g., Gemini's embedding endpoint): very low cost per call, no quota concern on the same scale as generation models. But: a local model requires a model file and a dependency (`sentence-transformers`, `torch` or `onnxruntime`), which adds 200MB-1GB to the Fly image and introduces a build step for the Rust-compiled components. That conflicts with the no-build-step constraint in ADR-003.

**Failure modes.** Cosine similarity is a proxy for lexical overlap in embedding space, not semantic fit. Two texts with high cosine similarity can be in the same domain but describe incompatible seniority levels or responsibilities. More importantly: **there are no matched/gaps** without a separate extraction pass. The embedding score alone gives the user nothing to act on, which violates the product's explainability requirement. Adding an extraction pass re-introduces an LLM call (and its variance) for the UI fields, making the overall system more complex, not less.

**Verdict: not viable standalone** in this stack given the no-build-step constraint and the explainability requirement. Could be a useful pre-filter (rank candidates before an LLM pass) at higher user counts, but at 4 users with batched scoring it adds complexity without proportional benefit.

---

### Approach 4: Hybrid — TF-IDF + Embedding + LLM Re-rank

**How it works.** A pipeline: TF-IDF cosine similarity gives an initial ranking, an embedding model refines it, and an LLM re-rank pass adjusts the top-N for semantic nuance. Used in high-volume recommender systems to balance cost and quality.

**Determinism.** High for the TF-IDF/embedding stages; the LLM re-rank stage reintroduces variance.

**LLM cost.** Higher than single-pass: the re-rank LLM call is on top of the embedding computation. If the LLM re-rank is on only the top-20, cost is manageable; but the complexity of maintaining three pipelines and keeping their signals consistent is disproportionate for a 4-user POC.

**Failure modes.** Three failure surfaces instead of one. If the TF-IDF pre-filter incorrectly excludes a job, the LLM never sees it. Pipeline disagreements are opaque to debug. At the current user count, the engineering cost far exceeds the quality gain.

**Verdict: over-engineered for current scale.** Revisit post-POC if job volumes grow to where a pre-filter meaningfully reduces LLM call count.

---

### Approach 5: Rubric/Anchored LLM Scoring (Temperature 0, Few-Shot)

**How it works.** Keep the LLM scoring a section 0-100, but: set `temperature=0`, add fixed rubric anchors ("a score of 85 means: all required skills present plus direct experience; 65 means: most required skills present, 1-2 gaps tailoring could close; 40 means: significant gaps but genuine transferable strength"), and add 2-3 few-shot examples showing a résumé + JD + expected score.

**Determinism.** Better than temperature 0.4, but not solved. Gemini's flash models do not expose a random seed. "Temperature 0" in practice means greedy decoding (highest-probability token at each step), which eliminates sampling variance but not the model's calibration variance: the model's internal sense of "what does 72 mean for an Operations role vs a Software role" can still shift between model versions or even between calls on loaded servers. Few-shot anchors narrow the range but require ongoing maintenance as the model updates.

**LLM cost.** The few-shot examples add tokens to every prompt. At 5 jobs per batch and 500-token examples, that's ~2500 extra tokens per batch — non-trivial on free-tier.

**Failure modes.** Still non-deterministic (just less so). Anchors must be maintained as the model updates. The calibration burden shifts to the team (writing and validating examples) rather than being solved architecturally.

**Verdict: a useful complement to Approach 2, not a standalone fix.** The temperature=0 change and the label-anchoring concept from this approach should be folded into the label-classification prompt (Approach 2) — but as a tie-breaker mechanism (e.g., include 1-2 brief examples per label), not as the primary stability mechanism.

---

### Approach 6: Hard-Requirement Gating

**How it works.** Before scoring (or in parallel), classify each JD's explicit hard requirements as met/partial/missing/unknown for this résumé. If any requirement is `missing`, the job is flagged as a knockout regardless of the weighted score. The scoring pipeline still runs, but the UI can surface "You scored 78 but are missing a mandatory P.E. license."

**Determinism.** High for the gating logic (it's backend code over enum labels); medium for the LLM extraction of what the hard requirements are (same label-classification approach applies).

**LLM cost.** Zero incremental if hard requirements are extracted in the same prompt call as the section scoring (as in the current implementation). The hard_requirements list already lives in the section-based schema from ADR-006.

**Implementation complexity.** Near zero — already implemented. The schema, the extraction, the `status` enum, and the `evidence` field all exist today. What doesn't exist yet: a UI surface that acts on a missing hard requirement distinctively (e.g., a badge, a filter, a sort signal).

**Failure modes.** Incorrect extraction of what is vs. isn't a hard requirement (JDs are inconsistently written). The `unknown` status is the safety valve: if the LLM isn't sure, it says so, and the UI can treat `unknown` as "check manually" rather than "missing." The grounding guard-rail already validates `met`/`partial` evidence.

**Verdict: complementary, not standalone.** This is already the right design (ADR-006). The next REQ should surface it more visibly in the UI and should treat the hard-req gating as an independent signal that can't be smoothed away by a high section score. No new scoring logic needed.

---

## Recommendation

**Adopt Approach 2 (label-based classification) as the core scoring contract, with Approach 6 (hard-requirement gating) elevated to a visible UI signal.**

The concrete path:

**Step 1 (next REQ — scoring contract fix).** Replace the LLM's per-section 0-100 numeric output with a 4-label classification: `strong_match | partial_match | weak_match | no_match`. The prompt instructs the LLM to classify and provide 1-3 evidence phrases per section; the backend maps labels to fixed anchor scores and computes the weighted average. The `matched` and `gaps` fields are unchanged — they remain the UI chip source, validated by the grounding guard-rail. Hard requirements remain a separate field, unchanged in schema.

Anchor score mapping (starting point, calibrate with fixtures):
- `strong_match` → 90 (clear, direct alignment, no material gaps)
- `partial_match` → 68 (meets most criteria, minor gaps tailoring could close)
- `weak_match` → 38 (genuine transferable strength but significant gaps)
- `no_match` → 10 (little to no alignment on this section's criteria)

This mapping produces a final score distribution consistent with the current verdict bands (85+/65+/40+/<40) while removing the LLM's ability to express "74 vs 76" — a distinction it cannot make reliably. Bump `scoring_version`; the existing cache-invalidation lever (ADR-006) handles the cache purge lazily.

Set `temperature=0` in `GeminiClient` for scoring calls. This doesn't fully solve non-determinism but removes sampling variance as a contributor.

**Step 2 (same REQ or immediate follow-on).** Surface hard requirements distinctively in the UI. The data already exists; a `missing` hard requirement on a job scored 80 should not look the same as a clean 80. Even a small badge or sort signal would prevent users from applying to legally excluded jobs.

**Incremental path:**
1. Write 3-4 label-classification fixtures (AEC, Sales, BI, career-switcher) covering all four label tiers. Lock them before shipping.
2. Ship the prompt change and `_parse_sections` rewrite behind a `scoring_version` bump. Cache invalidates lazily — no data loss.
3. Validate on the real-user apps (Fly.io) that the grounding drop rate falls vs. the Sprint 7 baseline. The `SCORING_BIAS_SUSPECT` event in `events.py` already tracks this.
4. If calibration feels off after 1-2 days of real scoring, adjust the anchor score mapping (a `scoring_version` bump; no LLM prompt change required).
5. Add hard-req UI signal (badge, sort weight) as a follow-on card once the scoring contract is stable.

**What to leave alone:**
- The batching architecture (5 per call), retry-on-individual-failure, and cache key (resume_id, job_id, lang, prompt_version, scoring_version) are all correct and should not change.
- The grounding guard-rail is correct in design; its `require_all=False` relaxation for matched summaries is intentional and should stay.
- The TF-IDF match in `tfidf_match.py` serves the résumé-tailor keyword gap feature, not the job card scoring. These are separate pipelines and should remain decoupled.

---

## Open Questions for the Team

1. **Anchor calibration.** The label → numeric mapping above is a starting estimate. After the first real-user scoring run under label-classification, do the resulting score distributions match intuition? (A 2x2 spot-check: one strong-fit job, one poor-fit job, for two different domain users.) If the bands feel off, the fix is a `scoring_version` bump and a mapping table change — no LLM prompt edit required.

2. **Temperature 0 availability on Gemini flash-lite models.** The `GeminiClient` currently sets `temperature=0.4`. Confirm that `temperature=0` (greedy decode) is available on `gemini-3.5-flash-lite` and the fallback chain, and that it doesn't affect JSON-mode compliance. If it causes JSON parse failures on some outputs, `temperature=0.1` is an acceptable compromise.

3. **Matched/gaps as classification output or free-text?** The current approach asks the LLM for free-text matched/gaps (validated by grounding check). An alternative is to ask it to select from a list of terms extracted deterministically from the JD (a hybrid of TF-IDF term extraction + LLM selection). This would increase matched/gaps stability at the cost of missing semantic equivalents. Worth a small experiment if grounding drop rates remain high after the label-scoring change.

4. **Hard-requirement UI priority.** Where does a "missing hard requirement" badge rank in the backlog relative to the scoring contract fix? If the scoring contract and the hard-req badge ship together, it's one `scoring_version` bump. If they're split, they're two. Splitting is safer (smaller diffs, easier to rollback) but requires two cache invalidations.

5. **Post-POC embedding layer.** At what user count does a TF-IDF/embedding pre-filter for job ranking become worth the added complexity? The current 4-user load does not justify it. Flag for re-evaluation at ~50 users or ~1000 daily jobs scored.
