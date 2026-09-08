# ADR-034: Phase 0 KPIs are computed deterministically and rendered live on /admin/pulse

Date: 2026-09-07
Status: Accepted
Relates to: REQ-026, non-negotiable #1 (honesty), non-negotiable #5 (BI loop)

## Context
REQ-026 needs the 2 Gold + 3 support KPIs visible so we can read retention and
earn the right to bet. `/admin/pulse` already exists, but it is a **Gemini-authored
markdown narrative** (`core/bi/pulse.py`). The numbers that decide the company
must not be summarized by an LLM — drift or a hallucinated figure there is not a
cosmetic bug, it is a lie about whether we have a business. The raw signals
already exist (events, applications, job_scores); only the computation + surfacing
are missing.

## Decision
Add `core/bi/kpis.py::compute_phase0_kpis` — **pure, deterministic**, reading the
existing tables. Render it as a **fixed KPI block computed live at view time** at
the top of `/admin/pulse`, above the LLM narrative (which stays for color).
Outcome loop v1 **derives "heard back" from application status transitions**
(interviewing/offer/rejected are durable ground truth) — no new capture needed to
get a first number; an explicit user-facing "did you hear back?" nudge is a later
slice. No new Gemini call site (llm-surface unchanged).

## Alternatives considered
- Let the pulse LLM report the KPIs: rejected — drift on the load-bearing numbers.
- Freeze KPIs into the weekly snapshot: rejected — view-time compute is always fresh.
- Build an explicit outcome nudge now: deferred — status transitions already give a
  first signal; the nudge needs UX design and shouldn't block the metric.

## Consequences
KPIs are trustworthy and always current; the LLM narrative becomes commentary, not
source of truth. S2 (acceptance) and the outcome number are **proxies** (download =
"used"; status-move = "heard back") — honest but coarse; refine when the explicit
nudge and edit-tracking land. Single-tenant means "returning users" is per-app
weekly-active; fleet-level retention is still eyeballed across the 10 apps.
