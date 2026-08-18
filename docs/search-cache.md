# Search Cache & Coverage — How It Works, Where It Falls Short

**Status:** research + design notes, no code yet.
**Date:** 2026-08-17
**Related:** [ats-research.md](./ats-research.md), [rate-limiting-quotas.md](./rate-limiting-quotas.md)

## 1. The concern

> Default is 30 jobs per search — if I look for "junior construction PMO" and
> then search again, all the results are going to be cached from the previous
> one. How do we gather more roles?

Short answer: today, "search again with identical params" just re-runs the
scrape (there's no cache-hit short-circuit on submit) but jobspy returns
roughly the same 30 top-ranked postings each time. To surface new roles we
need to vary the query dimension we're expanding along — time window, radius,
sites, related titles — not just re-run the same scrape.

## 2. How the current pipeline works

Files involved:
- `core/jobs/search.py` — `JobSearchParams`, `search_jobs()`, dedup.
- `core/jobs/cache.py` — disk cache keyed by SHA-1(params).
- `ui_web/routes/jobs.py` — `/jobs/run`, `/jobs/run/multi`, results page.

### `JobSearchParams` (search.py:29)
```
query, location, distance=50, sites=[indeed, linkedin, google],
hours_old=168, results_wanted=30, is_remote=None, country_indeed=canada,
linkedin_fetch_description=True
```

`cache_key()` (search.py:46) is `sha1(json.dumps(asdict(self), sort_keys=True))[:16]`
— it hashes **every** param. Any change to any field → different cache key →
separate cache file → a fresh scrape.

### `/jobs/run` (jobs.py:458)
```python
jobs = search_jobs(params)     # always runs a fresh scrape
if not jobs: ...
jobs_cache.save(params, jobs, label=label)
return HX-Redirect → /jobs/results/{params.cache_key()}
```

There is **no cache lookup on submit** — every submit runs jobspy. The cache
is only read when rendering `/jobs/results/{cache_key}`. So "same query
submitted twice" burns a second scrape and overwrites the cache file.

### `/jobs/run/multi` (jobs.py:641)
1–3 queries, run sequentially with an 8s cooldown, merged by `Job.id` into a
single cache entry labeled `"Multi: A + B + C"`. Bulk path already handles
multi-query aggregation but the cache key is a synthetic `multi_{timestamp}`
— so every multi-run gets a fresh cache entry, never merged with prior runs.

### The cache itself (`cache.py`)
- One JSON file per `cache_key` in `data/jobs_cache/`.
- Stored: `fetched_at`, `params_label`, full `params` dict, list of Job dicts.
- No TTL. Files live forever unless deleted.
- `list_recent(limit)` — glob + sort by `fetched_at`, used for the "recent
  searches" picker.

## 3. What actually limits coverage today

Three separate ceilings:

1. **`results_wanted=30` on the params.** jobspy's `scrape_jobs()` caps its
   fetch at this. Bumping to 100 makes each scrape slower (more page loads)
   and gets rate-limited faster, but gets more coverage.

2. **jobspy's per-site pagination.** Even with `results_wanted=100`, some
   sources bottom out earlier (Google-for-Jobs snippets thin out past ~40).
   Real ceiling per source is roughly Indeed ~200, LinkedIn ~100, Google ~40.

3. **Overlap across sources.** Dedup runs cross-source
   (`_dedup_across_sources`, search.py:120) via `(company|title|location)` key
   — for a specific query like "junior construction PMO Ottawa", the same
   ~15 real jobs surface from all three sources. Total unique output is
   often way under `results_wanted`.

Also worth noting: `hours_old=168` (1 week) means anything posted >7 days ago
is invisible. On a niche query in a small metro, that's most of the market.

## 4. The user's real question, unpacked

Two different asks smuggled into one:

**A. "If I re-search, do I get the same 30 again?"**
Yes — same params → same top-30 posting set. Right now the second submit
even scrapes again, wasting a request. Fix: on `/jobs/run`, check
`jobs_cache.load(params)` first; if hit is younger than N hours, HX-Redirect
straight to the results page without re-scraping.

**B. "How do I get MORE than those 30 unique jobs?"**
Need to expand along one of these axes, then merge:
- `results_wanted`: 30 → 60 → 100 (diminishing returns; rate-limit risk).
- `hours_old`: 168 → 336 → 720 (fresh scrape covering older postings).
- `distance`: 50 → 100 km (grabs adjacent metros).
- `sites`: add `glassdoor`, `zip_recruiter` to the mix.
- **Related titles**: "PMO coordinator" → also "project coordinator", "junior
  scheduler", "site coordinator". Bulk-multi already does this manually; we
  can auto-generate them with the LLM.

The winning UX is probably one "Expand this search" button on the results
page that runs 2–3 auto-generated variants in the background, merges into the
same cache entry, and reloads.

## 5. Recommendations

### 5.1 Fix the cheap bugs first
- **Cache-hit short-circuit on submit.** In `/jobs/run`, before calling
  `search_jobs`, check `jobs_cache.load(params)`. If hit is <6h old, redirect
  to results directly — save the scrape, save the rate-limit budget. Add a
  `?force=1` query param that bypasses this for a manual re-run.
- **Cache TTL.** Add an implicit "stale" flag when `fetched_at` is >24h old,
  shown in the recent-searches picker. Optionally auto-refresh on click.
- **Delete-cache endpoint** for admin use — currently the only way to clear
  a bad cache is `rm` in the data dir.

### 5.2 "Expand this search" — the main answer to the user's question
On the results page, add a button that runs a background broadening pass:

```
POST /jobs/results/{cache_key}/expand
  → in a thread:
    1. Generate 2 related-title variants via Gemini (cheap; ~200 tokens):
         input: original query + top-5 titles in current results
         output: 2 adjacent titles NOT already covered
    2. Run each variant with same location + broader hours_old (2x current).
    3. Merge all new jobs into the ORIGINAL cache file by Job.id.
    4. Update label to "{query} (expanded)".
    5. Update fetched_at, push a note to the results page (HTMX poll or SSE).
```

Batching + cooldown between the variant scrapes reuses the existing
`_run_multi_background` pattern. Cap at 2 variants (or 3 total scrapes per
expand) to stay under jobspy's rate-limit radar.

### 5.3 Broader coverage without extra scrapes
- **Persistent job DB, not per-search files.** `search.py` header note
  already flags this as out-of-scope-for-now — but once we have any second
  search that overlaps, we're re-storing the same job twice. Migrate to a
  single `jobs` table keyed by Job.id (already exists via
  `db.upsert_jobs()`), and turn cache files into just `{cache_key: [job_id,
  …]}` pointer sets. That way an "expanded" search merges into the shared
  DB naturally.
- **Background daily refresh.** For saved searches on the profile, run them
  once per day off-hours (see rate-limiting-quotas.md for scheduling). The
  user opens the app to already-fresh results.
- **Auto-widening on empty.** Current `/jobs/run` returns "no results, try
  broader terms" — we could just do the broadening automatically: 168 → 720
  hours, 50 → 100 km, retry once, and label the widened result set clearly.

### 5.4 Guard rails so this doesn't spiral
Expanding a search means N × scrapes. Concrete limits so we don't get blocked:
- **Per-user daily scrape budget.** Even for the single-user MVP, cap at 30
  scrapes/day (roughly one every 30 minutes over 16 waking hours). Reject
  the 31st with "try again tomorrow". See rate-limiting-quotas.md §4.
- **Per-source cooldown.** jobspy already handles some internal pacing but
  we should enforce ≥8 s between scrapes at our layer (`_run_multi_background`
  already does 8 s — extract that constant).
- **Circuit breaker on blocks.** `events.SEARCH_BLOCKED` already fires. Add
  a rule: if we get 3 blocks from the same source in 1 hour, disable that
  source for 24 h. `search.blocked` events feed a small `data/blocks.json`
  state file.

## 6. What NOT to do

- Don't bump default `results_wanted` past 50 for interactive searches. The
  scrape gets noticeably slower (>60s) and rate-limit risk climbs. If we
  need more, expand across queries instead of within one query.
- Don't disable dedup across sources to inflate counts. Same job appearing
  three times isn't more coverage, it's UI noise.
- Don't run the "expand" pass automatically on every search — burns the
  daily scrape budget. Keep it explicit (button click) or scheduled
  (background daily refresh for saved searches).
- Don't move the cache to Redis. SQLite + files fits the app's scale and
  hosting story; a Redis dep is overkill and one more thing to manage on Fly.

## 7. Recommended order of work

1. Cache-hit short-circuit in `/jobs/run` (30 min).
2. Extract cooldown constant + block-attribution history file (1 h).
3. "Expand this search" endpoint + LLM-generated variants + merge into
   existing cache entry (half-day).
4. Auto-widen on empty results (1 h).
5. Migrate cache files → cache pointers + shared jobs table (~1 day,
   coordinated with any DB schema change).
6. Background daily refresh for saved searches — build once the auth /
   multi-user story is ready, so we know whose searches to refresh.

Items 1–2 unblock everything else. Item 3 is the actual answer to the
user's original question.
