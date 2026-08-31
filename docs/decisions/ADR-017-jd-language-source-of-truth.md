# ADR-017: The JD's language is the source of truth for scoring

Date: 2026-08-31
Status: Accepted
Relates: REQ-016, ADR-016, ADR-018, RESEARCH-scoring-tech-landscape, GOV (bias R7)

## Context
jobot serves bilingual markets (LatAm/Spain ES, Canada EN/FR). The scoring
bake-off (real resumes × real JDs) exposed two failures: current language
detection mislabels (`Analista Comercial` → `fr`), and string/stem matching
cannot cross languages (Andrea's ES resume vs an EN JD scored 0.00 locally).
Research confirms ESCO covers ES/FR + `en-us`, used **monolingually per
market**. Eduardo's nuance: some JDs carry EN corporate boilerplate over ES
"meat" — detecting on the whole doc misroutes.

## Decision
The **JD's language decides the whole scoring pass** — vocabulary, matching,
and the language gaps are shown in. Detect it over the JD's **meat**
(requirements/responsibilities), not boilerplate, via `fastText lid.176` at
paragraph level. A resume in another language is **not** scored as "genuinely
lacking": the LLM judge credits cross-language evidence (`selección` ≈
`recruitment`), and the mismatch surfaces as a **fixable "wrong-language"
gap** ("localize your resume to this market"). This upholds the REQ-016
have-skill-wrong-word vs genuinely-lack split and mitigates non-English
understatement bias (R7).

## Consequences
- Skills vocabulary = ESCO competences (monolingual per market — single `es`,
  Spain, for now; incl. `en-us`) + `DOMAIN_HINTS` tools (ESCO alone misses
  tooling — validated).
- Language detection runs on the JD meat, not boilerplate; feeds ADR-018.
- Cross-language lives in the LLM judge (ADR-018 approach B), not a translation
  escape-hatch.
- **Guardrail = guidance, not bias.** Meat-detection and cross-language rules
  are taught with few-shot/multishot examples in the prompt (ES "meat" under EN
  boilerplate; `selección`≈`recruitment`) — never a thumb on the scale. Concrete
  examples land in the ADR-018 prompt work.
