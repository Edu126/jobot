# PR 6 — BI Agent + `/admin/pulse`

_Full dev spec — self-contained. Read this first, then execute._

## Why

Four real users (Mehran, sister in Colombia, Sara in Spain, Melissa) are
actively using the 3 Fly apps (`jobbotv2`, `jobbotv2-hermana`,
`jobbotv2-melissa`). We now have signal-rich tables (events, jobs,
applications, viewed_jobs, dismissed_jobs, and — as of PR 5 — feedback)
but no way to answer "how are people actually using this, and where is
it breaking?" without SSHing into each machine.

PR 6 ships a weekly Gemini-authored markdown report per app, viewable at
`/admin/pulse` in the browser, so we can spot engagement trends,
funnel drop-off, quality issues, stuck states, and user-reported pain
points (from the feedback table) without manual SQL.

## Scope — in

1. **`admin_reports` table** (schema bump v11 → v12). Stores generated
   markdown reports. Fields: id, generated_at (UTC), period_start,
   period_end, model, markdown, tokens_in, tokens_out. Index on
   generated_at.
2. **`core/bi/pulse.py`** — reads the 6 signal tables for the past
   window (default: 7 days), builds a compact structured summary
   (counts, top items, funnels, error rates), sends to Gemini with a
   fixed question set, stores the returned markdown in `admin_reports`.
3. **`ui_web/routes/admin.py`** — `GET /admin/pulse` renders the most
   recent report as HTML (Jinja + markdown-it). List older reports
   with a date selector. Rate limit: 30/hour per identity.
4. **CLI entrypoint** — `python -m core.bi.pulse` so GH Actions can
   run it against each Fly app's SQLite volume via `fly ssh console`.
5. **GH Actions cron** — `.github/workflows/pulse.yml`, runs weekly
   (Sun 09:00 UTC), matrix over the 3 apps, calls the CLI on each.
6. **Feedback table integration** — the BI agent MUST include a
   dedicated section summarizing feedback themes for the window, with
   direct quotes (truncated) and identity attribution when available.
   User explicitly asked for this: _"let's use some of this information
   to be al swell analyze by the agent"._

## Scope — out

- Auth on `/admin/pulse` (deferred; whole app is per-user right now).
- Multi-tenant reports (each Fly app has its own DB, so per-app is
  automatic).
- Interactive dashboards / charts — markdown only.
- Alerting / thresholds — read-only reporting for now.

## Question set (send to Gemini verbatim in the prompt)

Group the answers under these 6 headings in the returned markdown:

1. **Engagement** — DAU/WAU proxy from events. Which pages/actions
   dominate? Any users going silent vs. week-over-week?
2. **Funnel** — jobs surfaced → viewed → saved → applied. Where's the
   biggest drop? Any obvious dead ends?
3. **Match quality** — top-N job scores over the window; how often are
   high-score jobs being dismissed (a bad signal)?
4. **Stuck states** — search_tasks stuck in `running`, applications
   stuck in a status for >7 days, resumes uploaded but never scored.
5. **Errors + kill-switches** — Gemini failures, adapter canary trips,
   rate-limit hits. If LLM_DISABLED fired, when and why?
6. **Feedback themes** — grouped by topic. Include 1-2 direct quotes
   per theme (truncate to 120 chars). Note identity (sid: prefix or IP)
   so we can follow up per-user if needed.

End with a **Δ from last week** section if a prior report exists in
`admin_reports` — call out what shifted.

## Files to create / touch

- `core/db.py` — schema v12, add `admin_reports` CREATE TABLE, bump
  version bump in `_run_migrations`. Add helpers `save_pulse_report(...)`,
  `latest_pulse_report()`, `list_pulse_reports(limit)`.
- `core/bi/__init__.py` — empty.
- `core/bi/pulse.py` — `collect_signals(days=7) -> dict`, `build_prompt(signals) -> str`, `generate_report(days=7) -> ReportRow`, `main()` for CLI.
- `ui_web/routes/admin.py` — new router; `GET /admin/pulse`, `GET /admin/pulse/{report_id}`.
- `ui_web/templates/pages/admin_pulse.html` — new page. Render markdown via `markdown-it-py` (add to `pyproject.toml`).
- `ui_web/main.py` — `app.include_router(admin.router)`.
- `.github/workflows/pulse.yml` — weekly matrix cron per app.
- `docs/pr6-bi-agent.md` — this file (delete once shipped).

## Gemini prompt structure

Reuse `core/llm/client.py`'s `generate_json(...)` — but the response
here is _markdown_, not JSON. Either:
- Add a `generate_text(...)` sibling that skips the `response_mime_type: application/json` config, OR
- Ask for JSON `{"markdown": "..."}` and unwrap. Prefer the second — less code, keeps the fallback chain identical.

Include `language_instruction(get_output_language())` at the top of the
prompt so ES-preferred users get ES reports. Field names in the JSON
wrapper stay English regardless.

## Testing

- Unit test `collect_signals` with a seeded in-memory SQLite — assert
  correct counts + shape.
- Manual: run `python -m core.bi.pulse --days 30 --dry-run` locally,
  eyeball the summary structure.
- Deploy dry-run: `fly ssh console -a jobbotv2 -C 'python -m core.bi.pulse --days 7'`.
- Visit `https://jobbotv2.fly.dev/admin/pulse` — confirm renders.

## Non-obvious constraints (READ ME)

- **Credits are tight** — do NOT spawn multiple sub-agents in parallel
  for research. If you fork, do it once, and stay on Sonnet.
- **The `_run_migrations` pattern** in `core/db.py` is idempotent
  DDL, not versioned diffs. Just add the new CREATE TABLE inside
  `SCHEMA_SQL` and bump the version constant. See v11 (feedback) as
  the recent example.
- **`i18n.language_instruction(lang)`** exists in `core/settings.py`
  — reuse it. Do not re-implement.
- **Rate-limit identity** — use `ui_web.ratelimit.get_identity(request)`
  in the admin route so the limiter respects the CGNAT session-cookie fix.
- **No auth yet** — the admin route is publicly reachable. Do not
  include PII in the rendered report beyond what the feedback table
  already has. When we add auth (post-PR-6), gate the route.

## Definition of done

- [ ] `admin_reports` table created via migration, verified on all 3 Fly volumes.
- [ ] `python -m core.bi.pulse --days 7` runs green locally.
- [ ] `/admin/pulse` renders latest report; older reports listable.
- [ ] Weekly GH Actions cron in place; can be dispatched manually via `workflow_dispatch`.
- [ ] Feedback section present in the generated markdown.
- [ ] Committed + pushed; deploy green across the 3 apps.

## Suggested order

1. Schema + DB helpers (`core/db.py`).
2. `collect_signals` + a fixture test.
3. Gemini prompt + `generate_report`.
4. Admin route + template.
5. GH Actions workflow.
6. Ship, then manually trigger the workflow to seed the first report on each app.
