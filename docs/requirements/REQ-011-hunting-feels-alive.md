# REQ-011: Hunting should feel alive before it feels fast

Date: 2026-08-25
Source: Eduardo (product architect) + Claude (SA peer) — Sprint 8 scoping conversation
Status: Building

## What they asked for

> "Jobot should not make the user wait for intelligence."
>
> "Make Hunting feel alive before making it faster. First we make Jobot
> start delivering value while it works. Then we measure where the
> bottleneck actually is and optimize what the data tells us."

The framing named "progressive discovery + scoring + ranking + presentation
happening independently and asynchronously," across a 60-job universe
scored in batches of 5 with an initial visible window of ~30. The three
numbers must stay independent — changing one later must not require
redesigning the others.

## What they actually need

Today the user submits a search and stares at a spinner for 30–60 s
before the page renders. The scoring half of "feels alive" already ships
(chained batch-of-5 with OOB HTMX swaps at `ui_web/routes/jobs.py:776`).
What's missing is the discovery half: the user should see the results
page — with cards, even without scores yet — while scraping is still
running.

The ask is UX responsiveness, not throughput. The bet: if users see
jobs appearing while the system works, "how long does it take" stops
being the thing they notice.

## How we'll know it worked

Three observable timings, instrumented as `events` rows in Slice 1 so
the weekly Pulse report can track them without new dashboards:

- **TTFJ — Time to First Job.** Seconds from search submit to the
  first job card visible in the results page. Today: effectively
  equal to total scrape duration (30–60 s). Target after Slice 2:
  seconds after the first source responds.
- **TTFS — Time to First Score.** Seconds from search submit to the
  first LLM score badge landing on any card. Today: after full scrape
  completes + first score-batch returns. Target: score-batch starts
  as soon as any jobs exist.
- **Search completion.** Seconds from submit to
  `discovery_complete AND pending_score_count == 0`. Not the
  optimization target for Sprint 8 — measured to catch regressions and
  to establish a baseline for a future "make it faster" decision.

The thing that stops happening: users describing a search as "loading"
for 30+ seconds with nothing on screen.

## Related

- ADR-010 — the four-slice implementation decision and the explicit
  list of what we chose NOT to build in this phase.
