# REQ-024: Admin control plane — app management (keys, limits, users)

Date: 2026-09-05
Source: Eduardo
Status: Open (backlog stub — NOT a final decision; a bucket to feed)

## What they asked for
> "ya no somos un btok, ahora tenemos keys centralizadas… eso hace parte de
> nuestro future admin panel. keys, limits, users, etc." — "déjalo en un REQ,
> para que vayamos alimentando el admin panel; esto no es decisión final, pero
> sí deberíamos incluir todo lo relacionado con el management de la app."

Trigger: replicating the Tavily API key across the 4 Fly apps exposed that we
have no central place for shared vendor keys, quotas, or per-user attribution —
each app carries its own `fly secret`, duplicated, with no view of who consumes
what.

## What they actually need
A **control plane** over the fleet, separate from the candidate-facing product.
Today's single-tenant, file-per-user POC (one Fly app + one SQLite per real
user) has no operator surface. As shared, metered dependencies land (Tavily now,
Gemini quota already, more later) we need one place to manage the *running of
the app*, not the résumé work inside it. Candidate seeds to fold in as they come:

- **Keys** — central store for shared vendor credentials (Tavily, Gemini, …),
  one source of truth, propagated to deploys instead of N duplicated secrets.
- **Limits** — quota is a *shared* pool per vendor account (e.g. Tavily free =
  1,000 searches/month across ALL apps, not per app). Need visibility + caps
  before a pool is silently exhausted.
- **Users** — the 4 real users live as separate Fly apps + SQLite files today
  ([[reference_fly_app_user_mapping]]); no roster, provisioning, or per-user
  usage/attribution.
- Open bucket for the rest of app management (billing, provisioning, health,
  audit) as it surfaces — this REQ is the intake, not the spec.

## How we'll know it worked
An operator can answer "which key is app X using, and how much of the shared
Tavily quota is left this month?" from one place — instead of SSH-ing per app
and guessing.

## Related
- Depends on the fleet/deploy model — GH Actions matrix fan-out, per-app Fly
  secrets, shared vendor accounts.
- ADR-029 (Tavily) surfaced the shared-quota constraint that motivates this.
- Ties to the product-vision admin/monetization direction ([[project_product_vision]]).
- ADR-XXX (once we pick a control-plane shape — deferred).
