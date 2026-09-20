# REQ-038: Cut LLM cost on paid tier — validate 2.5-flash-lite as primary

Date: 2026-09-09
Source: Eduardo (product architect), after the paid-tier cost review
Status: Logged — NOT scheduled. Captured so the reasoning trail exists; the
switch itself is gated on the quality eval below.

## What they asked for

"Documenta el REQ+ADR para testear el primario a 2.5-flash-lite." Now that we
left the free tier and are on the paid plan, decide the primary model on cost,
not on free-tier daily quota — but prove the cheaper model doesn't degrade
quality before flipping it.

## What they actually need

Real usage pulled from Mehran's app (jobbotv2-hermana, 2026-08-18→09-10) shows
**all** load lands on `gemini-3.5-flash-lite`; the fallback chain never fired.
On the paid tier that model's **output** is $2.50/1M — the same as full 2.5
Flash, and 6× `gemini-2.5-flash-lite` ($0.40/1M). Output is ~22% of tokens but
~70% of cost, so the model's output price is the dominant lever. Projected: the
switch takes Mehran from ~$2.15/mo to ~$0.46/mo (−79%), fleet ~$3–8/mo → ~$1–2.
The "lite" in `3.5-flash-lite` is latency/size, not price. See
[[project_llm_cost_baseline]].

The need is not "spend less" for its own sake — it's to make the cheapest model
the default **without the user noticing a quality drop** in the monetized
surfaces (scoring, gaps, gap map, tailor).

## Scope guardrails (when scheduled)

- **In:** an offline eval that measures each candidate model against
  ground truth on real fixtures — score correctness, gap honesty (gap = real
  JD requirement, right language), tailor fidelity. Fixtures = Mehran's real
  high/low-fit jobs + real résumés ([[project_real_users]], anonymised), incl.
  the REQ-037 off-lane cases. Because scoring is stochastic, run each item **N×**
  and report drift, not a single sample.
- **Out:** an A/B "which output looks nicer" diff between two models — that is
  exactly the trap [[feedback_hitl_validation_needs_source]] warns against.
  The sheet must show the JD/résumé source and **per-finding checkboxes**
  (is THIS gap a real requirement? is THIS score justified?), scoring the
  actual claim, not model-vs-model preference.
- **Out:** any per-model prompt forking. If `2.5-flash-lite` needs a different
  prompt to pass, that is a signal to keep `3.5-flash-lite`, not to branch the
  prompt (contract-layer discipline, [[feedback_simplicity_over_escape_hatches]]).

## How we'll know it worked

`gemini-2.5-flash-lite` passes the quality gate on real fixtures (no material
drop in score correctness / gap honesty / tailor fidelity vs `3.5-flash-lite`)
→ it becomes the primary and the projected ~4.7× cost cut shows up in the next
`gemini_usage` pull. If it fails the gate, we stay on `3.5-flash-lite` and the
REQ closes as "tested, rejected" — the trail still has value.

## Related

ADR-043 (the decision + eval criterion), ADR-004 (original Gemini choice — this
amends its model-selection rationale from free-tier quota to paid cost),
ADR-008 (no new call sites, no prompt forking), ADR-018 (coverage-anchored
scoring — the calibration under test), GOV-005 (gap honesty), REQ-037 (off-lane
overscoring — same fixtures). Pulse can surface $ directly from `gemini_usage`
× a per-model price dict (separate small task).
