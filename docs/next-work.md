# Next Sprint — Scoring rework (Sprint 7)

**Status:** implemented 2026-08-26, pushed to `claude/sprint-7-scoring-rework-cekmx3`,
awaiting PR review. Sprint hygiene done: `/simplify` (4 parallel review
agents — reuse/simplification/efficiency/altitude, converged on the same
handful of issues) + `/code-review` (found and fixed 4 real bugs: a
QuotaExhaustedError-during-retry path that discarded good scores, a
stale-cache backfill gap for pre-migration `resume_ai_summary` rows, a
mid-word evidence truncation that could fail its own grounding check,
and an off-by-one in the AI-summary prompt's item count). All 6 test
files pass. Three commits: implementation, simplify pass, code-review
fixes.
**Date:** 2026-08-26 (current entry). Prior sprint kept below for history.
**Related:** [REQ-004](requirements/REQ-004-section-based-scoring.md),
[REQ-005](requirements/REQ-005-remove-aec-scoring-bias.md),
[REQ-006](requirements/REQ-006-aec-cleanup-search-matching-seeds.md),
[ADR-006](decisions/ADR-006-section-based-scoring-llm-evidence-backend-math.md),
[ADR-007](decisions/ADR-007-domain-neutral-persona-from-resume-context.md),
[ADR-013](decisions/ADR-013-persona-source-shared-resume-profile.md).

## PENDING — REQ-016 sprint hygiene (deferred by Eduardo 2026-08-31)
`/simplify` + `/code-review low` on the REQ-016 commits (`e630742` B-layer,
`d01a305` validation harness + disclaimer + A-layer rollback) NOT run yet —
Eduardo wants it folded into a larger project-wide review later. Also pending:
his marks on `data/ab_scoring_2026-08-31.md` (the cross-language prompt go/no-go).

## 2026-08-31 — Cache/memory architecture map + Mehran resume-gen feedback (MAP ONLY, do not fix yet)

Opened by Eduardo. Suspicion: "part of the cache stays in RAM, not DB."
**Confirmed — yes.** Audit of where state lives:

**In-RAM (module-level, lost on process death):**
- `core/llm/gemini.py` — `_exhausted_models` (model→quota-exhaustion date) and
  `_request_counts` ((model,date)→count). Comment acknowledges "cleared on
  restart."
- `core/settings.py` — `_cache` dict. **Write-through to DB**, repopulates on
  miss → lower risk.
- `core/jobs/ats/oracle_hcm.py` — `_SITE_COMPANY_CACHE` scrape optimisation.
  Minor.

**Durable (DB/file — already migrated, safe):** task state (`core/jobs/tasks.py`,
PR-2 migration off the old in-memory `ui_web.state.search_tasks`), job-search
cache (`data/jobs_cache/*.json`), scores / suggestions / ai_summary (SQLite).

**Risk of keeping the RAM state, esp. on Fly `auto_stop_machines='stop'`:**
The machine cycles often → `_exhausted_models` + `_request_counts` reset every
cycle. Effects: (a) re-probe exhausted models → wasted 429s; (b) the fallback
chain can pick a *different model* across runs → **inconsistent model →
inconsistent scores/quality**; (c) request-count shown to the user is wrong
after any restart; (d) if ever scaled >1 machine, per-process RAM state never
shares → divergence.

**Mehran feedback (search-by-link, LinkedIn job 4454079380, aggressive resume gen):**
1. *3 aggressive attempts → totally different scores each.* Mapped root causes:
   (a) scoring `temperature = 0.4` in `core/llm/gemini.py` → inherent run-to-run
   LLM non-determinism; (b) probable model-fallback divergence from the RAM-reset
   exhaustion state landing different runs on different models. This is exactly
   what [REQ-015](requirements/REQ-015-deterministic-scoring-redesign.md) /
   [REQ-016](requirements/REQ-016-scoring-v2-rank-aware-honest-fit.md) target.
2. *First aggressive run truncated the resume's experience.* Separate from cache
   — a generation/writer truncation bug (candidates: `MAX_RESUME_CHARS`,
   `core/resume/ai_regenerate.py`, `core/resume/writer.py`). Same class as the
   "mid-word evidence truncation" already fixed once in Sprint 7 hygiene.

**Improvement options:**
- ~~Persist gemini exhaustion + request counts to DB (mirror the PR-2
  task-state migration); small table keyed `(model, date)`.~~ **DONE
  2026-09-01** — schema v18 `gemini_model_state(model, day, exhausted, count)`;
  `core/llm/gemini.py` reads/writes it (helpers swallow DB errors → old
  "assume available" fallback so CLI/tests never break). Kills Mehran's
  cause (b): the fallback chain now stays on the SAME model across Fly
  restarts instead of re-probing and diverging. Test:
  `tests/test_gemini_model_state.py` (round-trip + durability).
- ~~Scoring `temperature → 0` for determinism (REQ-015/016).~~ **DONE
  2026-08-31** — per-call override on `generate_json` (scoring passes 0.0,
  generation keeps 0.4). Kills cause (a).
- ~~Score cache keyed on **resume-text hash** (not `resume_id`).~~ **DONE
  2026-08-31** — schema v17: `job_scores` PK re-keyed on the resume text hash
  (`resumes.text_hash`), resolved from `resume_id` inside `db.py` so no call
  site changed. A regenerated-but-equivalent resume now reuses its scores.
- ~~Investigate the regen truncation separately (writer / ai_regenerate).~~
  **FIXED 2026-09-01 — reproduced LIVE on Mehran's Fly app (`jobbotv2-hermana`,
  resume id 9 × job `li-4454079380`, aggressive level) and evidence-driven.**
  What it is NOT (ruled out by repro): a token cutoff. At the 8192 default the
  truncated run returned *complete, valid JSON with the full cover letter* —
  just 5 of 22 experience items. `generate_json` never raised MAX_TOKENS, so
  the model was **choosing** to emit ~5 items (interprets aggressive "collapse
  bullets" as "keep the top few"). ~20% of runs, non-deterministic (temp 0.4),
  same model each time (so not fallback divergence either). Two guessed fixes
  were tried and **both empirically refuted** on the machine, then reverted:
  (a) `max_output_tokens=16384` — irrelevant, it's not a token cutoff; (b) an
  `_OUTPUT_SCHEMA` "never drop an entry" rule — A/B on real data showed no
  effect (1/5 collapse with AND without it). **Actual fix:** a structural-
  fidelity guard in `core/llm/rewrite.py` (ADR-005 contract-layer pattern) —
  `_collapsed_sections` flags experience/education dropping below 60% of the
  original item count, `rewrite_resume` then retries once (per-call random →
  ~20%²≈4% residual) and restores any still-collapsed section verbatim from
  the original. No role/employer/degree can ever be silently lost. Live
  validation (6 guarded trials on Mehran's data): both catastrophic collapses
  (5/22) recovered to 22/22; legitimate aggressive trims (18–21/22) correctly
  pass through untouched. Test: `tests/test_rewrite_fidelity.py` (deterministic,
  fake client). **Note:** count-based threshold is a proxy — refining to true
  role-header counting was skipped (header detection is fragile; the 0.6 gap
  between collapse ~0.23 and legit trim ~0.82+ is clean).

Landed alongside the above (REQ-016 B-layer pass, 2026-08-31): the 5→3→1
`semantic_score.py` prompt reframe — coverage-anchored scoring + cross-language
rule + wrong-language gap (ADR-017/018), `PROMPT_VERSION` bumped.

REQ-016 A-layer (2026-08-31): `lite_score.rank()` wired at the score-batch
boundary then **ROLLED BACK** ([ADR-020](decisions/ADR-020-defer-lite-score-a-layer.md))
— the chain scores every job anyway, so it only reordered (no call saving) at
higher CPU and gave no cross-language gain. `affinity` retained; `lite_score`
unwired until a real top-N cap is chosen. A/B + determinism harnesses added
(`scripts/scoring_bakeoff.py --ab` / `--determinism`), now **batch-of-5** =
production path. **ACTION for Eduardo:** mark `data/ab_scoring_<date>.md` — the
ground-truth go/no-go on the NEW prompt. Batch findings: composition shifts
scores (Mehran 88 solo→75 in-batch), NEW less drifty than OLD, cross-language
wins clear (Andrea EN 45→62, wrong-language gap firing).

Determinism finding (2026-08-31, [ADR-019](decisions/ADR-019-gemini-scoring-nondeterministic-stability-via-cache.md)):
`--determinism` demo proved **temp=0 does NOT make Gemini deterministic** —
same model, same prompt, drift ±3–10 + band-edge bucket flips. Not fallback
divergence (model verified constant). Decision: user-facing stability = the
text-hash cache freezing the first score (not temperature); keep temp=0; ship an
honest tailor-tab disclaimer (`tailor.score_disclaimer`, EN/ES). Escalation if a
real user complains = median-of-3 on first write (deferred). ~~**Still open:**
persist gemini exhaustion/counts to DB (fallback divergence across restarts —
separate from this same-model finding); regen truncation bug.~~ **Both closed
2026-09-01 — see the two DONE/ADDRESSED bullets above.**

## What's the sprint
Section-based scoring (LLM produces per-section evidence, backend
does the math) + domain-neutral persona derived from resume context
(remove baked-in AEC assumptions in search seeds, matching, and
prompts). Requirements and ADRs already written; implementation is
what's left.

## 2026-08-26 kickoff — implementation decisions

Reading the code before touching it surfaced a gap: ADR-007 assumes
`role_label`/domain/seniority are already available resume signals;
in practice only `role_label` exists, and it's generated lazily by
`ui_web/routes/profile.py` on Profile visits — not guaranteed present
at scoring time, and not reachable from `core/` without an inverted
dependency. Raised as a 3-way architecture question; decided:

1. **Persona pipeline** — captured as [ADR-013](decisions/ADR-013-persona-source-shared-resume-profile.md).
   Shared resume-profile generation moves to `core/resume/ai_summary.py`,
   extended to also produce `domain` + `seniority`, callable from
   `score_jobs` with a generic fallback on failure.
2. **REQ-006 saved searches** — replace the 3 hardcoded AEC presets in
   `core/jobs/saved_searches.py` with domain-neutral content (keep the
   pre-baked/editable structure, just de-bias what's in it), and clean
   the AEC/"boyfriend" framing from comments.
3. **REQ-005 regression fixtures** — no real resume text or fixtures
   directory exists in this repo/environment (`data/` is gitignored).
   Building realistic *synthetic* fixtures for the AEC / non-AEC /
   career-switcher cases instead of real user resumes — committing
   real resume text to git is a separate data-governance call from the
   ephemeral per-request send to Gemini that GOV-001 covers. Fixtures
   are clearly labeled synthetic; swappable for real text later if
   provided.

## 2026-08-26 close-out — deferred / skipped items

- **Real resume fixtures.** Synthetic fixtures ship now (see decision 3
  above); swap in real (anonymized) resume text if/when provided —
  doesn't block the PR.
- **Full module split for the grounding guard-rail.** `/simplify`'s
  altitude review wanted `_grounding_ok`/`_term_grounded`/
  `_score_batch_grounded` pulled out of `semantic_score.py` into their
  own module. The actual duplication problem it was pointing at (three
  near-identical normalize/stem implementations) is fixed by extracting
  `core/matching/lexical.py`; a further file-size-only split was skipped
  as risking a `core/matching` import cycle for a stylistic win.
- **ADR-013's length.** `/code-review` flagged it (and the pre-existing
  ADR-012) as over CLAUDE.md's "under 150 words" ADR guideline. Left as
  written — every ADR since ADR-004 already runs well past that budget,
  and the Alternatives/Consequences sections are the parts the
  solution-architecture skill calls load-bearing.
- **Automated regression test for the `ai_summary` stale-cache fix.**
  `core/resume/ai_summary.py` doesn't accept a DB path override, so
  `get_or_generate` can't be exercised against an isolated test DB the
  way the rest of the suite tests `core/db.py` functions directly — the
  fix is covered by code inspection + the existing grounding test suite,
  not a dedicated test. Worth a path-injection param if this file grows
  more test surface.
- **`ui_web/templates/partials/job_card.html` keyboard-handling bug and
  ADR-012's word count**, both flagged by `/code-review` — both belong
  to REQ-012 (Sprint 8's fixed-viewport workspace), already merged to
  `main` before this branch forked. Out of this sprint's scope; not
  touched.

## 2026-08-25 hotfix detour (not Sprint 7)
Mehran feedback shipped as 6 commits in an unplanned session:
1. `08e9619` — cache key gains `lang` (schema v13 + migration).
2. `216c0c1` — feedback modal Send button (iOS Safari race).
3. `d4750aa` — translate Matched / Gaps / Gaps flagged headers.
4. `3f672f7` — north-star docs: `llm-surface.md` + `ADR-008`.
5. `a2c0423` — /simplify pass (3 cleanups).
6. `71fce5a` — reset feedback textarea on close (from /code-review).

Sprint hygiene done: /simplify pass ran, /code-review medium partial
(6/8 finders cut by session rate-limit — inline review closed the
gap; only surviving actionable finding was the textarea reset).

Known drift documented but NOT fixed in this detour (real work, own
session): `resume_suggestions` and `resume_ai_summary` caches carry
the same missing-`lang` bug class we fixed for `job_scores`.
Flagged in [llm-surface.md](architecture/llm-surface.md) under
"Known drift risks."

## 2026-08-25 PM — Mehran feedback dump (post-hotfix) — SHIPPED

**Status: shipped 2026-08-25.** Deployed to all 4 Fly apps (Melissa
`jobbotv2`, Mehran `-hermana`, Andrea `-andrea`, Sara `-melissa`).
Andrea validated end-to-end in her live session; Melissa hit + we
fixed one regression during rollout (see hotfixes below); Mehran /
Sara validation still pending on their own time.

**Sprint hygiene:** user explicitly skipped `/simplify` +
`/code-review` for this detour to move to a separate concern. If
we come back to it, run `/code-review low` (or `ultra`) — memory
`feedback_sprint_hygiene` says never `medium`.

**Andrea's open validation task:** confirm whether the 54→98 score
jump reproduces from "regenerate cleanly" alone (would be an
invalidation bug not covered by REQ-009) vs. from re-uploading the
PDF (expected — new `resume_id` = cache miss).

**Shipped scope:**
- REQ-007 destructive-action modals (`a0a7659`).
- REQ-008 jobs_results filter reactivity + card meta lookup (`a0a7659`).
- REQ-009 cache-key lang parity + schema v14 migration (`a0a7659`).
- REQ-010 + ADR-009 language-onboarding architectural doc (`a0a7659`).
- Bucket D — jobs UX polish (hide fr toggle on ES, hide dismissed on
  empty dataset, broaden `onlyNew` semantic, i18n load stages,
  personalised role placeholder, city placeholder incl. country) (`a0a7659`).
- Bucket F — full tailor-flow i18n sweep, 44 EN/ES keys (`a0a7659`).

**In-session hotfixes (rollout regressions):**
- `990132f` — tojson in x-data attribute broke jobs.html and
  tailor_panel.html (Melissa's browser leaked raw x-data as text).
  Fixed via `<script>` window globals; memory
  `feedback_tojson_in_html_attribute` updated with both patterns.
- `4b4e1ec` — `hideFrench: true` store default was invisibly active
  on UI=es after Bucket D hid the toggle. Coupled the value to UI
  language in `init()`.
- `3dcbc0b` → `3ebf9c4` → `7696df1` → `6b5dece` — four iterations
  on the split-viewport detail pane. Started with `sticky top-20 +
  self-start`, tried `items-start`-belt, cut to `position: fixed`
  (visually ugly overlap), landed on user proposal: aside is
  `position: absolute` inside a `relative` grid, JS sets `top` from
  clicked card's Y — card and pane share document flow, scroll
  together. Ships as `6b5dece`.

**Deferred / left as follow-up work:**
- Andrea's validation of the score-jump mechanic.
- Mehran / Sara feedback on all shipped fixes.
- `/simplify` + `/code-review low|ultra` sweep of the detour.
- REQ-010 implementation (docs only in this detour; the actual
  language-onboarding banner extension is its own sprint).

---

### Original PM dump (kept for retro)

**Filed as REQs (this session):**
- [REQ-007](requirements/REQ-007-restore-destructive-action-modals.md)
  — bucket C. Destructive-action buttons on Profile lost their
  confirm modal (likely regression from `79d3e6a` tiered
  data-destruction PR). ~30 min. **Highest severity — data loss
  risk.**
- [REQ-008](requirements/REQ-008-jobs-results-filter-reactivity.md)
  — bucket E. `min_score` and "solo nuevas" filters don't react to
  scores arriving via HTMX OOB swap during the batch chain. User
  sees 3 of 31 when it should be 21. ~1–2 h. **Product-breaking.**
- [REQ-009](requirements/REQ-009-cache-key-lang-parity.md) — bucket
  A. Apply the `job_scores` cache-key fix pattern to
  `resume_suggestions` (#7) and `resume_ai_summary` (#8). ~1–1.5 h.
  Closes the drift entry in llm-surface.md.

**Buckets D, F, B shipped in the same session (docs + code):**
- **Bucket D (code)** — jobs_results: hide FR toggle when UI=es;
  hide Dismissed toggle when dataset has zero dismissed;
  base.html filter store: `onlyNew` unions `is_new || new_since_expand`;
  city placeholder now includes country example; jobs.html:
  loading stages (search / multi / URL) go through `_()` + `tojson`
  so overlay speaks the user's language; job-title first placeholder
  personalises using `resume_ai_summary.role_label` when cached,
  falls back to generic; `filters.only_new.tooltip` reworded to
  match new semantic.
- **Bucket F (code)** — full tailor-flow i18n sweep. 44 new keys
  (EN + ES parity). Covers: drawer chrome (base.html), tailor_panel
  (setup, runs, level tiles, generate/generating buttons, TAILOR_STAGES),
  tailor_runs_list (in-progress row), tailor_result (fallback banner,
  ribbon, meta line, insight, resume/cover sections, action row).
  Level labels + descs now flow as i18n keys from the route
  (`jobs_tailor_open`), not hardcoded English strings.
- **Bucket B (docs)** — [REQ-010](requirements/REQ-010-explicit-language-onboarding.md)
  + [ADR-009](decisions/ADR-009-explicit-language-onboarding.md).
  Extend the geo first-visit banner to also ask UI + output
  language; retire silent `Accept-Language` overwrites. Implementation
  is a follow-up sprint — this pass captures the architectural
  decision only.

**Open question for the user:** confirm with Mehran which button
exactly triggered the 54→98 score jump. Code mechanics say re-upload
of PDF (new `resume_id` → cache miss); if she insists it was only
"regenerate cleanly", there's an invalidation bug not covered by
REQ-009.

**Session hygiene note:** `/code-review medium` earlier today burnt
6/8 finders on rate-limit. Next end-of-sprint pass use `low` or
`ultra`, not `medium`. Cap sub-agent parallelism at 3–4 Sonnet by
default.

---

# Prior Sprint (shipped) — i18n + Geography + BI Agent

**Status:** shipped (PRs 1–6 landed weeks 2026-08-18 → 2026-08-25).
**Date:** 2026-08-18 (session-break checkpoint).
**Supersedes:** the earlier session-break notes; that version conflated
strategic direction and implementation.
**Related:** [mobile-plan.md](./mobile-plan.md), [rate-limiting-quotas.md](./rate-limiting-quotas.md).

## Why this is the sprint

Four real users are hunting for jobs. Sara lives in Spain, the sister
lives in Colombia — both write resumes in Spanish, and the app currently
hardcodes Ottawa + `country_indeed="canada"` + English prompts. Every
non-Canada, non-English user hits a wall before they see anything Jobot
is actually good at.

Fixing this unblocks half the user cohort AND makes Jobot honestly
usable outside a single metro. Deferring it means Sara and the sister
literally can't use the product.

Observability (BI agent) comes second because we already have a first
signal to react to.

## Locked design decisions (do NOT re-litigate)

### Three-language model — two knobs users flip

| Setting | Controls | Default |
|---|---|---|
| **UI language** | Nav, buttons, labels, filter chips, toasts | Browser `Accept-Language`; user override in Profile |
| **Output language** | Tailored resume + cover letter generation | Matches UI language on first set; changeable in Profile |
| **Reasoning language** | Score reasoning, gaps, matched skills on cards / detail pane | Follows UI language (coupled — reads weird otherwise) |

Two user-facing toggles: UI + Output. Reasoning piggybacks on UI.

### Geography

- Profile gets `home_country` + `home_city`.
- `JobSearchParams` default location comes from profile, not hardcoded.
- `country_indeed` derived from `home_country` via a small map.
- First-visit banner asks for city + country when country is missing;
  dismissible after fill.

### Prompt-language handling

Prompts stay in English (templates). Each gets a `{response_language}`
slot at the top: *"Respond in {language}. All strings in your output
must be in {language}."* Gemini is multilingual — no need for parallel
Spanish prompt templates.

### Storage (no auth yet)

Per-app settings live in the existing `meta` table:
- `settings.ui_language`
- `settings.output_language`
- `settings.home_country`
- `settings.home_city`

No new `user_settings` table needed. When auth ships, these move to
`user_settings(user_id, key, value)`.

### Tailor versioning

Tailor history entries gain a `.language` field. History list shows
*"Balanced (ES) · 2d ago"* / *"Aggressive (EN) · today"*. Both language
versions coexist per user requirement about accumulating data in both.

### i18n mechanism

Two dict lookups (`EN`, `ES`) in a new `ui_web/i18n.py`. Templates use
`{{ _('key') }}` via a Jinja global. **No Babel, no `.po` files, no
compile step.** For two languages a dict is the honest choice.

### BI agent

- Weekly scheduled task (GitHub Actions cron, hits each app's admin
  API endpoint).
- Runs a Gemini prompt against `events` + `jobs` + `applications` +
  `viewed_jobs` + `dismissed_jobs`.
- Fixed question set (see PR 6).
- Writes markdown to `admin_reports(week, app, report_md, generated_at)`.
- Single `/admin/pulse` route renders the latest.
- **Not** a real-time dashboard. Weekly is the cadence.

### Subagent model tiering

- Research / lookup → `general-purpose` with `model: sonnet-4-6` (or
  haiku when the task is straight-up factual).
- Deep synthesis (design docs, architecture) → `fork` (inherits Opus).
- Implementation code → main session, no subagent.

Net: research becomes 3-4× cheaper without losing quality.

## Sprint plan — ordered PRs

Each PR ships independently and can be validated on a Fly deploy before
the next starts. Times are Claude-execution time, not human-dev time.

### PR 1 — Settings model + i18n helper (~1 h)
- `core/settings.py`: `get_setting(key)`, `set_setting(key, value)`
  reading/writing `meta` table with a small in-process cache.
- `ui_web/i18n.py`: EN/ES translation dicts (initially seeded with
  ~30 core strings), `translate(key, lang=None)` helper, exposed to
  Jinja as `_()` global via `templates.env.globals`.
- Middleware: reads `settings.ui_language` (or falls back to
  `Accept-Language`) and stashes it on `request.state.ui_language`.
- **No template touches yet** — plumbing only.

### PR 2 — Geography (profile fields + defaults) (~1 h)
- `home_country` + `home_city` in `meta` via new settings API.
- `core/jobs/search.py`: `JobSearchParams` default `location` reads
  from settings; `country_indeed` derived from a `_COUNTRY_TO_INDEED`
  dict (Canada, US, UK, Spain, Colombia, Mexico, Argentina, Chile,
  France, Germany).
- Profile UI: two inputs for home country + home city with typeahead
  reuse from the existing Photon integration.
- First-visit banner in `base.html`: shows when both are empty; single
  form; dismisses on save.

### PR 3 — Prompt language passthrough (~1.5 h)
- New helper `get_output_language()` (Output setting) and
  `get_reasoning_language()` (mirrors UI setting).
- Every prompt template touched with a `{response_language}` slot:
  - `core/jobs/from_url.py::_build_extraction_prompt`
  - `core/matching/semantic_score.py::_score_batch` (scoring prompt)
  - `core/llm/rewrite.py::rewrite_resume` + cover-letter prompt
  - `core/llm/prompts.py` templates
  - `ui_web/routes/jobs.py::_generate_variant_queries` (expand)
- Callers pass the resolved language string into each `generate_json`
  call.
- Prompt-injection sentinel + validators from earlier PR still apply.

### PR 4 — Profile settings UI + UI translation pass 1 (~1.5 h)
- Profile: two toggles (UI language, Output language) inside the
  existing Settings block — replaces / joins the Notifications tab.
  Persisted via settings API.
- Wrap user-visible strings on the three highest-value pages in `_()`:
  - `pages/jobs.html` + `pages/jobs_results.html` + `pages/profile.html`
  - `partials/job_card.html` + `partials/mobile_nav.html` + `base.html` header
  - Toast messages / kill-switch messages
- Fill Spanish dict for those strings (~80 strings). Anything not
  translated falls back to English.

### PR 5 — Tailor history language versioning (~30 min)
- `state.tailored_history[job_id]` entries gain `.language`.
- Tailor drawer's "past runs" list shows `(EN)` / `(ES)` suffix per
  entry, and orders newest-first regardless of language.
- Download filename includes language suffix.

### PR 6 — BI agent + admin pulse (~4 h)
- Schema bump 10 → 11: `admin_reports(week, app_name, report_md,
  generated_at, question_set_version)`.
- New `scripts/bi_agent.py`: for each app URL, calls a new
  `/admin/bi-snapshot` endpoint that returns a JSON dump of aggregate
  metrics (no PII beyond what's already in the DB), then feeds that
  JSON to Gemini with the question-set prompt, then POSTs the markdown
  report back to `/admin/bi-report`.
- Question set v1:
  1. Engagement per user — sessions/week, active-days/week
  2. Funnel per user — search → view → save → tailor → apply, with
     drop-off percentages
  3. Score quality signal — dismiss rate at each 10-point score band
  4. Stuck patterns — same job viewed 3+ times without action
  5. Delta vs. previous week — what changed
- `/admin/pulse` route renders the latest report (Jinja + markdown
  filter). Simple, unstyled — this is a report, not a dashboard.
- GH Actions cron: `0 6 * * 1` (Monday 06:00 UTC). Runs the script
  against all 3 apps in parallel via a matrix.
- Auth on `/admin/*`: HTTP Basic with a single admin password (from
  `fly secrets set ADMIN_PASS=…`). Placeholder until real auth ships.

### PR 7 (optional, only if PR 4 leaves gaps) — UI translation pass 2 (~1 h)
- Journey page + Applications sub-view + edge/empty states
- Any strings PR 4 skipped

**Total: ~10-11 hours of Claude execution across 6 required + 1 optional PRs.**

## Open decisions the user must resolve before PR 1 starts

1. **Should PR 6 (BI agent) piggyback on the sprint, or land in a follow-up?**
   Cleaner separation would say "ship the i18n+geo bundle first, then BI
   in a follow-up sprint." Faster to ship both together while the
   architecture is fresh. Recommendation: bundle. It's independent code
   and doesn't slow the language work.

2. **Country-to-`country_indeed` map coverage.** Confirmed: Canada, US,
   UK, Spain, Colombia. Anything else worth pre-adding? Mexico,
   Argentina, Chile, France, Germany would round it out. Recommendation:
   include all 10 in one shot.

3. **UI-language default source.** `Accept-Language` header vs. always
   ask on first visit. Recommendation: `Accept-Language` first, ask only
   if browser doesn't send a supported lang.

4. **Reasoning language coupling.** Locked to UI language for now. Any
   scenario where a user wants Spanish UI but English gaps/matched?
   Recommendation: no. Cognitive cost > flexibility gain.

## What's explicitly NOT in this sprint

- **Auth / multi-user rewrite.** 3-app pattern still fine for N=4.
- **Full admin UI.** BI markdown report is the interim.
- **Additional languages beyond ES.** Dict pattern makes adding a third
  language trivial; not this sprint's work.
- **Live analytics dashboard.** Weekly BI report replaces it for now.
- **Per-search language override.** User goes to Profile to change.
- **Rich onboarding flow.** First-visit banner is enough for now.
- **Migrating individual apps to a shared codebase.** They ARE the
  isolation layer. Keep them.

## Subagent tiering rule (self-instruction for this sprint)

When I need external research or lookup (e.g. "what's the standard
`country_indeed` value for Spain?"), spawn `general-purpose` with
`model: "claude-sonnet-4-6"`. When I need synthesis with full context,
`fork` and pay for Opus. For implementation, main session executes
directly — no subagent hop.

Estimate: sprint runs 3-4× cheaper than if I forked everything.

## Sequencing calendar (rough)

- **Day 1 (this or next session):** PR 1 + PR 2 + PR 3 → the language +
  geography plumbing lands together. Ship. Users can now change UI
  language and see their home city as the default.
- **Day 2:** PR 4 + PR 5 → visible i18n in the UI + versioned tailor
  history. Sara and the sister can now use the app end-to-end in Spanish.
- **Day 3:** PR 6 + PR 7 → BI agent lands, admin can see how the 4 users
  actually behave. Any translation gaps get filled.
- **Week 2:** Wait. Read what the BI agent says. Don't build more until
  we know.
