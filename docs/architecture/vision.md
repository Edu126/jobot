# Architecture Vision

Last updated: 2026-08-21

The north star for jobot's technical architecture. Every ADR and design
decision must be checkable against these principles. If a proposal
conflicts with the vision, either the proposal changes or the vision
changes explicitly — never silently.

Scope note: this doc is about **jobot's architecture**. How we
collaborate as builders (peer-architect mode, sprint hygiene) lives in
Claude's memory, not here.

## What jobot is

A personal AI job-hunt agent for a **handful of trusted real users**.
One Fly.io app per person. Not multi-tenant. Not SaaS. Not a product for
a market — a product for named individuals.

## Non-negotiables

### 1. One user per deployment is a feature, not a limitation
Each user gets their own Fly app, their own SQLite volume, their own
data. This is not "we'll add multi-tenancy later." The single-user
architecture is what enables the things that make jobot different from
LinkedIn:
- Honest AI critique (no engagement-farm incentive to soften it).
- Behavioral analytics that mean something ("you're most active on
  Wednesdays") because they're about ONE person.
- Zero cross-tenant data leakage risk — there is no other tenant.
- Radical operational simplicity: no auth (yet), no user table, no
  session management, no row-level security.

Any proposal to introduce shared infrastructure (shared DB, shared
compute, cross-user features) must explicitly justify giving up what
single-tenant enables.

### 2. Honesty is the product
The single most differentiated thing jobot does is tell the user the
truth: brutal AI resume critique, "0% moved to next" funnel labels,
"you've viewed 47 jobs and applied to 0 — is something off?"
LinkedIn structurally cannot ship these because they undermine the
engagement flywheel.

Concrete implication: prompts default to a "colleague not coach"
voice. Sycophancy is a bug. "Solid mid-career resume, no red flags"
is better than a manufactured pep talk.

### 3. Quality lives in contracts, not in escape hatches
When output quality is fragile, the fix goes in the **contract layer**
— prompts, Pydantic schemas, server-side validators, silent retries,
grounding checks. Never in user-facing "Regenerate" / "Retry" /
toggle-more-options affordances.

Rationale: escape-hatch UI trains users to distrust the output, invites
quota-burning spam clicks, and lets real bugs hide behind "just try
again." A summary either passes the grounding check or doesn't render.
See `_grounded_or_none` in `ui_web/routes/profile.py` for the pattern.

### 4. Local-first flavor on hosted infra
Even though jobot runs on Fly, it inherits the ergonomics of a
local-first tool:
- SQLite is the database. One file per user. Backups are file copies.
- No third-party analytics. No trackers. No cross-user telemetry.
- Per-user data isolation is enforced by architecture (separate app,
  separate volume), not by app code.
- All user data can be exported by copying one file; all user data can
  be deleted by nuking one volume.

### 5. LatAm-first Spanish for ES users
Every ES-generating prompt (`language_instruction("es")`) anchors
Latin American register — "postulación" not "candidatura",
"acostumbras" not "sueles", no vosotros. Spain-Spanish output is a
regression. This is codified in `core/settings.py:language_instruction`
so all prompts inherit it automatically.

### 6. The BI loop is a first-class product surface
The weekly `/admin/pulse` report is not devops instrumentation — it's
how we learn what's actually happening in each deployment. Signal
tables (events, jobs, applications, viewed_jobs, dismissed_jobs,
feedback) are load-bearing. Any feature that skips instrumenting
itself makes the BI loop weaker.

## Deliberate non-goals

- **Multi-tenancy.** Each user gets their own app. Adding tenants adds
  auth, RLS, cross-tenant risk — all things single-tenant lets us skip.
- **Recruiter side.** Jobot is for the job seeker. It will never have a
  recruiter/employer surface (that's the LinkedIn business model
  jobot exists to sidestep).
- **User-facing knobs to fix quality problems.** See non-negotiable #3.
- **Growth-optimized engagement patterns.** No streaks-for-streaks-sake,
  no gamification, no dark patterns. See #2.

## Constraints that shape every decision

- **Budget: ~$0.** Free-tier Gemini, Fly's hobby plan, no paid services
  unless a real limit is being hit today. Not "we'll spend when we
  scale" — we're not scaling.
- **Users: 4 real people.** Every feature is validated against real
  behavior with named users, not personas. When the pulse report says
  "0 applications this week for Melissa," that's a real person we
  know.
- **Solo maintainer + AI pair.** Every new complexity is a maintenance
  cost the maintainer carries. See non-negotiable #3.

## When to revisit

Rewrite this doc (not silently amend) if any of:
- We add a fifth user in a way that shares infrastructure between them.
- We add a recruiter/employer surface.
- We start monetizing / go paid.
- We move off Fly + SQLite as the deployment substrate.
