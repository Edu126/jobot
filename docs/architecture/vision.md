# Architecture Vision

Last updated: 2026-08-21

The north star for jobot's technical architecture. Every ADR and design
decision must be checkable against this. If a proposal conflicts with the
vision, either the proposal changes or the vision changes explicitly —
never silently.

Scope note: this doc is about **jobot's architecture**. How we
collaborate as builders (peer-architect mode, sprint hygiene) lives in
Claude's memory, not here.

## What jobot is

A personal AI job-hunt agent. Currently: one Fly.io app per user, for a
handful of trusted real users (friends testing the POC). Post-POC:
multi-user with row-level security and real auth. See the "Current
posture" and "Post-POC direction" sections below for the mode shift.

## Non-negotiables (evergreen — survive POC exit)

### 1. Honesty is the product
The single most differentiated thing jobot does is tell the user the
truth: brutal AI resume critique, "0% moved to next" funnel labels,
"you've viewed 47 jobs and applied to 0 — is something off?" LinkedIn
structurally cannot ship these because they undermine the engagement
flywheel; jobot can precisely because it serves the user, not
advertisers or recruiters.

Concrete: prompts default to "colleague not coach" voice. Sycophancy
is a bug. "Solid mid-career resume, no red flags" beats a manufactured
pep talk.

### 2. Quality lives in contracts, not in escape hatches
When output quality is fragile, the fix goes in the **contract layer**
— prompts, Pydantic schemas, server-side validators, silent retries,
grounding checks. Never in user-facing "Regenerate" / "Retry" /
extra-toggle affordances. Escape-hatch UI trains users to distrust
output, invites quota-burning spam, and lets real bugs hide behind
"just try again." A summary either passes the grounding check or
doesn't render. See ADR-005 and `_grounded_or_none` in
`ui_web/routes/profile.py` for the pattern.

### 3. Per-user data isolation is a first-class guarantee
Whether that's implemented as file-per-user SQLite (current POC) or
row-level security in a shared DB (post-POC target), one user's data
must never touch another's. The isolation guarantee survives across
storage choices; the mechanism does not.

### 4. LatAm-first Spanish for ES users
Every ES-generating prompt (`language_instruction("es")`) anchors
Latin American register — "postulación" not "candidatura",
"acostumbras" not "sueles", no vosotros. Spain-Spanish output is a
regression. Codified in `core/settings.py:language_instruction` so
every prompt inherits it automatically.

### 5. The BI loop is a first-class product surface
The weekly `/admin/pulse` report is not devops instrumentation — it's
how we learn what's actually happening in each deployment. Signal
tables (events, jobs, applications, viewed_jobs, dismissed_jobs,
feedback) are load-bearing. Any feature that skips instrumenting
itself makes the BI loop weaker.

## Current posture: Proof of Concept

We are explicitly in POC mode. The following are **tactical
decisions**, not permanent architectural bets. They are chosen to ship
fast with a solo maintainer + AI pair, on a ~$0 budget, to four real
beta users. All are subject to revisit at POC exit:

- **One Fly app per user** (ADR-001). Chosen because getting each
  friend their own URL was faster than building multi-tenant auth.
  Multi-user with RLS is the planned successor.
- **SQLite over managed DB** (ADR-002). Chosen because it worked and
  needed zero setup. Not weighed against Supabase / Postgres —
  reconsideration open (Supabase would bring free auth as a
  side-effect).
- **HTMX + Alpine + CDN Tailwind, no build step** (ADR-003). Chosen
  for zero-build complexity + AI-pair ergonomics. Open to
  reconsideration if the ceiling is hit or if a better-documented
  stack proves worth the cost.
- **Gemini free tier with a 3-model fallback chain** (ADR-004).
  Chosen for $0 cost during POC. Multi-provider architecture is
  planned post-validation.

## Post-POC direction (known at 2026-08-21)

Explicit forward calls the user has already made:

- **Multi-user with row-level security.** Migration planned ~2 weeks
  post-feedback collection.
- **Real auth.** Likely magic-link + Google. Supabase is a candidate
  precisely because it bundles this.
- **Multi-provider LLM.** Post-validation, without affecting quality
  or price. The `GeminiClient` abstraction already gives us a
  swap-in point.
- **Possible frontend framework upgrade** if the current HTMX ceiling
  is hit as user count / UI complexity grows.

Each of these will get its own ADR when the decision is actually made
— not before.

## Deliberate non-goals (evergreen)

- **No recruiter / employer surface.** Jobot serves the job seeker.
  That is the LinkedIn business model jobot exists to sidestep.
- **No third-party analytics or telemetry.** Local pulse report only.
- **No sycophantic AI voice.** See non-negotiable #1.
- **No user-facing "Regenerate" or retry buttons.** See non-negotiable
  #2.

## When to formally revisit this vision

Rewrite this doc (not silently amend) when any of the tactical POC
decisions is superseded — starting with the planned multi-user
migration. That's not "silent evolution": that's a vision update with
new ADRs superseding the current ones.
