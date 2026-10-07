# REQ-042: One inventory of every score Jobot computes — and the rules they share

Date: 2026-10-01
Source: Eduardo (after the Practice Feedback gave "Solid" to junk answers)
Status: Open (living inventory — update when a score is added, changed or retired)

## What they asked for
> "lets put it as an REQ, before we forget so we keep all the scores we are
> calculating in the app, and also the logic we use and make sure we are
> aligned on the heuristics or at least the idea or intention"

## What they actually need
Jobot now shows many grades: fit rings, bands, readiness, ATS score, and the
new session score. Each one was built in a different sprint with its own logic.
Nobody can say in one place what each number means, who computes it (code or
LLM), or why we trust it. When one is wrong (Practice "Solid" for junk), we
can't easily check whether the others have the same flaw. The need is **one
reference** that lists every score and the principles all of them must follow.

## Shared principles (the intention every score must meet)
1. **The LLM gives evidence; code does the maths.** The model extracts facts
   (requirements met, checks passed, quotes). Code counts, sums and assigns the
   band. We never ask the model for a holistic gut number (it drifts and
   flatters).
2. **No credit without proof.** Every positive grade must point to evidence the
   user can see: a résumé line, a quote of their own words, or a matched term.
   If we can't verify the evidence in code, the grade is zero.
3. **Strict by default.** When unsure, the answer is "no". An unknown or blank
   grade becomes the weakest band (`band_or_default` → `needs_work`). We never
   round up.
4. **Explainable.** Each score shows *why* next to it (checks, gaps, quotes).
   A bare number with no reason is not allowed.
5. **Words before numbers.** The verdict label is the headline and the number
   supports it. We show a raw 0–100 only where it's built from countable parts
   (session score, ATS) or calibrated against a recruiter (fit ring).
6. **Reproducible.** `temperature=0`, versioned prompts, and deterministic code
   gates. Running the same input twice should land in the same band.
7. **Fair denominators.** We don't punish the user for something they weren't
   asked (not-asked competencies are excluded).
8. **Real numbers come from code.** wpm, fillers, seconds and counts are
   measured, never estimated by a model. The model once guessed 305 wpm for
   normal speech.

## Inventory

| # | Score (where shown) | Scale → label | Computed by | Logic | Intention |
|---|---|---|---|---|---|
| 1 | **Job fit ring** (Jobs list, detail) — `core/matching/semantic_score.py` | 0–100 → strong_fit ≥85 · workable ≥65 · stretch ≥40 · poor_fit | LLM extracts JD requirements and marks each evidenced/missing; the score is anchored to coverage = evidenced ÷ total | Band thresholds in `_verdict_from_score`. Cross-language evidence counts. A wrong-language résumé is one fixable gap. | "How much of this JD can you prove?" Calibrated vs recruiter (EXP-001, ρ≈0.75–0.86) |
| 2 | **Lite fit bucket** (ranking pre-LLM) — `core/matching/lite_score.py` | Strong ≥0.60 · Good ≥0.35 · Weak | Code | Share of the JD's top-25 skill terms found in the résumé, plus an exact-title check | Fast, honest local ranking, never shown as a % |
| 3 | **Tailoring delta** — `lite_score.delta` / `tfidf_match` | before → after cosine | Code (TF-IDF) | Cosine similarity of résumé vs JD, before and after tailoring | Shows real movement when you tailor, not a chased number |
| 4 | **Affinity** (sort order only) — `core/matching/affinity.py` | raw count, never displayed | Code | Token overlap; title tokens count 3× description tokens | Decides which jobs get the expensive LLM scoring first |
| 5 | **Fit type** (in-lane / reach / pivot / long-shot) — `core/matching/fit_story.py` | label | Code heuristic | Domain words in the title × seniority level (junior<mid<senior<lead) | The *kind* of match that the number hides |
| 6 | **Prep fit band** (Prep context bar) — `core/prep/fit.py` | strong ≥75 · solid ≥50 · needs_work | Derived from #1 | Band only, no number shown | You already have the interview, so the band protects confidence while staying honest |
| 7 | **Gap map** (Profile) — `core/matching/gap_map.py` | counts per gap, top 5 per pillar | SQL counts + LLM classifies wording vs real | Built from jobs scored ≥70 in the last 60 days | Your real, recurring gaps across the market |
| 8 | **ATS score** (Profile) — `core/resume/ats.py` | 0–100 | Code | 100 minus penalties: critical 15 · warning 5 · info 1. Sections detected by content, not headings | Catch the common reasons a résumé gets silently dropped |
| 9 | **Résumé evidence per competency** (Prep Brief) — `core/prep/brief.py` | strong / solid / needs_work | LLM, must quote the résumé line (evidence null → needs_work) | Evidence quote required | How well your résumé already proves each competency |
| 10 | **Readiness** (Prep home, interview rows, Feedback line) — `core/prep/readiness.py` | not_started → getting_there → almost_ready → ready (bar fill only) | Code | brief reviewed → stories mapped to ≥½ → all mapped + 1 practice → every competency solid+ in the **latest** session | "Am I prepared for THIS interview?" (process + results) |
| 11 | **Get Ready self-rating** (answer cards) | nailed / ok / missed | The user | Missed cards lead the next practice session (ADR-056) | The user's own honest read |
| 12 | **Session score** (Practice Feedback) — `core/prep/session_score.py` | 0–100 → ready ≥75 · close ≥50 · not_ready. Ready is capped to close if any competency is needs_work | LLM answers 5 yes/no checks per competency and quotes the user; code verifies the quote and sums | See "Session score" below | "How did THIS rehearsal go, and what exactly was missing?" |
| 13 | **Per-answer band** (typed practice) — `practice._parse_eval` | strong / solid / needs_work | Same checks as #12, one answer | Band derived from the checks; the model's own `overall` is ignored when checks exist | Same as #12 at answer level |
| 14 | **Delivery gauges** (Practice Feedback) — `session_score.delivery_gauges` | pace wpm (good 130–160), fillers **per 100 words** (fluent <2 · typical 2–4 · high >4), answer length (good 60–120s) | Code | Words ÷ speaking seconds, measured server-side from the candidate WAV against its own noise floor, with gaps < 1 s bridged ([ADR-070](../decisions/ADR-070-speaking-time-measured-from-audio.md)); the browser count is only a fallback. Answer length is the average of each answer's measured seconds; in voice, answers are cut where the coach's turns start ([ADR-071](../decisions/ADR-071-voice-answers-split-at-coach-turns.md)); fillers counted from a fixed list and normalised per 100 words. Each gauge shows a research baseline ([REQ-043](REQ-043-delivery-gauges-and-baselines.md)) | Real, countable speaking habits, read against what's normal |
| 15 | **Offline judges** (eval harness only) — `recruiter_judge.py`, `answer_judge.py` | advance 85 / maybe 55 / reject 20; specificity 1–5 | LLM (self-judging caveat) | Recruiter screen of generated résumés; interviewer check of answer cards | Quality control on what WE generate. Not shown to users |

### Session score (#12) — exact logic
- **Five checks per competency.** Each check passed is 1 point:
  - answered the question
  - a real example
  - their own actions
  - a result
  - a number
- **Gates applied in code** (they override the model):
  - The quote must be found in the transcript: a normalized substring, or ≥60% of its tokens. A quote under 3 words doesn't count. If the quote fails, every check is false.
  - `answered = false` → 0 points.
  - `quantified` needs a digit or number word in the quote.
  - `own_actions` needs a first-person word in the quote (I / my / me, je / mon, yo / mi).
    - Known false negative: Spanish that drops the pronoun ("lideré").
- **Band per competency:**
  - strong = all five checks (complete story with a number)
  - solid = answered + example + own actions + result, no number. Only the number is optional ([ADR-072](../decisions/ADR-072-solid-band-needs-the-full-story.md)).
  - anything else = needs work, even at 4/5. Example: "we cut clashes by 40%" has no own actions, so it's needs work.
  - A competency with no question this session is "Not asked". It's shown, but left out of the score.
- **Score** = points ÷ (5 × competencies asked) × 100, rounded.
- **Verdict:**
  - ≥75 ready
  - ≥50 close
  - otherwise not ready
  - It's never "ready" while any asked competency is needs work.
- **Delta:** compared with the most recent earlier finished session that has a score.

### Known weak spots (where we are NOT yet aligned / need watching)
- **#12:** if the model ticks checks on a real-but-weak quote, the code gates can't fully catch it. Answered and example rely on the model. Mitigations:
  - the quote is shown next to the ticks, so the user can see when it's being generous
  - solid needs the full story; only the number is optional (ADR-072)
  - `result` must be a concrete outcome of their own actions, and the quote must include what they did. Measured false-solid: 19% → 0%, with controls at 9/9 (EXP-002).
  - the ready cap
  - measured by `scripts/practice_judge_eval.py` over a junk-answer set ([EXP-002](../experiments/EXP-002-practice-judge-leniency.md)). Track the false-solid rate after every rubric or prompt change.
- **#1 vs #6 vs #12** use different thresholds for similar words ("strong", "solid"). Thresholds should converge or be renamed.
- **#10 only reads the latest session.** One bad short session can drop readiness.
- **#15 judges are self-graded** (Gemini judges Gemini output).

## How we'll know it worked
- Nobody has to read code to answer "what does this number mean?"
- Every new score lands as a row here in the same PR.
- A junk practice session never shows "Solid" again (locked by `tests/test_session_score.py`).

## Related
ADR-059 (session score), ADR-048 (bands not scores), ADR-016 / ADR-018 (fit scoring), REQ-016, REQ-025, REQ-041
