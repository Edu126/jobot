# Research plan — the market thesis (orchestration + pillars)

Date: 2026-08-27
Status: **Planned — not launched.** Runs on explicit go (credit-aware).

Purpose: give the product vision a *theoretical foundation*, not
intuition — especially the "are we giving the real fit, vs. what the ATS
rewards?" question. Feeds `product/vision.md` and future scoring ADRs.

## Pillars

1. **Psychology of job search** — cognitive load, job-search
   self-efficacy (Bandura), decision/rejection fatigue, emotional toll.
   Frame: Job Demands–Resources (JD-R). *This is our "why we exist" and
   our marketing.*
2. **Technical foundation of ATS** — how parsers work (Workday,
   Greenhouse, Lever, Taleo), knockout questions, parsing failure modes,
   keyword vs. semantic/embedding matching, the shift of ATS toward LLMs.
   *Defines what we optimize.*
3. **AI tailoring in the age of AI screening** — the arms race (both
   sides use LLMs), AI-content detection, authenticity, homogenization
   risk, the honesty constraint. *Defines our limits and differentiator.*
4. **(Founder-led) Existing founder-agent systems** — do similar
   multi-role founder/advisor agent setups already exist, and how have
   they integrated at each stage? **Eduardo drives this one** — the point
   is to learn the shape ourselves, not absorb another AI-construction
   bias. Agents assist with sourcing only, not conclusions.

## Orchestration design

The mechanism we agreed on (build when we launch):

1. **N pillar sub-agents in parallel** — one per pillar (1–3), each does
   its own research run and returns a structured brief.
   - Model: **Sonnet** (credit-aware — no Opus sprawl).
   - Scope each tightly: key theories/papers, what it means for jobot, 3
     testable implications. No open-ended wandering.
2. **1 consolidator sub-agent** — ingests the pillar briefs, cross-links
   them, surfaces tensions and the "real fit vs. ATS" answer, and
   presents a single synthesized memo.
3. **High-level review** — Eduardo + Claude review the memo *here*,
   founder-to-founder, and decide what becomes REQ/ADR.

Expected output: one memo (~1–2 pages) with a decisions section, not raw
dumps. Pillar 4 stays founder-led and merges in as Eduardo's own notes.

## Guardrails

- Credit-aware: Sonnet sub-agents, scoped prompts, no parallel research
  sprawl beyond the 3 pillars.
- Nothing here becomes a decision without the high-level review step.
