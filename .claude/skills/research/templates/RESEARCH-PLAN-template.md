# RESEARCH-PLAN-<slug> — <the question>

Date: <YYYY-MM-DD>
Status: **Planned — not launched.** Runs on explicit go (credit-aware).
Mode: quick | deep
Feeds: <product/vision.md | REQ-XXX | ADR-XXX | backlog>

## The question
<One sharp sentence. What decision does this unblock?>

## Pillars (1–4)
1. **<pillar>** — <scope: key theories/papers, what it means for jobot>
2. …
   - Mark any **founder-led** pillar: the user drives conclusions; agents
     source only.

## Guardrails
- Model: Sonnet sub-agents.
- Scope: <bound each pillar — no open-ended wandering>.
- Sources: every citation verified (OpenAlex/Crossref) or flagged.
- Credit budget: <expected # of agents / rough cap>.

## Expected output
One `RESEARCH-<slug>.md` memo (~1–2 pages) with an Implications table and
a decisions section. Reviewed high-level with the user before anything
becomes a REQ/ADR.
