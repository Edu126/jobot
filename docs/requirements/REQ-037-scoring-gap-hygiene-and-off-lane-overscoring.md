# REQ-037: Scoring hygiene — gaps must be requirements, and off-lane roles must not over-score

Date: 2026-09-09
Source: Eduardo (product architect), surfaced by the REQ-036 -hermana investigation
Status: Logged — NOT scheduled. Captured so the reasoning trail exists; needs
Eduardo to prioritise (it is a `semantic_score` change, not a gap-map change).

## What the investigation found

Reproducing Mehran's gap map against his real data (2026-09-09) showed two
defects that originate in the **scoring layer** (`core/matching/semantic_score.py`),
upstream of the gap map — so REQ-036's recency/fit filter cannot fix them:

1. **Advice leaks into `gaps_json` as if it were a requirement.** The gap
   "localiza tu cv al francés para este mercado" ("localize your CV to French for
   this market") appeared as a gap across 4 of his jobs. That is coaching output,
   not a JD requirement — the scoring prompt is letting suggestions contaminate
   the gap list. It even leaks the wrong language (Spanish text on `lang=en` rows).
2. **Off-lane roles score high.** Gaps like "Sage software proficiency" (job fit
   90), "commercial furniture installation industry experience" (75-82), and
   "AECOM internal enterprise framework" (95) come from jobs the scorer rated
   strong-fit for a PMO/admin candidate. Because the fit score is inflated, the
   REQ-036 `score > 70` filter keeps these off-lane gaps — the problem is the
   score, not the gap.

## What they actually need

The gap map is the monetized artifact; it can only be as honest as the scores and
gaps feeding it. A gap must be a real, JD-sourced requirement (never advice), and
a fit score must reflect true lane fit so the >70 filter means what it says.
Otherwise the user sees off-lane gaps among "good" roles and quietly stops
trusting the map.

## Scope guardrails (when scheduled)

- **In:** tighten the scoring prompt / Pydantic so `gaps` are requirement phrases
  only (no advice, no cross-language leakage — [[feedback_simplicity_over_escape_hatches]]:
  fix in the contract layer); investigate the off-lane over-scoring (calibration
  of the coverage-anchored 0-100, ADR-018) with Mehran's real high-scored off-lane
  jobs as the fixture.
- **Out:** anything in the gap map itself (REQ-036 already done); user-facing
  "report this gap" buttons (fix quality upstream, not with escape hatches).

## How we'll know it worked

No advice strings in `gaps_json`; off-lane roles (furniture install, Sage-centric
IT) score below the strong-fit bar for a PMO/admin résumé, so their gaps no longer
reach the map.

## Related

REQ-036 (the gap-map rework that surfaced this), ADR-018 (coverage-anchored
scoring — the calibration to revisit), ADR-008 (no new call sites), GOV-005
(honesty), product vision (gap monetized 3×). Investigate on -hermana (Mehran)
per [[reference_fly_app_user_mapping]].
