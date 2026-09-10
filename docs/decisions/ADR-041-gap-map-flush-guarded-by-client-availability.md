# ADR-041: The gap-map Rebuild flush is guarded by LLM-client availability

Date: 2026-09-09
Status: Accepted
Relates to: ADR-040 (the flush, decision 4), REQ-036, ADR-008 (economy),
GOV-005 (honesty), the RAM-only exhaustion state in `core/llm/gemini.py`

## Context

Shipped the manual Rebuild flush (ADR-040): it deletes this résumé's cached gap
classifications, then re-renders, which reclassifies. Eduardo hit Rebuild on -edu
and the map was **destroyed** — every gap collapsed into the Domain pillar as
"in 1 role" singletons, Technical/Certifications empty.

Root cause: the reclassification needs a working Gemini client. When none is
usable (no API key, or the model is flagged quota-exhausted — a flag that lives
in RAM and does not self-clear, see the gemini.py note), `build_gap_map` leaves
every gap unclassified, and an unclassified gap defaults to its own singleton
cluster in the DEFAULT_PILLAR (domain). So the flush had wiped the good clustered
map and left raw, unclustered, mis-bucketed junk — worse than before, and not
self-healing until a later successful render.

## Decision

The flush route checks client availability **before** deleting. It resolves the
API key and constructs a `GeminiClient`; if there is no key or
`client.all_models_exhausted()` is true, it does **not** delete — it re-renders
the untouched map and fires `gap-rebuild-unavailable`, which the base.html
listener turns into an info toast ("can't rebuild right now… your map was left
unchanged"). Only with a usable client do we delete + reclassify.

## Alternatives considered

- Reclassify-into-a-shadow-set, swap only on full success (fully atomic): safest
  but more code (a parallel classify path ignoring cache). Deferred — the guard
  removes the destructive case (no key / exhausted), which is what actually bit.
- Never delete; overwrite in place: still needs an ignore-cache classify path;
  same cost as the shadow-set option.

## Consequences

- Rebuild can no longer destroy a good map when the AI is down.
- Residual (accepted) risk: if quota blows *mid-reclassify* after a passing
  guard, the already-deleted gaps that didn't get reclassified degrade to domain
  singletons until a later successful render. Much rarer than the no-client case;
  revisit with the shadow-set approach if it recurs.
- Operational: a stale RAM exhaustion flag makes the guard refuse even when paid
  quota is actually available — restart the app (or redeploy) to clear it.
