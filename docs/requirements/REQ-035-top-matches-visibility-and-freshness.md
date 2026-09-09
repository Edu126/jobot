# REQ-035: Top matches — make it show, drop stale postings (>5d)

Date: 2026-09-08
Source: Eduardo
Status: Open

## What they asked for
Verbatim: "no veo lo del section de top matches, tipo la colección de vacantes
recientes donde yo tengo alto puntaje (no se muestra) … pero pensando, si la
vacante es más de 5 days old, remover el perfil de ahí."

## What they actually need
The "Top matches for you" section **exists** (`pages/jobs.html:386`, populated by
`_list_top_matches`, `min_score=65`) but rendered empty for **everyone**.

**Root cause found on -edu (2026-09-08) — a bug, NOT scoring coverage.** -edu has
183 scored jobs, **116 ≥ 65** (max 90), 7 cache files. Yet `_list_top_matches`
returned 0. The cache files are **pointer format** (`{fetched_at, params_label,
params, job_ids: [...]}`) — there is no `jobs` key. But `_list_top_matches` read
`data.get("jobs", [])`, which is `[]` for every file, so no job was ever
considered. `cache.load()` already hydrates pointers via `db.get_jobs()`; this one
call site didn't. Simulating the fix on -edu: 189 hydrated ids, **115 scored ≥65**
→ Top matches populates.

Two parts:
1. **Fix visibility (done)** — hydrate pointer files in `_list_top_matches`
   (`data["job_ids"] → db.get_jobs()`), keeping the legacy inline `jobs` path. The
   ≥65 gate was never the problem, so it stays untouched.
2. **Freshness rule** — drop entries older than **5 days**. `_age_days` is already
   computed from `fetched_at`; apply a 5-day cutoff. Posting age isn't trustworthy,
   so fetch age is the pragmatic proxy.

## How we'll know it worked
A user with scored searches sees their high-score jobs curated in Top matches;
nothing older than 5 days appears there.
