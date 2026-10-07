# EXP-002: Practice-judge leniency (false-solid rate)

Date: 2026-10-07 · Owner: Eduardo + Claude · Relates to: REQ-042 #12, ADR-059, ADR-072

## Question
How often does the session-score judge band a **weak** answer as solid or strong? The quote gate only proves the words were said. `answered`, `example` and `result` are the model's call.

## Method
- **Set:** `tests/fixtures/practice_judge_set.json`, 15 items, each one question + one answer + one competency. Two anonymised interviews: AEC/BIM and operations.
  - **12 junk answers:** off-topic, hypothetical "I would…", "we" only, vague result ("it went well"), duties with no result, buzzwords, credentials instead of a story, too short, blame with no resolution.
  - **3 controls:** 2 strong, 1 solid.
- **Judge:** the real voice-transcript judge (`session_debrief_from_transcript`). It uses the same rubric as the audio path.
- **Runs:** 3 per item, because the score drifts even at temperature 0.
- **Run:** `.venv/bin/python scripts/practice_judge_eval.py --out docs/experiments/results/<name>.md`, about 45 small Gemini calls.
- **Free check:** a fully lenient judge, ticking yes on everything with the whole answer quoted, made all 12 junk answers solid or strong. The code gates alone stop one point.

## Results
| Run | False-solid (junk) | Controls pass | Drift | Report |
|---|---|---|---|---|
| Baseline (2026-10-07) | **7/36 = 19%** | 9/9 | 1/15 items | [before](results/EXP-002-before.md) |
| + ADR-072 band rule | **3/36 = 8%** | 9/9 | 0/15 | [after](results/EXP-002-after-band-rule.md) |
| + strict `result` definition | **0/36 = 0%** | 6/9 ❌ | 2/15 | [result rubric](results/EXP-002-after-result-rubric.md) |
| + quote must include own action | **0/36 = 0%** | **9/9** | 0/15 | [quote rule](results/EXP-002-after-quote-rule.md) |

After the band rule, one junk answer was left: `vague_result_ops`. The model accepted "things were much smoother" as a result. Two prompt changes to the shared `RUBRIC_BLOCK` closed it. The audio judge uses the same block, so both judges get them:
1. **`result` must be concrete and observable**, and must follow from the candidate's own actions. Vague impressions and things that just happened to them count as false. This took junk to 0%, but strong controls began losing `own_actions`. The model quoted only the result sentence, which has no "I", so the code gate removed the point.
2. **The quote must include what they personally did** (8–40 words, up from 30). Controls went back to 9/9.

Lesson: one quote backs all five checks. A rubric change can shift which span the model quotes, so re-run this eval after every rubric or prompt change.

## Limits
- One judge path. The audio path (main voice scoring) shares the rubric but hears audio. It isn't measured here.
- English only. Spanish has a known `own_actions` false negative.
- 15 items is a smoke alarm, not a benchmark. Add every real false-solid users report to the set.
