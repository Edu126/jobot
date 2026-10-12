# REQ-052: Prepared answers that are actually strong — and say so when they aren't

Date: 2026-10-12
Source: Eduardo, notes spoken into -edu session 55 + follow-up
Status: Open — step 1 (reference set) in progress

## What they asked for
On the prepared answers read from the teleprompter: "you're just giving me job
titles, not much about what you actually do… 'housing mission' — what's the
housing mission, how does it play into what I do?"; "you're still giving me
what tools you used, but not the situation nor the results"; "so short, so
lame"; "a bunch of numbers, nothing is connected… like I pulled it out of a
book". "Even in the teleprompter they should see that this answer is vague."
"Let's create on our side some database of good answers, bad answers, medium
answers, and also super extended… one minute, maximum two… plain language…
we just want to get our message across." And a step 0: "the user reviews the
material used for this interview, because maybe not all the answers from the
bank align with this company, so they want to use the ones that connect most."

## What they actually need
Prepared answers built as stories (situation → what I did → result and why it
mattered → link to the role), judged by a rubric we've measured against their
own judgment, with the verdict visible wherever the answer appears — and
control over which of their experiences an interview draws on.

## How we'll know it worked
On the reference set, the evaluator agrees with Eduardo's labels; in Get Ready
and the teleprompter a weak answer is flagged with what's missing; a session
built from weak answers can't score 95.

## The core loop (Eduardo, 2026-10-12)
"Answer questions in your own words, then here is an evaluation with some gaps
and opportunities in how you can refine it; after the user gives data, it can
be rewritten again." So Get Ready flips from AI-first to candidate-first:
1. The candidate answers each question in their own words (typed or spoken).
2. The evaluator returns gaps + opportunities (missing situation, result not
   tied to the action, no why-it-mattered, no link to the role, too long…).
3. The candidate fills the gaps with real data.
4. The answer is rewritten from their words + that data — never invented — and
   re-evaluated. Repeat until strong.

## Plan
0. Material review: stories + résumé items ranked by fit to this interview;
   the candidate checks which to use.
1. Reference set (EXP-003): strong / medium / weak / too-long versions of real
   answers, labelled by Eduardo on a sheet that shows the source.
2. Answer-quality evaluator (separate judge call), measured on the set.
3. Generation rewritten as stories (no 14-word skeleton); badge + fix line in
   Get Ready and the live aid.
4. Session score recalibrated with the same rubric (REQ-042).

## Where it lives (ADR-080)
An account-level Answer Bank holds the loop above; Get Ready picks and adapts
per interview (step 0); Practice validates out loud. English first: build and
review in English, wire the Spanish counterpart without mixing (AGENTS.md).
Reference answers for CMHC: https://claude.ai/artifact/WHCXbaDcLU9RFunCqVfSCP

## Related
Audit of today's pipeline (2026-10-12): no prepared answer is ever evaluated;
skeleton format (≤3 bullets × ≤14 words) and missing "why it mattered" / "link
to role" sections make weakness structural. REQ-042, REQ-051, ADR-057, ADR-058.
