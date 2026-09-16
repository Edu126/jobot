# ADR-049: The debrief is a separate non-Live call over the transcript, lands as an artifact, and never produces a score

Date: 2026-09-16
Status: Accepted (design)
Relates to: REQ-041, ADR-047 (transport), ADR-048 (modes), ADR-016 (bucketed
fit display — no raw %), ADR-032 (user is hero), ADR-005, ADR-008, GOV-005,
GOV-008, research memo Pillars 1–2

## Context

Three findings collide here:

1. **The Live API streams both input and output transcription in the same
   connection** (Pillar 3) — a written record of the call arrives free, with no
   STT hop.
2. **The Live API has no clean "structured JSON at the end" mode** (Pillar 3).
   A scorecard needs either mid-session function calls or a second, ordinary
   `generateContent` call over the transcript.
3. **Feedback works *through* self-efficacy**, not directly on outcomes
   (Petruzziello et al. 2021) — and **coaching improved performance but did NOT
   reduce anxiety** (Tross & Maurer 2008). Meanwhile the entire competitive
   category grades *delivery* (filler words, pace, eye contact) rather than
   substance, and **none of them leave the user with a durable artifact**.

## Decision

**The debrief is a second, ordinary Gemini call** — `generate_json` on the
normal `DEFAULT_MODEL_CHAIN`, over the session transcript the browser posts back
when the call ends. Not a Live call. It inherits every existing convention:
JSON-mode, `language_instruction()`, temperature 0.0, quota accounting, and its
own row in `llm-surface.md`.

**The debrief never contains a PERFORMANCE score** — no grade, no stars, no
"7/10".

*Corrected 2026-09-16 after adversarial review.* This ADR originally justified
that by citing ADR-016 ("no raw %"), which is **`Superseded by ADR-038`** — the
repo already reversed it. ADR-038's actual reasoning is the test that matters:
the objection to a number was that it **drifted run-to-run and invited
regenerate-until-greener chasing**; once the score became coverage-anchored
(ADR-018) and cache-stable (ADR-019), the objection went stale and the number
stayed. So the right move is not to swap the citation and keep the conclusion —
it is to **re-run ADR-038's test** on what we propose:

| Candidate signal | Stays put for the same inputs? | Resists chasing? | Verdict |
|---|---|---|---|
| A performance score of a spoken answer | **No** — uncached and irreproducible; the same person answering twice scores differently | **No** — it is the definition of a number to chase | **Banned.** Also collides with GOV-008's ban on employability inference |
| A **progress count** over the user's own transcripts | **Yes** — a count of facts, not a judgment | **Yes** — you cannot move it without actually doing the thing | **Allowed** |

So: **no performance score, but a progress count is permitted and wanted** —
*"answered 5 of 5 this time, 3 of 5 last time"*, *"defended 2 of the 3 gaps you
flagged"*. Sourced only to deltas in the user's own transcripts, never a
percentage, never comparable across users, never an applicant-percentile (the
one guardrail ADR-038 explicitly preserved from ADR-016). This is also what the
north-star metric — *career advancement per hour of effort* — needs in order to
move against something more than an anecdote.

The output contract is:

- **`strongest_moment`** — one thing they actually said, **quoted from their own
  transcript**, and why it works. Feedback runs through self-efficacy; lead with
  evidence that they already did something right.
- **`one_thing`** — exactly one change for next time. One. Not a list.
- **`unanswered`** — questions where the answer never arrived (silence, "no sé",
  drift). Named honestly, not scored.
- **`substance_notes`** — where an answer did/didn't meet a **specific JD
  requirement**. This is the category's white space: substance, not delivery.
- Delivery observations are **secondary and optional**, never the headline.

**Grounded-or-none applies (ADR-005):** every claim in the debrief must quote or
reference the actual transcript. A debrief that cannot ground on what was said
does not render — we show the transcript alone rather than invented praise.
**Sycophancy is a bug** (non-negotiable #1): "solid answer, no red flags" beats
a manufactured pep talk.

**The call must end in something that outlives it.** The debrief + transcript
persist on the prep session. A "this is better than what the kit had" hand-back
into the STAR bank is the intended follow-up — the loop where *speaking*
improves the *written* kit — and is scoped separately, not in v1.

## Alternatives considered

- **Score the performance.** Rejected on ADR-038's own test (above), not by
  citing a superseded ADR: an unreproducible number is exactly the drifting,
  chaseable kind ADR-038 kept a number *despite* — and it converts the one
  low-stakes surface we have into another judgment (pre-mortem #4).
- **Ban every number, including the progress count.** Rejected — that was this
  ADR's first draft, and it was wrong. It foreclosed a non-gameable signal on a
  precedent the repo had already overturned, and left the north-star metric with
  nothing to measure.
- **Mid-session function calling to accumulate a structured scorecard.**
  Rejected for v1 — it puts evaluation logic inside an unobservable stream
  (ADR-047), and the transcript already gives us everything after the fact.
- **Use the Live model itself to deliver the debrief out loud.** Rejected:
  spoken feedback is unskimmable, uncopyable, and costs output audio tokens for
  content that wants to be read twice.
- **Grade delivery metrics (filler words, WPM, pace).** Rejected as the
  headline — it is precisely what the category already does and what Yoodli
  concedes measures "how you speak, not what you say". Available later as a
  secondary note.
- **No debrief at all (transcript only).** Tempting and honest, but the
  literature's whole causal path runs through feedback → self-efficacy.

## Consequences

- **One new cheap call site**, on the existing chain, with existing quota
  accounting — the expensive part of this feature is the audio, not the analysis.
- The transcript is a **new data class** (the user's spoken words, verbatim) —
  governed in GOV-008, not here.
- "No performance score" will feel like a missing feature to anyone
  benchmarking us against the category. That is the point — and it now rests on
  ADR-038's live test rather than on ADR-016's superseded conclusion.
- The progress count needs **transcripts from more than one call** to say
  anything, so it is dark on a first call and must degrade honestly ("first
  one — nothing to compare yet") rather than showing a lonely "5/5".
- The debrief's honesty is bounded by transcription quality; accented or noisy
  input degrades it. When transcription is visibly broken, show the transcript
  and skip the analysis rather than analyze garbage.
