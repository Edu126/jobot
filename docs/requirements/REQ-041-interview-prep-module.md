# REQ-041: Interview-prep module (the Prep tab, rebuilt)

Date: 2026-09-21
Source: Eduardo (product owner) — via the `jobot-prep-pack` product decisions
Status: Building

## What they asked for
"Okay we are going to start working on the prep tab." Handed over a product
pack (`01-product-decisions` … `04-ai-pipeline-and-prompts`) and a Stitch
design set. The pack reframes Prep from the current per-vacancy "land-it kit"
into a full **interview-preparation module**: the *Interview* is the central
object (one role + one company + one round), holding a Brief, a Toolkit
(Get Ready), Practice (a live mock with an AI interviewer), and Feedback
(a debrief). Plus an account-level **Story Bank** of STAR stories reused
across interviews, and a per-interview **Readiness** band.

## What they actually need
The current kit answers "how do I land it" for one posting but stops at a
static Q&A list. Candidates practising for real interviews need the thing the
market's leaders do: read the JD → derive 4–6 **competencies** → generate
questions per competency → practise out loud → get feedback scored against a
rubric, in honest **bands** (Strong / Solid / Needs work), never fake
percentages. The credibility story is that Jobot mirrors structured
interviewing, not that it guesses the interviewer.

## How we'll know it worked
A candidate can create an Interview from a Jobot match (or a pasted JD), get a
grounded Brief with competencies + resume-evidence bands in under ~60s, and the
Toolkit's questions all trace back to those same competencies — no orphan
questions, no invented facts, no bare "82% ready" number anywhere.

## Related
ADR-047 (Interview as the central object, replaces the kit),
ADR-048 (competency-first AI pipeline), ADR-049 (live-voice Practice).
Supersedes the direction of REQ-023 once the new module reaches parity.
