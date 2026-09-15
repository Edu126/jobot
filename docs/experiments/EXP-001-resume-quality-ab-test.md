# EXP-001 — Does Jobot make resumes that actually work? (A/B test plan)

Status: **planned** · Owner: Eduardo · Drafted 2026-09-15 · Supersedes the
2026-09-14 proof-of-concept run (`scripts/adversarial_eval.py`, `data/adversarial_eval_*.md`).

---

## Executive summary (one page)

**Why.** We ship two things a user trusts blindly: a **fit score** and a
**tailored resume**. We have never proven either is good. A tiny 15-cell probe
(2026-09-14) already found: the score used to drift on identical text (now fixed
— A1), adding numbers to bullets helps (B), and even good resumes get rejected
for reasons that are *not* bullet quality. This experiment turns that probe into
a real, repeatable measurement we can run before/after every change.

**Question.** For a real candidate applying to a real job, does a Jobot-tailored
resume beat their original one — on ATS parsing and on a recruiter screen — and
do our changes (B = quantified bullets) improve outcomes *without* making the
resume dishonest?

**Design.** Within-subject A/B: the **same (resume, job) pair** runs through
every condition, so each pair is its own control. Two factors:
1. **Quantification**: B **off** (control) vs B **on** (treatment).
2. **Tailoring**: original · conservative · balanced · aggressive.
Jobs are **stratified**: in-domain "matched" vs adjacent "stretch" — analyzed
separately so domain mismatch can't drown the signal (the mistake in the probe).

**Subjects.** Real resumes across domains: Eduardo (BI), Mehran (AEC), hermana
(her field), + 3 fixtures for breadth. ≥4 real subjects.

**Primary metrics.** Recruiter decision (advance/maybe/reject) + 5 rubric axes
(0–5); ATS score (0–100); **quantification axis** (H1); **credibility axis +
warnings count** (H2, the honesty guard); score-stability (regression guard);
honest cosine movement.

**Pre-registered success criteria.**
- **Ship B** if quantification axis rises **≥ +1.5** (B-on vs B-off, paired) AND
  credibility does **not** drop and warnings do **not** rise.
- **Flag the score as misleading (finding C)** if Jobot's fit score correlates
  weakly with the recruiter decision (Spearman ρ < 0.4 on matched jobs).
- **Constrain aggressive** if it raises credibility/keyword-stuffing complaints
  vs balanced with no requirement_match gain.

**Known limitation, stated up front.** The recruiter judge is Gemini — the same
model that writes the resume (judge-and-party). Verdicts are read with a
discount; an **independent judge (Claude) on a 20% subset** quantifies the bias.
This is the single biggest threat to validity and is tracked, not hidden.

---

## 1. Hypotheses (pre-registered — write them before we look)

| # | Hypothesis | Primary metric | Pass bar |
|---|---|---|---|
| H1 | B (XYZ quantification) makes bullets read as outcomes | recruiter `impact_quantification` (0–5), B-on vs B-off | +1.5 mean, paired |
| H2 | B does not trade honesty for numbers | `credibility` axis + `warnings` count | no worse than control |
| H3 | Tailoring beats the untouched original for the same job | `requirement_match` + ATS keyword coverage | tailored > original |
| H4 | Jobot's fit score tracks recruiter reality | Spearman ρ(score, decision) on matched jobs | ρ ≥ 0.4 or flag C |
| H5 | Aggressive over-optimizes | credibility/stuffing complaints, aggressive vs balanced | no rise, or constrain |

## 2. Design

- **Within-subject, paired.** Every (resume, job) pair passes through all
  conditions. Pairing removes "some jobs are just harder" as a confound.
- **Factor A — quantification:** control (B off) vs treatment (B on). *Requires a
  toggle* — see §7.
- **Factor B — tailoring level:** original (no tailoring) · conservative ·
  balanced · aggressive. "Original" is the baseline arm for H3.
- **Job stratification:** for each subject pick **3 matched** (genuine in-domain
  fits) + **2 stretch** (adjacent). Report the two strata separately. Selection:
  `lite_score.rank` for a shortlist, then a human/domain sanity pass so "matched"
  really is matched (the probe skipped this and paid for it).

## 3. Subjects & sample size

| Subject | Domain | Source |
|---|---|---|
| Eduardo | BI / analytics | DB resume #14 |
| Mehran | AEC / construction PM | DB resume #5–8 |
| hermana | (her field) | `jobbotv2-hermana` Fly app → local fixture |
| sara_hr / melisa_grc / andrea_sales | HR / GRC / sales | existing fixtures |

First real run: **4 real subjects × 5 jobs (3 matched + 2 stretch) × 4 levels ×
2 quant-conditions**, minus redundant cells (original arm has no level/quant
split) ≈ **~180 recruiter+ATS evaluations**. Batchable within the Gemini free
tier across a day; the score half is a content-cache hit after the first pass.
If quota is tight, drop to {balanced, aggressive} for Factor B first.

## 4. Metrics (dependent variables, per cell)

- **Recruiter:** decision (advance/maybe/reject) + axes {requirement_match,
  seniority_fit, impact_quantification, clarity_structure, credibility}, each 0–5.
- **ATS:** `ats.run_checks` score 0–100 + critical/structure issue counts.
- **Honesty guard:** `tailoring_warnings` count + credibility axis (H2).
- **Score stability:** same text scored twice must match (A1 regression guard;
  expected 100% now).
- **Honest movement:** `lite_score.delta` cosine, original→tailored.
- **Fidelity:** any experience/education entry dropped (`rewrite._collapsed_sections`).

## 5. Measurement instrument (the judges) & bias control

- **Recruiter judge:** calibrated Gemini judge (`core/resume/recruiter_judge.py`)
  — fair stance, given today's date, normal career patterns protected. Run at
  `temperature=0` and content-cache the verdict so re-runs are stable.
- **Independent-judge subset:** re-judge a random **20%** of cells with Claude;
  report agreement (Cohen's κ on decision) to size the self-judging bias. This is
  the validity keystone — without it the advance-rate numbers are suggestive only.
- **ATS:** heuristic now; a real parser (Jobscan/Resume Worded or an OSS parser)
  on a subset later, to check the heuristic isn't lying.

## 6. Analysis

- Paired deltas per hypothesis (Wilcoxon signed-rank; small n ⇒ report **effect
  size + direction**, not p-value theater).
- Advance/maybe/reject rate by condition and by stratum (matched vs stretch).
- H4: Spearman ρ(fit score, decision) on matched jobs only.
- Every claim ships with the n it rests on.

## 7. What the harness still needs (execution backlog)

1. **B toggle** — `build_rewrite_prompt(..., quantify: bool)` so control (B off)
   is runnable. One flag threaded to `_QUANTIFICATION_RULES`.
2. **Original-resume arm** — evaluate the untouched resume as the H3 baseline.
3. **Job stratification** — matched vs stretch buckets + a human confirm step.
4. **Score↔recruiter correlation** output (H4).
5. **Independent-judge (Claude) path** for the 20% subset (needs an Anthropic key).
6. **Judge verdict caching** — content-cache the recruiter call too, so a re-run
   of the report is free and stable.

## 8. Risks & limitations (say them out loud)

- **Self-judging bias** (Gemini writes and grades) — mitigated by the calibrated
  prompt + the 20% independent-judge subset; not eliminated.
- **Small n / synthetic fixtures** — directional evidence, not proof.
- **Heuristic ATS ≠ real ATS** — validate on a subset.
- **Judge nondeterminism** — judge at temp 0 + cache.
- **"Matched" selection is subjective** — the human confirm step is where bias
  can sneak in; log the reason each job was labelled matched/stretch.

## 9. Decision this experiment feeds

Keep / iterate / revert **B**; whether **finding C** (score↔recruiter divergence)
is real enough to rework what the score measures; whether **aggressive** needs a
guard-rail. Results land in a follow-up ADR/REQ per `CLAUDE.md`.
