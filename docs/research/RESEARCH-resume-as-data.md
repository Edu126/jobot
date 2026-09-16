# RESEARCH-resume-as-data — what the industry actually does, and what it says about REQ-039

Date: 2026-09-16
Plan: [RESEARCH-PLAN-resume-as-data.md](RESEARCH-PLAN-resume-as-data.md)
Feeds: [REQ-039](../requirements/REQ-039-resume-as-structured-data.md),
[ADR-045](../decisions/ADR-045-structured-resume-generation-side-first.md),
[REQ-037](../requirements/REQ-037-scoring-gap-hygiene-and-off-lane-overscoring.md),
[REQ-022](../requirements/REQ-022-structured-profile-parse.md)
Status: **Delivered — awaiting Eduardo's review before anything becomes a REQ/ADR amendment.**

## TL;DR

1. **REQ-039's stated premise does not survive contact with the evidence.** "A
   breakdown score increases transparency and therefore trust" is weakly
   supported at best, and the closest study to our domain found *limited*
   effect. Worse: quantifying a dimension makes people over-weight it
   regardless of whether the number is any good — and ADR-019 already proved
   ours drift ±3–10. A four-number breakdown is four chances to manufacture
   false precision instead of one.
2. **The data-model precedent we should copy is Textkernel's, not JSON
   Resume's.** The load-bearing field is a skill pointing at the work-history
   entries that evidence it. JSON Resume has no such field and cannot support
   per-dimension scoring.
3. **The templates bet is the weakest leg** — the "ATS can't read columns"
   literature is essentially vendor fear-marketing, and our own `ats.py`
   tells users to re-flow into a single column.
4. **The strongest finding in the whole run is one nobody asked for:** a
   preregistered field audit (n=9,022 real applications) found that rendering
   work history as *years worked* instead of *employment dates* raised real
   callbacks ~8–15%, with the largest gain for people with career gaps. That
   is impossible on flat strings and trivial on structured data.
5. **Grounding: go numeric, not semantic.** General faithfulness metrics all
   carry a real false-rejection rate — the exact failure that broke us in
   ADR-015. Numeric provenance is a separate, tractable, near-zero-cost check.

---

## Pillar 1 — Schemas, parser entity models, and the layout reality

- **JSON Resume models a skill as `{name, level, keywords[]}`, with `level` as
  free text.** No proficiency scale, no recency, no link to the experience that
  evidences it; `work` entries carry no computed duration, seniority, or gap
  detection. → Source: jsonresume/resume-schema `schema.json` · Confidence: high.
- **Textkernel gives every extracted skill a `FoundIn` field — a list of
  work-history item IDs where that skill was evidenced — plus `LastUsed` and
  `MonthsExperience`.** ✓ verified against
  [developer.textkernel.com](https://developer.textkernel.com/Parser/master/data_model/candidate-data-model/):
  *"a comma-separated list of Work History items Id's indicating where the skill
  was found"*; `LastUsed` is *"derived from position dates"*. · Confidence: high.
- **Textkernel also computes seniority/experience server-side**, de-duplicated
  across overlapping jobs (`MonthsOfWorkExperience`, `AverageMonthsPerEmployer`,
  `MonthsOfManagementExperience`, `CurrentManagementLevel`, `NormalizedTitle`).
  The arithmetic is in code, not in a model. · Confidence: med-high.
- **schema.org's `skills` property has range `Text` only** — a bare string,
  flagged by its own community as unable to reference a taxonomy. · Med.
- **No methodology-disclosed study comparing ATS parse accuracy on single- vs
  multi-column résumés could be found.** The space is dominated by
  résumé-builder marketing with suspiciously precise, un-sourced statistics.
  This is an *absence-of-evidence* finding and should be treated as one. · High.
- **The one genuine vendor-primary signal:** Greenhouse's own support docs list
  "a columned layout" among named causes of failed résumé parsing. The
  defensible mechanism is **scrambled reading order**, not "ATS can't read
  columns" — text is usually extracted, but field↔bullet association breaks. · Med.

## Pillar 2 — Skill taxonomies as the join key

- **ESCO is the only viable one for us bilingually**: ~3,039 occupations /
  ~13,939 skill-and-knowledge concepts across 28 languages with current,
  maintained Spanish. · Med-high.
- **O*NET's Spanish is disqualifying** — only the legacy v4.0 translation
  exists, with no plans to update, against a current v31.0. · High.
- **Lightcast Open Skills (~34k skills, biweekly updates) needs a paid
  contract for API access** — out for a free-tier app. · Med-high.
- **ESCO's slow versioned cadence structurally guarantees coverage gaps** for
  emerging tools. · Med-high.
- **LLM in-context skill extraction is *inferior* to traditional supervised
  methods** (better only on syntactically complex mentions) — Nguyen, Zhang,
  Montariol & Bosselut, *Rethinking Skill Extraction in the Job Market Domain
  using LLMs*, NLP4HR 2024 ✓ verified. So "just let the LLM extract and link"
  is not automatically safer than "let the LLM score". · High.
- **Cross-lingual linking to ESCO is still an open research problem** (MELO
  benchmark, 21 languages, baselines only). · Med.
- **Evidence gap, stated plainly:** no paper directly measures
  taxonomy-linked vs free-text scoring on *run-to-run reproducibility* for job
  matching. Support for our hypothesis is indirect. · High (as a gap).
- **We already run the recommended lightweight middle path**: `gap_map.py`
  generates a `canonical` label per gap, persists it, and feeds known
  canonicals back as anchors. Extending that mechanism to score-relevant
  skills is far cheaper than importing an ontology. · High.

## Pillar 3 — Per-dimension scoring and the trust question

**The premise check (this is the important part).**

- **Closest study to our exact domain:** Hannibal & Bauer, *The Challenge of
  Understanding Explanations for User Trust in AI: Insights From an Online
  Experiment About Job Matching* (LNCS vol. 16109, 2026) ✓ verified — a
  mock job-recommender ("JobMatcher"); varying the explanation had **limited
  effect on trust in the algorithm or understanding of the match**. · High.
- **Content-free explanations buy the same trust as real ones:** Eiband,
  Buschek, Kremer & Hussmann, *The Impact of Placebic Explanations on Trust in
  Intelligent Systems*, CHI'19 EA, n=30 ✓ verified — placebic explanations
  *"may indeed invoke perceived levels of trust similar to real explanations."*
  A breakdown can raise trust **without informing anyone**. · High.
- **Quantifying a dimension makes people over-weight it, independent of its
  validity:** Chang, Kirgios, Mullainathan & Milkman, *Does counting change
  what counts? Quantification fixation biases decision-making*, PNAS 2024 —
  21 preregistered experiments, N≈23,000, **hiring decisions included** ✓
  verified. · High.
- **Users overestimate how much they understand** from feature-level
  explanations (illusion of explanatory depth) — Chromik et al., IUI 2021. · Med.
- **Inaccurate explanations are worse than none** — they read as a deceptive
  experience and erode trust (Papenmeier et al., ACM TOCHI 2022, n=959). · Med.
- **Architecture consensus:** every credible pipeline separates LLM
  *extraction* from deterministic *scoring*. Code owns the arithmetic. This is
  the same lesson ADR-006→ADR-015 taught us the expensive way. · High.

**Seniority and recency — both are landmines.**

- **Prior work experience barely predicts performance:** Van Iddekinge,
  Arnold, Frieder & Roth, *A meta-analysis of the criterion-related validity of
  prehire work experience*, Personnel Psychology 72(4) ✓ verified — corrected
  correlations **.06 for job performance** (k=44, n=11,785), .11 training,
  .00 turnover. Weighting "years of experience" heavily is not merely risky,
  it is close to non-predictive. · High.
- **Recency decay is mathematically the same mechanism that penalises
  caregivers and returners** (Weisshaar, ASR 2018; Kristal et al., Nature
  Human Behaviour 2023). Any decay curve needs an explicit gap-exemption path
  or it is a governance issue, not a UX one. · Med-high.

**⭐ The unasked-for finding that actually moves outcomes.**

- **Kristal, Whillans, Bailey et al., *Reducing discrimination against job
  seekers with and without employment gaps*, Nature Human Behaviour 7 (2023)
  ✓ verified** — preregistered field audit, **n=9,022 real résumés sent to real
  employers**: rewriting a résumé so prior jobs list **the number of years
  worked instead of employment dates** raised callbacks ~**8%** for applicants
  without gaps and ~**15%** for applicants with gaps; the effect holds for
  male and female applicants and is driven by making experience salient. · High.
  → This is the only *measured real-world outcome* win in the entire run, it
  directly serves candidates the market penalises, and **it is impossible to
  implement on flat strings**: you can only re-render dates as durations if
  dates are fields.

## Pillar 4 — Grounding and provenance for generated content

- **Every general faithfulness method carries a real false-rejection rate** —
  NLI-based (SummaC, TACL 2022 ✓ verified; AlignScore, ACL 2023), QA-based
  (QAGS/QAFactEval), and LLM-as-judge (G-Eval, Spearman ≈0.51 even with a
  frontier model). None is near-perfect. That rate is exactly what silently
  dropped ~100% of our results in the ADR-015 incident. · High.
- **Numeric hallucination is its own tractable sub-problem**, with dedicated
  prior work (HERMAN, Findings of EMNLP 2020) and evidence that NLI models are
  specifically weak at quantitative reasoning (EQUATE, CoNLL 2019). A dedicated
  deterministic numeric check beats a general semantic one. · Med-high.
- **Self-reported attribution is unreliable in the open case** (RAG citation
  hallucination reported at 11–57%) — but our case is a **closed set**: "which
  of these N original bullets did this come from?" is a far narrower task.
  Usable as a cheap narrowing signal, **not** as the sole verifier. · Med.
- **Never auto-block rendering.** Tiered warn/flag (per-bullet highlight for a
  numeric mismatch, aggregate flag otherwise) makes the worst-case false
  positive an ignorable highlight rather than a broken feature. · High.

---

## Tensions this run exposes

1. **REQ-039 vs REQ-037.** REQ-039 asserts the score is accurate; REQ-037
   documents it as *inflated* on real user data six days earlier. Unresolved.
2. **REQ-039's ρ 0.75–0.86 has no committed data.** `EXP-001` is status
   `planned`; `git log -S` traces the figure to the single commit that wrote
   the prose. It is also replicated into `core/matching/fit_story.py:4`.
3. **ADR-045 vs REQ-022.** They propose opposite phase orders
   (generation-side-first vs parse-side-first) and neither cites the other.
4. **Templates vs our own ATS advice.** `core/resume/ats.py:204` tells users
   to *"Re-flow content into a single column"* while REQ-039 Phase 1 plans a
   two-column template.
5. **ADR-045 cites ADR-005 (fidelity in the contract layer) but its phase
   order forfeits fidelity verification** — structure on the output side only
   leaves nothing on the input side to verify against.

## Implications

| # | Finding | Action hook |
|---|---|---|
| 1 | Breakdown→trust is weakly supported; quantification fixation + drift = false precision | Amend REQ-039: breakdown ships as **counts/labels + evidence**, never as 4 scores |
| 2 | Textkernel's `FoundIn` is the real precedent | New ADR: the schema's load-bearing field is `evidenced_by: [claim_id]` |
| 3 | Years-worked rendering raises real callbacks 8–15% (n=9,022) | New REQ: highest evidence-per-effort feature in the backlog |
| 4 | Recency decay ≡ caregiver penalty; YoE barely predicts (r≈.06) | New GOV before any decay/seniority weighting ships |
| 5 | Column-parsing evidence is marketing, and contradicts our own `ats.py` | Amend REQ-039 Phase 1: decide the ATS stance before building templates |
| 6 | Numeric provenance is cheap; semantic grounding repeats ADR-015 | New REQ/ADR: numeric-delta check on tailored bullets, warn-not-block |
| 7 | Don't import ESCO; extend `gap_map`'s canonical mechanism | Note on REQ-039; taxonomy adoption stays out of scope |
| 8 | LLM extraction is inferior to supervised SE | Kills "extraction is inherently safer than scoring" as an assumption |

## Decisions for Eduardo

1. **Run EXP-001, or downgrade the ρ claim** in REQ-039 + `fit_story.py`. It is
   currently load-bearing for ADR-045 and unsupported.
2. **Reconcile REQ-037 first** — if the score is inflated, the breakdown is a
   *diagnostic instrument*, not transparency, and its design changes.
3. **Choose the phase order:** ADR-045 as written (cheap, forfeits
   verification) vs REQ-022's order (costlier, buys fidelity + grounding).
4. **Decide the templates stance** before Phase 1 — shipping a layout our own
   checker penalises is a vision-#1 problem, not a design one.
5. **Approve or reject the two evidence-backed quick wins** (numeric
   provenance check; years-worked rendering) independent of the big bet.

## Verification note

Crossref, OpenAlex, doi.org and aclanthology.org were all blocked by this
environment's egress proxy (gateway 403 on CONNECT), so the skill's standard
`curl`-based verification could not run. The load-bearing citations were
instead verified via web search against publisher pages and marked ✓ above.
Claims not individually verified are marked with their confidence and should
not be hard-cited in an ADR without a second pass. Per-pillar briefs with full
source lists are in the session scratchpad.
