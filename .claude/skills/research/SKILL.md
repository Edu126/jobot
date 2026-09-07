---
name: research
description: "Run structured external research that plugs into the build — not a one-off dump. Use when the user says 'haz un research', 'investiga X', 'busca papers/evidencia sobre', 'dame el fundamento teórico', 'necesito la tesis de mercado/técnica', or wants to ground a product/architecture decision in outside evidence. Produces a fixed-format memo where every finding ends in a REQ/ADR/GOV action hook, with sources verified against real scholarly APIs. Pairs with the solution-architecture skill (research feeds REQ/ADR)."
---

# Research Practice

Turn a question into **verified, integrable evidence** — never a wall of
text. The output is a memo in a fixed format where **every finding is
tied to an action hook** (REQ / ADR / GOV / product-vision / backlog), so
nothing stays as loose knowledge.

Philosophy: **AI is copilot, not pilot.** Agents source and structure;
the human decides what becomes a decision. Adapted lean from the
`academic-research-skills` suite — we kept its two best ideas (real-source
verification + claim→evidence→confidence rigor) and dropped the 39-agent
manuscript machinery as overkill for a product team.

**Credit-aware (hard rule for jobot):** Sonnet sub-agents, tightly scoped
prompts, no parallel research sprawl beyond the declared pillars. A run
that balloons is a bug.

---

## The pipeline (5 steps)

**1. Frame** — write `docs/research/RESEARCH-PLAN-<slug>.md` first
(template in `templates/`). Declares: the question, 1–4 pillars, guardrails,
and which artifact it will feed. **No plan, no run.**

**2. Search** — one Sonnet sub-agent per pillar, in parallel. Each returns
a brief in the fixed Findings shape: `Claim → Source → Locator (quote) →
Confidence (high/med/low)`. Scope each prompt tightly: key theories/papers,
what it means for jobot, 3 testable implications. No open-ended wandering.
Search **primarily in English** (where most literature and options live);
include other-language sources only where they add distinct regional value.

**3. Verify** — before anything ships, confirm each cited source *exists*.
Free, no-key, deterministic (via Bash), cheap:
- OpenAlex by title:
  `curl -s 'https://api.openalex.org/works?search=<title>&per_page=1' | jq '.results[0].id,.results[0].doi'`
- Crossref by DOI:
  `curl -s 'https://api.crossref.org/works/<doi>' | jq '.message.title'`
Mark each source `✓ verified` or `⚠ unverified`. **Unverified claims are
flagged in the memo, never presented as established.** This is the antidote
to hallucinated papers.

**4. Consolidate** — one sub-agent fuses the pillar briefs into a single
`docs/research/RESEARCH-<slug>.md` (template in `templates/`): TL;DR,
findings per pillar, tensions, an **Implications table** (the bridge to the
product), and decisions to make with the user.

**5. Deliver + integrate** — review the memo *with the user*, high level.
Each row that survives becomes a REQ/ADR/GOV via the solution-architecture
skill. Research that produces no action hook produced nothing.

---

## Modes (pick per run, keep it light)

- **`quick`** — 1 pillar, 1 agent, ~5 sources, skip consolidation. For a
  focused "is X true / what does the literature say" check.
- **`deep`** — 2–4 pillars, parallel agents + consolidator. For a thesis
  (e.g. the market thesis: job-search psychology + ATS foundations + AI
  tailoring in the age of AI screening).

Default to `quick` unless the question genuinely spans pillars. Bigger is
not better — it's more credits.

---

## Guardrails

- Nothing becomes a decision without the step-5 human review.
- Founder-led pillars (where the user wants to learn the shape themselves)
  stay founder-led: agents assist with *sourcing only*, not conclusions.
- Every source verified or explicitly flagged. No exceptions.
- Respect the credit budget over completeness.

First instance on file: `docs/research/RESEARCH-PLAN-market-thesis.md`.
