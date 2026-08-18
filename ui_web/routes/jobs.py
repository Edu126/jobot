"""Jobs tab routes.

Flow:
    GET  /jobs                              → search picker (default landing)
    POST /jobs/run                          → execute a saved or custom search;
                                              returns HX-Redirect to /jobs/results/{key}
    GET  /jobs/results/{cache_key}          → results page: cards, filters, AI scoring
    POST /jobs/save/{job_id}                → save-as-interested (HTMX card fragment)

    GET  /jobs/tailor/{job_id}              → open tailor panel (fragment)
    POST /jobs/tailor/{job_id}              → generate tailored resume + cover letter
    POST /jobs/tailor/{job_id}/save         → persist tailored output to application
    GET  /jobs/tailor/{job_id}/download     → download tailored DOCX

State:
    Search results → disk cache (data/jobs_cache/{key}.json) — reused from v1.
    AI scores → SQLite `job_scores` table (see semantic_score.score_jobs).
    Tailored dicts → in-memory `state.tailored_results` (single-user local).
"""
from __future__ import annotations

import io
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from core import db, events, feature_flags
from core.jobs import cache as jobs_cache
from core.jobs import tasks as search_tasks
from core.jobs.from_url import (
    UrlExtractError,
    UrlFetchError,
    extract_job_from_text,
    fetch_page_text,
)
from core.jobs.search import Job, JobSearchParams, search_jobs
from core.llm.gemini import (
    DEFAULT_MODEL,
    GeminiClient,
    GeminiError,
    QuotaExhaustedError,
    exhausted_models,
    resolve_api_key,
)
from core.llm.prompts import Level
from core.llm.rewrite import rewrite_resume, tailored_to_text
from core.matching.semantic_score import (
    ScoreResult,
    score_jobs as score_jobs_batch,
    score_single_no_cache,
)
from core.resume.writer import render_cover_letter_docx, render_docx

from .. import state
from ..deps import slugify, templates
from ..ratelimit import limiter
from ..state import get_tailored, list_runs, record_tailor


router = APIRouter(tags=["jobs"])


# Cache-hit short-circuit: a search resubmitted with identical params
# within this window skips the scrape and jumps straight to results.
# Job market moves slowly enough that 6h feels "instant on resubmit" while
# not hiding meaningful churn. `?force=1` on /jobs/run bypasses.
_CACHE_SHORT_CIRCUIT_SECONDS = 6 * 3600

# Cooldown between sequential scrapes anywhere in this module (multi-search,
# expand, bulk). Was previously a local constant in `_run_multi_background`;
# hoisted here so every scrape path uses the same pacing.
_SCRAPE_COOLDOWN_S = 8


def _scrape_disabled_response() -> HTMLResponse:
    """HTMX-friendly 503 when SCRAPE_DISABLED is set. Returned inline so
    the existing error slots on the jobs page render it correctly."""
    return HTMLResponse(
        f'<div class="alert alert-warning text-sm p-3">{feature_flags.scrape_disabled_message()}</div>',
        status_code=feature_flags.KILL_SWITCH_STATUS,
    )


def _tailor_disabled_response() -> HTMLResponse:
    """HTMX-friendly 503 when TAILOR_DISABLED is set."""
    return HTMLResponse(
        f'<div class="alert alert-warning text-sm">{feature_flags.tailor_disabled_message()}</div>',
        status_code=feature_flags.KILL_SWITCH_STATUS,
    )


# Regex-driven experience extraction. Ordered by specificity — first hit wins
# so "3-5 years" matches before the more permissive "5+ years" pattern.
# Kept in the route (not core/) because it's a UI-affordance, not domain logic.
_EXPERIENCE_PATTERNS = [
    # "3-5 years of experience" / "3 to 5 years"
    re.compile(r"\b(\d+)\s*(?:-|to|–)\s*(\d+)\+?\s*years?\s+(?:of\s+)?(?:relevant\s+)?experience\b", re.I),
    # "5+ years experience" / "5 or more years"
    re.compile(r"\b(\d+)\s*\+?\s*(?:or\s+more)?\s*years?\s+(?:of\s+)?(?:relevant\s+)?experience\b", re.I),
    # "minimum 3 years" / "at least 3 years"
    re.compile(r"\b(?:minimum|at\s+least)\s+(?:of\s+)?(\d+)\s*(?:\+)?\s*years?\b", re.I),
    # Fallback: any "N+ years" mention
    re.compile(r"\b(\d+)\s*\+\s*years?\b", re.I),
]


def _list_top_matches(min_score: int = 65, limit: int = 20) -> tuple[list[dict], int]:
    """Aggregate top-scored jobs across all cached searches for the current
    resume. Deduplicated by job_url; sorted by score desc. Enriches each job
    with the same `_score/_verdict/_reasoning/_matched/_gaps/_experience/_app_status`
    fields the results page uses, so job_card.html can render them identically.

    Returns (jobs, cache_count) — cache_count is the number of cache files
    we swept, useful for the header ("across N searches").
    """
    resume = db.get_current_resume()
    if not resume:
        return [], 0
    resume_id = int(resume["id"])

    all_jobs: list[tuple[dict, str, str]] = []   # (job_dict, source_label, fetched_at)
    cache_count = 0
    import json as _json
    for path in jobs_cache.CACHE_DIR.glob("*.json"):
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        cache_count += 1
        label = data.get("params_label") or path.stem[:8]
        fetched_at = data.get("fetched_at", "")
        for j in data.get("jobs", []):
            all_jobs.append((j, label, fetched_at))

    if not all_jobs:
        return [], cache_count

    # Single DB query for all scores + first_seen (for "new job" flag)
    all_ids = list({j["id"] for j, _, _ in all_jobs})
    scores = db.get_cached_scores(resume_id, all_ids)
    first_seens = db.get_first_seen_batch(all_ids)

    # Dedupe by URL (fallback to id if URL missing). Keep highest score per URL.
    from datetime import datetime as _dt
    now = _dt.utcnow()
    by_url: dict[str, dict] = {}
    for job, source, fetched_at in all_jobs:
        s = scores.get(job["id"])
        if not s or s["score"] < min_score:
            continue
        url = job.get("job_url") or job["id"]
        existing = by_url.get(url)
        if existing is not None and existing["_score"] >= s["score"]:
            continue

        # Compute age in days for the client-side date filter
        age_days = 999
        if fetched_at:
            try:
                fetched_dt = _dt.fromisoformat(fetched_at.rstrip("Z"))
                age_days = max(0, int((now - fetched_dt).total_seconds() / 86400))
            except Exception:
                pass

        # "New" = first seen in the last 48h. Uses jobs.first_seen from DB,
        # which is set on upsert — only newly-encountered ids get a fresh stamp.
        is_new = False
        fs = first_seens.get(job["id"])
        if fs:
            try:
                fs_dt = _dt.fromisoformat(fs.rstrip("Z"))
                is_new = (now - fs_dt).total_seconds() < 48 * 3600
            except Exception:
                pass

        app = db.get_application_by_job(job["id"])
        by_url[url] = {
            **job,
            "_score": s["score"],
            "_verdict": s["verdict"],
            "_reasoning": s["reasoning"],
            "_matched": _json.loads(s["matched_json"]),
            "_gaps": _json.loads(s["gaps_json"]),
            "_source_label": source,
            "_fetched_at": fetched_at,
            "_age_days": age_days,
            "_is_new": is_new,
            "_experience": _extract_experience(job.get("description", "")),
            "_app_status": app["status"] if app else None,
        }

    top = sorted(by_url.values(), key=lambda x: x["_score"], reverse=True)[:limit]
    return top, cache_count


def _extract_experience(description: str) -> Optional[str]:
    """Try to pull a compact experience-required string from a JD.

    Returns None if we can't confidently identify one — we'd rather show
    nothing than a wrong or misleading label.
    """
    if not description:
        return None
    text = description[:2500]   # cap — reqs are usually near the top

    for pat in _EXPERIENCE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        groups = m.groups()
        if len(groups) >= 2 and groups[1]:
            return f"{groups[0]}–{groups[1]} yrs"
        return f"{groups[0]}+ yrs"

    # Softer signal: seniority keyword in title-like proximity
    for kw, label in [
        ("senior", "Senior"),
        ("junior", "Junior"),
        ("entry.level", "Entry level"),
        ("lead ", "Lead"),
        ("principal", "Principal"),
    ]:
        if re.search(r"\b" + kw + r"\b", text[:400], re.I):
            return label
    return None


# ─────────────────────────────────────────────────────────────
# Search picker (default landing)
# ─────────────────────────────────────────────────────────────

@router.get("/api/geocode")
async def api_geocode(request: Request):
    """Location typeahead — proxies Photon (photon.komoot.io, free, no auth,
    OSM-derived). Returns a styled custom dropdown fragment (not a native
    <datalist>) so we control the look + kill the browser's built-in
    dropdown arrow that used to appear next to the input.

    In-memory cache: 24h TTL per lowercased query so we don't hammer Photon
    when the user retypes 'Ottawa' every session. Silent-fails to a hidden
    dropdown on any error — the input is still typable manually."""
    import urllib.parse
    import urllib.request
    import json as _json
    from datetime import datetime as _dt, timedelta as _td

    # Location input has name="location" so HTMX auto-includes it.
    q = (request.query_params.get("location") or request.query_params.get("q") or "").strip()[:60]
    idx = "0"
    if len(q) < 2:
        return HTMLResponse("", status_code=200)

    key = q.lower()
    now = _dt.utcnow()
    cache = state.geocode_cache
    items: list[str] = []
    hit = cache.get(key)
    if hit and hit["expires"] > now:
        items = hit["items"]
    else:
        try:
            url = (
                "https://photon.komoot.io/api/"
                f"?q={urllib.parse.quote(q)}&limit=5&layer=city"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "jobot/0.5"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            seen: set[str] = set()
            for feat in (data.get("features") or [])[:5]:
                p = feat.get("properties") or {}
                name = p.get("name") or ""
                state_or_region = p.get("state") or ""
                country = p.get("country") or ""
                parts = [x for x in (name, state_or_region, country) if x]
                display = ", ".join(parts)
                if not display or display.lower() in seen:
                    continue
                seen.add(display.lower())
                items.append(display)
                if len(items) >= 5:
                    break
            cache[key] = {"items": items, "expires": now + _td(hours=24)}
        except Exception:
            items = []

    return templates.TemplateResponse(
        request,
        "partials/typeahead_dropdown.html",
        {"items": items, "idx": idx, "kind": "loc"},
    )


@router.get("/api/search-suggest")
async def api_search_suggest(request: Request):
    """Job-title typeahead — same dropdown pattern as geocode. Pulls from
    three LOCAL sources (prefix match, case-insensitive, cap 5):
      1. Saved searches — the user's own explicit picks (highest signal)
      2. Recent scrape queries from data/jobs_cache/*.json (what they ran)
      3. AI-generated suggestions cached per resume (lowest signal)
    Zero LLM calls; deterministic; instant."""
    import json as _json

    # Query inputs have name="queries" so HTMX auto-includes them. When
    # multiple query rows exist, the input that TRIGGERED the request is
    # the last param (HTMX overrides). Take the last, fall back to first.
    values = request.query_params.getlist("queries") or request.query_params.getlist("q")
    prefix = (values[-1] if values else "").strip().lower()[:60]
    idx = "0"
    if len(prefix) < 1:
        return HTMLResponse("", status_code=200)

    seen: set[str] = set()
    items: list[str] = []

    def _add(candidate: str) -> None:
        c = (candidate or "").strip()
        if not c or c.lower() in seen or not c.lower().startswith(prefix):
            return
        seen.add(c.lower())
        items.append(c)

    for s in db.list_saved_searches():
        _add(s.get("query") or "")
        if len(items) >= 5:
            break

    if len(items) < 5:
        for path in sorted(
            jobs_cache.CACHE_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:30]:
            try:
                data = _json.loads(path.read_text(encoding="utf-8"))
                params = data.get("params") or {}
                _add(params.get("query", ""))
                if len(items) >= 5:
                    break
            except Exception:
                continue

    if len(items) < 5:
        resume = db.get_current_resume()
        if resume:
            cached = db.get_cached_suggestions(int(resume["id"]))
            for q in (cached or {}).get("queries", []) or []:
                _add(q)
                if len(items) >= 5:
                    break

    return templates.TemplateResponse(
        request,
        "partials/typeahead_dropdown.html",
        {"items": items[:5], "idx": idx, "kind": "q"},
    )


@router.get("/jobs/quick-fill")
async def jobs_quick_fill(request: Request):
    """Chip-row fragment. Called by the Jobs page on first visit when the
    AI-suggestion cache is empty — HTMX auto-fetches this, we generate the
    suggestions (spends ~1 LLM call), and swap the fragment in. Also the
    endpoint the 'Shuffle' button hits when the user forces a regen."""
    from .profile import _get_or_generate_suggestions
    force = request.query_params.get("force", "0") == "1"
    queries, error, age_days = _get_or_generate_suggestions(force=force)
    quick_fill = [{"kind": "ai", "label": q, "query": q} for q in queries[:6]]
    return templates.TemplateResponse(
        request,
        "partials/quick_fill_row.html",
        {"quick_fill": quick_fill, "error": error},
    )


@router.get("/jobs")
async def jobs_landing(request: Request):
    """Landing: Search block (custom + bulk + recent) at top, Top matches below.
    Templates are now editable from the Profile tab — not shown here."""
    recent = jobs_cache.list_recent(limit=6)
    resume = db.get_current_resume()
    has_key = bool(resolve_api_key())

    top_matches: list[dict] = []
    cache_count = 0
    if resume:
        top_matches, cache_count = _list_top_matches(min_score=65, limit=20)

    # Quick-fill chips are AI-only now. Old behavior mixed saved searches
    # (which shipped as AEC defaults) into every user's chips — noise for
    # Melissa/hermana in different domains. Saved searches still exist in
    # DB; they'll live in a typeahead/autocomplete on the search input in
    # a future pass. If AI suggestions aren't cached yet, the template
    # auto-fetches them on first Jobs visit (see quick_fill_needs_fetch).
    all_saved = db.list_saved_searches()   # kept for future autocomplete
    seen_q: set[str] = set()
    quick_fill: list[dict] = []
    if resume:
        cached_suggestions = db.get_cached_suggestions(int(resume["id"]))
        for q in (cached_suggestions or {}).get("queries", []):
            key = str(q).strip().lower()
            if not key or key in seen_q:
                continue
            seen_q.add(key)
            quick_fill.append({"kind": "ai", "label": q, "query": q})
            if len(quick_fill) >= 6:
                break

    # Trigger a fresh generation on first visit when cache is empty AND
    # user has both a resume + an API key (both needed to succeed).
    quick_fill_needs_fetch = (
        not quick_fill and bool(resume) and has_key
    )

    return templates.TemplateResponse(
        request,
        "pages/jobs.html",
        {
            "active_tab": "jobs",
            "saved_searches": all_saved,           # future: autocomplete source
            "quick_fill": quick_fill,               # AI only, ≤6 items
            "quick_fill_needs_fetch": quick_fill_needs_fetch,
            "recent": recent,
            "has_resume": bool(resume),
            "has_api_key": has_key,
            "top_matches": top_matches,
            "cache_count": cache_count,
        },
    )


# ─────────────────────────────────────────────────────────────
# Run a search
# ─────────────────────────────────────────────────────────────

@router.post("/jobs/run")
@limiter.limit("30/hour")
async def jobs_run(
    request: Request,
    search_name: Optional[str] = Form(None),
    custom_query: Optional[str] = Form(None),
    custom_location: Optional[str] = Form("Ottawa, Ontario, Canada"),
):
    """Execute a jobspy scrape. Sync (30-90s) — HTMX spinner covers the wait.

    Returns an HX-Redirect header to the results page. HTMX will do a full
    navigation on receiving it; regular form submitters get a 200 with the
    link exposed so we don't fall over.
    """
    if feature_flags.is_scrape_disabled():
        return _scrape_disabled_response()
    if search_name:
        # search_name is now a DB row id (from the saved-searches picker on
        # Profile) OR still the string name for backward-compat with older
        # links. Try id first, then fall back to name lookup.
        row = None
        try:
            row = db.get_saved_search(int(search_name))
        except (ValueError, TypeError):
            row = None
        if not row:
            for s in db.list_saved_searches():
                if s["name"] == search_name:
                    row = s
                    break
        if not row:
            raise HTTPException(status_code=404, detail=f"Saved search not found: {search_name}")
        params = JobSearchParams(
            query=row["query"],
            location=row["location"],
            distance=row["distance"],
            hours_old=row["hours_old"],
            results_wanted=row["results_wanted"],
        )
        label = row["name"]
    elif custom_query and custom_query.strip():
        params = JobSearchParams(
            query=custom_query.strip(),
            location=(custom_location or "Ottawa, Ontario, Canada").strip(),
        )
        # No "Custom:" prefix — the query itself is the identity
        label = params.query
    else:
        raise HTTPException(status_code=400, detail="Provide search_name or custom_query")

    # Cache short-circuit: identical params submitted within 6h skips the
    # scrape and jumps straight to results. Saves rate-limit budget on
    # accidental double-submits and back-button retries. `?force=1`
    # bypasses (Refresh button, admin re-run).
    force = request.query_params.get("force", "0") == "1"
    if not force:
        cached = jobs_cache.load(params)
        if cached and cached.jobs:
            age = jobs_cache.age_seconds(cached.fetched_at)
            if age is not None and age < _CACHE_SHORT_CIRCUIT_SECONDS:
                resp = Response(status_code=200)
                resp.headers["HX-Redirect"] = f"/jobs/results/{params.cache_key()}"
                return resp

    try:
        jobs = search_jobs(params)
    except RuntimeError as exc:
        return HTMLResponse(
            f'''<div class="rounded-lg p-3 my-3 flex items-start gap-3 text-sm"
                     style="background: hsl(0 60% 96%); border: 1px solid hsl(0 50% 88%);">
                  <i class="ph-thin ph-warning-octagon" style="font-size: 1.25rem; color: hsl(0 60% 45%);"></i>
                  <div>
                    <div class="font-semibold">Search failed</div>
                    <div class="text-body-muted mt-0.5">{exc}</div>
                  </div>
                </div>''',
            status_code=200,
        )

    # Auto-widen on empty results: retry once with doubled hours_old +
    # distance. Small firms + niche titles often have nothing in 168h/50 km
    # but plenty in 336h/100 km. Cache is written against the widened
    # params so a second submit hits the short-circuit above.
    widened_note = ""
    if not jobs:
        time.sleep(_SCRAPE_COOLDOWN_S)
        widened = JobSearchParams(
            query=params.query,
            location=params.location,
            distance=params.distance * 2,
            sites=list(params.sites),
            hours_old=params.hours_old * 2,
            results_wanted=params.results_wanted,
            is_remote=params.is_remote,
            country_indeed=params.country_indeed,
            linkedin_fetch_description=params.linkedin_fetch_description,
        )
        try:
            jobs = search_jobs(widened)
        except RuntimeError:
            jobs = []
        if jobs:
            params = widened
            label = f"{label} (widened)"
            widened_note = " widened to " + f"{widened.hours_old // 24}d/{widened.distance}km"

    # Still nothing after widening — surface the same "no results" message
    # the original code showed, with a note that we widened once.
    if not jobs:
        return HTMLResponse(
            f'''<div class="rounded-lg p-4 my-3 flex items-start gap-3 text-sm"
                     style="background: hsl(35 85% 96%); border: 1px solid hsl(35 70% 82%);">
                  <i class="ph-thin ph-magnifying-glass" style="font-size: 1.25rem; color: hsl(28 75% 42%);"></i>
                  <div>
                    <div class="font-semibold">No results for "{params.query}"</div>
                    <div class="text-body-muted mt-1">
                      We also tried a wider search — still nothing. Try broader terms
                      (e.g. "Coordinator" instead of "Coordinator I") or a nearby city.
                    </div>
                  </div>
                </div>''',
            status_code=200,
        )

    # DB upsert must precede the cache save — cache files now store pointers
    # (job_ids), and the results page hydrates those ids from `db.jobs`.
    db.upsert_jobs([j.to_dict() for j in jobs])
    jobs_cache.save(params, jobs, label=label)

    target = f"/jobs/results/{params.cache_key()}"
    resp = Response(status_code=200)
    resp.headers["HX-Redirect"] = target
    return resp


# ─────────────────────────────────────────────────────────────
# Results page
# ─────────────────────────────────────────────────────────────

@router.get("/jobs/results/{cache_key}")
@limiter.limit("60/hour")
async def jobs_results(request: Request, cache_key: str):
    """Render the scored job list for a specific cached search.

    **No blocking Gemini calls here.** We read the SQLite score cache
    only. Any job without a cached score renders with a spinner in its
    badge, and the client kicks off `/jobs/results/{key}/score-batch`
    which streams scores in 5-at-a-time via OOB HTMX swaps. Users see
    the page instantly instead of waiting 30s+ for a full re-score
    after an Expand.

    `?view=fresh` — landed on after Expand completes. Same underlying
    cache; the template defaults its client-side filters to hide
    already-viewed jobs and chips cards that were added by the most
    recent expand pass as "new". The user can toggle back to the
    unified list without a server round-trip.
    """
    cached = _find_cached_by_key(cache_key)
    if cached is None:
        raise HTTPException(status_code=404, detail="Search cache not found")

    view = request.query_params.get("view", "all").lower()
    if view not in ("all", "fresh"):
        view = "all"

    jobs_dicts = [j.to_dict() for j in cached.jobs]
    db.upsert_jobs(jobs_dicts)   # ensure FK for scoring

    # Load viewed + dismissed + "new since expand" sets in one shot for
    # the whole cache. All three drive per-card flags AND the header stats.
    all_ids = [j["id"] for j in jobs_dicts]
    viewed_ids = db.get_viewed_ids(all_ids)
    dismissed_ids = db.get_dismissed_ids(all_ids)
    new_since_expand_ids = set(cached.last_expand_added_ids)

    resume = db.get_current_resume()
    api_key = resolve_api_key()

    ai_scores: dict[str, ScoreResult] = {}
    scoring_note: str = ""
    scoring_error: Optional[str] = None
    quota_exhausted: bool = False
    pending_score_count = 0

    if resume and jobs_dicts:
        all_ids = [j["id"] for j in jobs_dicts]
        from core.matching.semantic_score import _row_to_result
        cached_rows = db.get_cached_scores(int(resume["id"]), all_ids)
        for jid, row in cached_rows.items():
            ai_scores[jid] = _row_to_result(row)

        pending_score_count = len(jobs_dicts) - len(ai_scores)

        # Compose the header note. Real scoring status arrives later via
        # OOB swaps; here we describe the initial state.
        if not api_key:
            scoring_note = f"{len(ai_scores)} from cache · no Gemini key set"
        elif pending_score_count > 0:
            scoring_note = f"{len(ai_scores)} from cache · {pending_score_count} scoring…"
        else:
            scoring_note = f"all {len(ai_scores)} from cache"

    # Batch first_seen lookup for "New job" flag
    from datetime import datetime as _dt2
    now2 = _dt2.utcnow()
    first_seens = db.get_first_seen_batch([j["id"] for j in jobs_dicts])

    # Attach score + verdict + experience to each job for template convenience.
    # `_pending_score` distinguishes "genuinely un-scorable (no resume/key)"
    # from "scored async by the batch endpoint". The score_badge partial
    # renders a spinner when pending, "—" when unscorable.
    can_score_async = bool(resume and api_key)
    for j in jobs_dicts:
        r = ai_scores.get(j["id"])
        if r:
            j["_score"] = r.score
            j["_verdict"] = r.verdict
            j["_reasoning"] = r.reasoning
            j["_matched"] = r.matched
            j["_gaps"] = r.gaps
            j["_pending_score"] = False
        else:
            j["_score"] = 0
            j["_verdict"] = "none"
            j["_reasoning"] = ""
            j["_matched"] = []
            j["_gaps"] = []
            j["_pending_score"] = can_score_async
        j["_experience"] = _extract_experience(j.get("description", ""))
        j["_is_viewed"] = j["id"] in viewed_ids
        j["_is_dismissed"] = j["id"] in dismissed_ids
        j["_is_new_since_expand"] = j["id"] in new_since_expand_ids

        # "New" flag — first_seen within 48h
        j["_is_new"] = False
        fs = first_seens.get(j["id"])
        if fs:
            try:
                fs_dt = _dt2.fromisoformat(fs.rstrip("Z"))
                j["_is_new"] = (now2 - fs_dt).total_seconds() < 48 * 3600
            except Exception:
                pass

        app = db.get_application_by_job(j["id"])
        j["_app_status"] = app["status"] if app else None

    jobs_dicts.sort(key=lambda x: (x["_score"], x.get("date_posted") or ""), reverse=True)

    # Compact metadata array for Alpine — used by the client-side filter to
    # compute visible count reactively without a server round-trip.
    jobs_meta = [
        {
            "id": j["id"],
            "score": j["_score"],
            "french": int(
                bool(j.get("french_required"))
                or j.get("detected_language") == "fr"
            ),
            "remote": int(bool(j.get("is_remote"))),
            "is_new": int(bool(j.get("_is_new"))),
            "viewed": int(bool(j.get("_is_viewed"))),
            "dismissed": int(bool(j.get("_is_dismissed"))),
            "new_since_expand": int(bool(j.get("_is_new_since_expand"))),
        }
        for j in jobs_dicts
    ]

    # Aggregate counts for the fresh-view header. Computed server-side so
    # the template doesn't need Alpine reactivity for them.
    total_new_since_expand = len(new_since_expand_ids & set(all_ids))
    total_viewed = len(viewed_ids)
    total_unviewed_from_before = sum(
        1 for j in jobs_dicts
        if not j["_is_new_since_expand"] and not j["_is_viewed"]
    )

    return templates.TemplateResponse(
        request,
        "pages/jobs_results.html",
        {
            "active_tab": "jobs",
            "cache_key": cache_key,
            "label": cached.params_label or "Search",
            "fetched_at": cached.fetched_at,
            "jobs": jobs_dicts,
            "jobs_meta": jobs_meta,
            "total_jobs": len(jobs_dicts),
            "has_resume": bool(resume),
            "has_api_key": bool(api_key),
            "pending_score_count": pending_score_count,
            "scoring_note": scoring_note,
            "scoring_error": scoring_error,
            "quota_exhausted": quota_exhausted,
            "exhausted_models": exhausted_models(),
            "view": view,
            "is_fresh_view": view == "fresh",
            "total_new_since_expand": total_new_since_expand,
            "total_unviewed_from_before": total_unviewed_from_before,
            "total_viewed": total_viewed,
        },
    )


# ─────────────────────────────────────────────────────────────
# Lazy scoring — batch endpoint that streams scored fragments
# ─────────────────────────────────────────────────────────────

# How many pending jobs to score per batch call. Small enough that the
# first badges appear quickly, large enough that the chain doesn't
# thrash the server. Fits ~1s scoring on Gemini's Flash-Lite tier.
_SCORE_BATCH_SIZE = 5


@router.get("/jobs/results/{cache_key}/score-batch")
@limiter.limit("120/hour")
async def jobs_score_batch(request: Request, cache_key: str):
    """Score the next `_SCORE_BATCH_SIZE` pending jobs, return HTML fragments.

    Response body always ends with either:
      - a self-triggering `<div hx-get="…" hx-trigger="load">` when more
        pending jobs remain (chain continues on the client), OR
      - an empty terminal element when nothing left / no permission /
        quota exhausted (chain stops).

    Per-job scored badges + gaps are emitted as `hx-swap-oob="true"`
    fragments targeted at `#score-slot-{job_id}` and `#gaps-slot-{job_id}`
    already present in each rendered card.
    """
    if feature_flags.is_llm_disabled():
        # Kill switch — silently stop the chain. Header note already
        # shows scoring status; blowing up the results page over this
        # would be bad UX.
        return HTMLResponse("")

    cached = jobs_cache.load_by_key(cache_key)
    if cached is None or not cached.jobs:
        return HTMLResponse("")

    resume = db.get_current_resume()
    api_key = resolve_api_key()
    if not resume or not api_key:
        return HTMLResponse("")

    resume_id = int(resume["id"])
    all_ids = [j.id for j in cached.jobs]
    already_scored_ids = set(db.get_cached_scores(resume_id, all_ids).keys())

    # Pending = jobs still uncached against THIS resume. Order matches
    # the cached list order so the visual "spinner → badge" cascade
    # matches the render order.
    pending = [j.to_dict() for j in cached.jobs if j.id not in already_scored_ids]
    if not pending:
        return HTMLResponse("")

    batch = pending[:_SCORE_BATCH_SIZE]

    try:
        client = GeminiClient(api_key=api_key)
    except GeminiError:
        return HTMLResponse("")

    try:
        results = score_jobs_batch(
            resume_id=resume_id,
            resume_text=resume["parsed"].get("raw_text", ""),
            jobs=batch,
            client=client,
        )
    except QuotaExhaustedError:
        # Quota out for the day — stop chain. Already-scored jobs stay
        # visible; user will see partial results.
        return HTMLResponse("")
    except GeminiError:
        # Some transient issue — stop chain to avoid tight loops.
        return HTMLResponse("")

    # Build OOB swaps for each scored job in this batch + a tiny script
    # that pushes the new score into the client-side jobs_meta array so
    # Alpine's minScore filter re-evaluates. Without this, a card that
    # scores 82 stays hidden when the user has minScore ≥ 1 because
    # jobs_meta still says score=0 for it.
    fragments: list[str] = []
    scored_ids: list[tuple[str, int]] = []
    for j in batch:
        r = results.get(j["id"])
        if not r:
            continue
        j["_score"] = r.score
        j["_verdict"] = r.verdict
        j["_reasoning"] = r.reasoning
        j["_matched"] = r.matched
        j["_gaps"] = r.gaps
        j["_pending_score"] = False
        fragments.append(templates.env.get_template("partials/score_badge.html")
                         .render(job=j, oob=True))
        fragments.append(templates.env.get_template("partials/job_gaps.html")
                         .render(job=j, oob=True))
        scored_ids.append((j["id"], int(r.score)))
    if scored_ids:
        pushes = "".join(
            f'window.__jobotUpdateScore && window.__jobotUpdateScore("{jid}", {score});'
            for jid, score in scored_ids
        )
        fragments.append(f'<script>{pushes}</script>')

    # Chain continuation: are there more pending after this batch?
    remaining_after = len(pending) - len(batch)
    if remaining_after > 0:
        fragments.append(
            f'<div hx-get="/jobs/results/{cache_key}/score-batch"'
            f' hx-trigger="load delay:200ms"'
            f' hx-swap="outerHTML"></div>'
        )

    return HTMLResponse("\n".join(fragments))


@router.post("/jobs/run/multi")
@limiter.limit("30/hour")
async def jobs_run_multi(
    request: Request,
    queries: list[str] = Form(...),
    location: str = Form("Ottawa, Ontario, Canada"),
):
    """Airline-style multi-search: 1-3 fresh queries share one location, run
    sequentially with cooldown, results merged into a single cache entry when
    N > 1. Called from the redesigned landing search form.

    - 1 query  → behaves like /jobs/run: cache single result, redirect
    - 2-3      → behaves like /jobs/run/bulk: merge into one "Multi: A + B + C"
                 cache entry, redirect to combined results
    """
    if feature_flags.is_scrape_disabled():
        return _scrape_disabled_response()
    queries = [q.strip() for q in queries if q and q.strip()]
    if not queries:
        return HTMLResponse(
            '<div class="rounded-lg p-3 my-3 text-sm" style="background: hsl(35 85% 96%); border: 1px solid hsl(35 70% 82%);">'
            'Enter at least one job title.</div>',
            status_code=200,
        )
    if len(queries) > 3:
        return HTMLResponse(
            '<div class="text-error text-sm p-3">Max 3 queries per run.</div>',
            status_code=200,
        )
    location = (location or "Ottawa, Ontario, Canada").strip()

    # Single query: same as /jobs/run — cache short-circuit + redirect
    if len(queries) == 1:
        params = JobSearchParams(query=queries[0], location=location)
        cached = jobs_cache.load(params)
        if cached and cached.jobs:
            age = jobs_cache.age_seconds(cached.fetched_at)
            if age is not None and age < _CACHE_SHORT_CIRCUIT_SECONDS:
                return Response(
                    status_code=200,
                    headers={"HX-Redirect": f"/jobs/results/{params.cache_key()}"},
                )
        try:
            jobs = search_jobs(params)
        except RuntimeError as exc:
            return HTMLResponse(
                f'<div class="text-error text-sm p-3">Search failed: {exc}</div>',
                status_code=200,
            )
        if not jobs:
            return HTMLResponse(
                f'<div class="rounded-lg p-4 my-3 text-sm" style="background: hsl(35 85% 96%); border: 1px solid hsl(35 70% 82%);">'
                f'<div class="font-semibold">No results for "{queries[0]}"</div>'
                f'<div class="text-body-muted mt-1">Try broader terms, a nearby city, or a longer time window.</div>'
                f'</div>',
                status_code=200,
            )
        db.upsert_jobs([j.to_dict() for j in jobs])
        jobs_cache.save(params, jobs, label=queries[0])
        return Response(status_code=200, headers={"HX-Redirect": f"/jobs/results/{params.cache_key()}"})

    # Multi-query: fire off as a background thread so the browser doesn't hang.
    # User gets redirected to a dedicated loading page that polls status.
    # Task state is durable (SQLite) — survives Fly machine cycling so a user
    # who closes the tab and returns can still see the completion.
    task_id = str(uuid.uuid4())[:8]
    search_tasks.create(
        task_id,
        kind="multi",
        payload={
            "queries": queries,
            "location": location,
            "message": "Starting…",
        },
    )
    thread = threading.Thread(
        target=_run_multi_background,
        args=(task_id, queries, location),
        daemon=True,
    )
    thread.start()

    return Response(
        status_code=200,
        headers={"HX-Redirect": f"/jobs/loading/{task_id}"},
    )


def _run_multi_background(task_id: str, queries: list[str], location: str) -> None:
    """Worker for multi-query bulk runs. Runs sequential scrapes with an
    8s cooldown, merges results into ONE cache entry, updates task status
    so the loading page can poll progress.

    Task state lives in SQLite via `core.jobs.tasks` — survives process
    restarts. The thread itself does not; a stale-running row will be
    swept to `failed` by `tasks._sweep()` when the next task is created."""
    if search_tasks.get(task_id) is None:
        return

    search_tasks.update(task_id, status="running")
    merged: dict[str, Job] = {}
    successes: list[str] = []
    failures: list[str] = []

    for i, q in enumerate(queries):
        if i > 0:
            search_tasks.update(task_id, message=f"Cooling down {_SCRAPE_COOLDOWN_S}s before '{q}'…")
            time.sleep(_SCRAPE_COOLDOWN_S)
        search_tasks.update(task_id, message=f"Searching for '{q}' ({i + 1}/{len(queries)})…")
        try:
            params = JobSearchParams(query=q, location=location)
            js = search_jobs(params)
            for j in js:
                if j.id not in merged:
                    merged[j.id] = j
            successes.append(q)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{q}: {exc}")

    if not merged:
        search_tasks.mark_failed(
            task_id,
            "No results from any of the searches. " + (
                f"Errors: {', '.join(failures)}" if failures else ""
            ),
        )
        return

    search_tasks.update(task_id, message="Saving and organizing results…")
    bulk_params = JobSearchParams(query=f"multi_{int(time.time())}", location=location)
    bulk_label = "Multi: " + " + ".join(successes)
    merged_list = list(merged.values())
    # DB upsert must precede the cache save — the cache file now stores
    # only pointers into the jobs table.
    db.upsert_jobs([j.to_dict() for j in merged_list])
    jobs_cache.save(bulk_params, merged_list, label=bulk_label)

    events.track(
        events.SEARCH_BROAD,
        queries=successes,
        result_count=len(merged_list),
        failure_count=len(failures),
    )

    search_tasks.mark_done(
        task_id,
        result_url=f"/jobs/results/{bulk_params.cache_key()}",
        message=f"Done — {len(merged_list)} jobs across {len(successes)} searches.",
    )


@router.get("/jobs/loading/{task_id}")
async def jobs_loading_page(request: Request, task_id: str):
    """Full-page loader for background multi-searches. Polls task status
    every 2s. When done, redirects to results. Non-blocking for the user."""
    task = search_tasks.get(task_id)
    if task is None:
        return Response(status_code=404, content="Task not found — probably completed already.")
    return templates.TemplateResponse(
        request,
        "pages/jobs_loading.html",
        {"active_tab": "jobs", "task_id": task_id, "task": task},
    )


@router.get("/jobs/loading/{task_id}/status")
async def jobs_loading_status(request: Request, task_id: str):
    """Polled every 2s by the loading page for both multi-search and
    expand tasks. Returns HTML fragment for the running/failed states;
    on done, returns HX-Redirect so HTMX drives the browser to the
    task's result URL (results page or ?view=fresh for expand)."""
    task = search_tasks.get(task_id)
    if task is None:
        return HTMLResponse('<div class="text-error">Task not found.</div>', status_code=200)
    if task["status"] == "done":
        return Response(status_code=200, headers={"HX-Redirect": task.get("result_url") or "/jobs"})
    if task["status"] == "failed":
        return HTMLResponse(
            f'<div class="text-error text-sm">{task.get("error", "Unknown error")}</div>',
            status_code=200,
        )
    # Still running
    message = task.get("message", "Working…")
    try:
        started = datetime.fromisoformat((task.get("started_at") or "").rstrip("Z"))
        elapsed = int((datetime.utcnow() - started).total_seconds())
    except (TypeError, ValueError):
        elapsed = 0
    return HTMLResponse(
        f'<div class="text-body-muted">{message} <span class="text-base-content/40 ml-1">({elapsed}s)</span></div>',
        status_code=200,
    )


@router.post("/jobs/run/bulk")
async def jobs_run_bulk(search_ids: list[str] = Form(...)):
    """Run multiple searches sequentially with a small cooldown between each
    to avoid tripping LinkedIn/Indeed rate limits. Max 3 per bulk request.

    Grouping: results from all sub-searches are merged into ONE cache entry
    labeled "Bulk: A + B + C". Recent list shows a single row per bulk run;
    clicking it opens the results page with everything visible together.

    `search_ids` values are prefixed to disambiguate:
        - "template:<name>"   → look up in SAVED_SEARCHES
        - "cached:<cache_key>" → recover params from the cache file
    """
    if not search_ids:
        return HTMLResponse(
            '<div class="text-error text-sm p-3">Pick at least one search.</div>',
            status_code=200,
        )
    if len(search_ids) > 3:
        return HTMLResponse(
            '<div class="text-error text-sm p-3">Max 3 searches per bulk run.</div>',
            status_code=200,
        )

    COOLDOWN_S = 8   # gentle spacing between scrapes to avoid rate-limits

    merged_jobs: dict[str, "Job"] = {}   # dedupe by job.id across sub-searches
    sub_labels: list[str] = []
    failures: list[str] = []
    last_location = "Ottawa, Ontario, Canada"

    for i, sid in enumerate(search_ids):
        # Resolve the search identifier to params + label
        if sid.startswith("template:"):
            raw = sid[len("template:"):]
            row = None
            try:
                row = db.get_saved_search(int(raw))
            except (ValueError, TypeError):
                # Backward-compat: allow name lookup
                for s in db.list_saved_searches():
                    if s["name"] == raw:
                        row = s
                        break
            if not row:
                failures.append(raw)
                continue
            params = JobSearchParams(
                query=row["query"], location=row["location"],
                distance=row["distance"], hours_old=row["hours_old"],
                results_wanted=row["results_wanted"],
            )
            label = row["name"]
        elif sid.startswith("cached:"):
            cache_key = sid[len("cached:"):]
            cached_meta = _load_cache_params(cache_key)
            if not cached_meta:
                failures.append(cache_key)
                continue
            params = JobSearchParams(**cached_meta["params"])
            label = cached_meta.get("params_label") or params.query
        else:
            failures.append(sid)
            continue

        sub_labels.append(label)
        last_location = params.location

        if i > 0:
            time.sleep(COOLDOWN_S)

        try:
            jobs = search_jobs(params)
            for j in jobs:
                # First occurrence wins — order matches user's picker order
                if j.id not in merged_jobs:
                    merged_jobs[j.id] = j
        except Exception:
            failures.append(label)

    if not merged_jobs:
        return HTMLResponse(
            f'''<div class="rounded-lg p-4 my-3 text-sm"
                     style="background: hsl(35 85% 96%); border: 1px solid hsl(35 70% 82%);">
                  <div class="font-semibold">No results from any of the searches.</div>
                  <div class="text-body-muted mt-1">Failed: {", ".join(failures) or "all"}.</div>
                </div>''',
            status_code=200,
        )

    # Synthetic params — the query is timestamp-unique so bulk runs each get
    # their own cache_key (won't overwrite previous bulk runs).
    bulk_query = f"bulk_{int(time.time())}"
    bulk_params = JobSearchParams(query=bulk_query, location=last_location)
    bulk_label = "Bulk: " + " + ".join(sub_labels)

    merged_list = list(merged_jobs.values())
    # DB upsert precedes cache save — pointer files reference jobs by id.
    db.upsert_jobs([j.to_dict() for j in merged_list])
    jobs_cache.save(bulk_params, merged_list, label=bulk_label)

    return Response(
        status_code=200,
        headers={"HX-Redirect": f"/jobs/results/{bulk_params.cache_key()}"},
    )


@router.post("/jobs/results/{cache_key}/expand")
@limiter.limit("10/hour")
async def jobs_expand(request: Request, cache_key: str):
    """Broaden an existing search by running a deeper same-query scrape,
    merging new jobs into the same cache entry.

    Triggered by a plain <form target="_blank"> on the results page so
    it opens in a NEW TAB. Returns a 303 to a loading page that polls
    the background task and — when done — HX-Redirects to
    /jobs/results/{key}?view=fresh (the "just what came from this
    expand" view). The user's original tab is never touched.

    303 (See Other) converts the POST to a GET on the loading URL so a
    browser refresh doesn't re-fire the expand task.
    """
    if feature_flags.is_scrape_disabled():
        return _expand_error_page(feature_flags.scrape_disabled_message(),
                                  status=feature_flags.KILL_SWITCH_STATUS)
    cached = jobs_cache.load_by_key(cache_key)
    if cached is None:
        return _expand_error_page("Search cache not found — reload the results page and try again.",
                                  status=404)

    cached_meta = _load_cache_params(cache_key)
    if not cached_meta or not cached_meta.get("params"):
        return _expand_error_page("Cache missing params — can't expand.", status=400)
    params = JobSearchParams(**cached_meta["params"])
    original_label = cached_meta.get("params_label") or params.query

    task_id = str(uuid.uuid4())[:8]
    search_tasks.create(
        task_id,
        kind="expand",
        payload={
            "cache_key": cache_key,
            "query": params.query,
            "location": params.location,
            "message": "Searching deeper…",
        },
    )
    thread = threading.Thread(
        target=_run_expand_background,
        args=(task_id, cache_key, params, original_label),
        daemon=True,
    )
    thread.start()

    return Response(
        status_code=303,
        headers={"Location": f"/jobs/loading/{task_id}"},
    )


def _expand_error_page(message: str, *, status: int) -> HTMLResponse:
    """Standalone HTML error for the /expand tab-opening flow. Since the
    Expand button opens a new tab, an error can't be an HTMX fragment
    swapped into the results page — it has to render as a page in the
    new tab."""
    return HTMLResponse(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Expand — Jobot</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:520px;margin:6rem auto;padding:0 1rem;color:#333}}
h1{{font-size:1.1rem;color:#a44}} .btn{{display:inline-block;margin-top:1.5rem;padding:.5rem .9rem;
border:1px solid #999;border-radius:.4rem;text-decoration:none;color:#333}}</style>
</head><body>
<h1>Couldn't start the expansion</h1>
<p>{message}</p>
<a class="btn" href="javascript:window.close()">Close this tab</a>
</body></html>""",
        status_code=status,
    )


def _run_expand_background(
    task_id: str,
    cache_key: str,
    original_params: JobSearchParams,
    original_label: str,
) -> None:
    """Worker for /jobs/results/{cache_key}/expand.

    Single deeper scrape on the same query, then merge back into the
    cache entry. This is the "give me another 30 of the same job"
    experience — no LLM, no adjacent-title variants (dropped 2026-08-18
    based on user feedback that the multi-scrape flow was too slow and
    the extra titles weren't what they wanted).

    Params get widened all three ways: `results_wanted` bumped (2×,
    floor 60) so jobspy pages deeper, `hours_old` doubled so older
    postings become visible, `distance` doubled so nearby metros come
    in. Duplicates against what's already in the cache are dropped so
    the "N new jobs" count is honest.

    Runtime: ~15-30s depending on jobspy latency. No cooldowns (only
    one scrape)."""
    already_ids = _existing_cache_job_ids(cache_key)

    search_tasks.update(task_id, message="Searching deeper…")
    deeper_params = JobSearchParams(
        query=original_params.query,
        location=original_params.location,
        distance=max(original_params.distance * 2, original_params.distance),
        sites=list(original_params.sites),
        hours_old=max(original_params.hours_old * 2, original_params.hours_old),
        results_wanted=max(original_params.results_wanted * 2, 60),
        is_remote=original_params.is_remote,
        country_indeed=original_params.country_indeed,
        linkedin_fetch_description=original_params.linkedin_fetch_description,
    )
    try:
        scraped = search_jobs(deeper_params)
    except Exception as exc:  # noqa: BLE001
        search_tasks.mark_failed(task_id, f"Deeper scrape failed: {exc}")
        return

    all_new: dict[str, Job] = {}
    for j in scraped:
        if j.id not in all_new and j.id not in already_ids:
            all_new[j.id] = j

    if not all_new:
        # No new jobs to chip — send the user to the fresh view anyway,
        # where the "0 new since expand" header + "unviewed from before"
        # count still gives them something actionable.
        search_tasks.mark_done(
            task_id,
            result_url=f"/jobs/results/{cache_key}?view=fresh",
            message=f"No new jobs found beyond your current {len(already_ids)}.",
        )
        return

    search_tasks.update(task_id, message="Merging into results…")
    new_jobs = list(all_new.values())
    db.upsert_jobs([j.to_dict() for j in new_jobs])

    # Label swap: append "(expanded)" once, don't stack.
    new_label = original_label if "(expanded)" in original_label else f"{original_label} (expanded)"
    merged = jobs_cache.merge_into(cache_key, new_jobs, new_label=new_label)
    if merged is None:
        search_tasks.mark_failed(task_id, "Cache entry disappeared during expand.")
        return

    events.track(
        events.SEARCH_BROAD,
        queries=[original_params.query],
        result_count=len(merged.jobs),
        expand=True,
        failure_count=0,
    )

    # Fresh view: filters to jobs added by this expand pass +
    # jobs the user hasn't viewed yet from before. Keeps them out of the
    # already-worked-through pile so the new tab feels like turning a
    # page, not re-reading the previous one.
    search_tasks.mark_done(
        task_id,
        result_url=f"/jobs/results/{cache_key}?view=fresh",
        message=f"{len(new_jobs)} new jobs added ({len(merged.jobs)} total).",
    )


def _existing_cache_job_ids(cache_key: str) -> set[str]:
    """Snapshot of what's already in the cache entry, so a deeper-pass
    result that's identical to what the user's already seeing doesn't
    count as 'new' in the message we show them."""
    cached = jobs_cache.load_by_key(cache_key)
    if not cached:
        return set()
    return {j.id for j in cached.jobs}


@router.post("/jobs/refresh/{cache_key}")
async def jobs_refresh(cache_key: str):
    """Re-run a cached search from scratch — bypasses the disk cache.
    Same params as the original, so the cache key stays the same. Returns
    HX-Redirect back to the results page (which will re-render + re-score
    if needed against any new jobs)."""
    if feature_flags.is_scrape_disabled():
        return _scrape_disabled_response()
    cached_meta = _load_cache_params(cache_key)
    if not cached_meta:
        raise HTTPException(status_code=404, detail="Cache not found")

    params = JobSearchParams(**cached_meta["params"])
    label = cached_meta.get("params_label") or params.query

    try:
        jobs = search_jobs(params)
    except RuntimeError as exc:
        return HTMLResponse(
            f'<div class="text-error text-sm p-4">Refresh failed: {exc}</div>',
            status_code=200,
        )

    # DB upsert precedes cache save — pointer files reference jobs by id.
    db.upsert_jobs([j.to_dict() for j in jobs])
    jobs_cache.save(params, jobs, label=label)

    return Response(status_code=200, headers={"HX-Redirect": f"/jobs/results/{cache_key}"})


# ─────────────────────────────────────────────────────────────
# Import a specific job from a URL (or manual paste)
# ─────────────────────────────────────────────────────────────

@router.post("/jobs/from-url")
@limiter.limit("20/hour")
async def jobs_from_url(
    request: Request,
    job_url: str = Form(""),
    manual_text: str = Form(""),
):
    """Import a single job from either a URL or a manually-pasted description.

    Flow:
        1. If manual_text present → extract from it directly (URL optional)
        2. Else → fetch URL, extract from page HTML
        3. If URL fetch fails → return the manual-paste form fragment (with
           the URL pre-filled) so the user can paste the JD by hand
        4. Persist job + score → redirect to /jobs/analyzed/{job_id}
    """
    job_url = (job_url or "").strip()
    manual_text = (manual_text or "").strip()

    if not job_url and not manual_text:
        return HTMLResponse(
            '<div class="text-error text-sm p-3">Paste a URL or a job description first.</div>',
            status_code=200,
        )

    api_key = resolve_api_key()
    if not api_key:
        return HTMLResponse(
            '<div class="rounded-lg p-3 text-sm" style="background: hsl(35 85% 96%); border: 1px solid hsl(35 70% 82%);">'
            'This needs a Gemini API key. Add one on <a href="/profile" class="underline">Profile</a>.</div>',
            status_code=200,
        )

    client = GeminiClient(api_key=api_key)

    # 1) Manual paste takes precedence — user has already decided to bypass fetch
    if manual_text:
        try:
            job_dict = extract_job_from_text(manual_text, source_url=job_url, client=client)
        except UrlExtractError as exc:
            return HTMLResponse(
                f'<div class="rounded-lg p-3 text-sm" style="background: hsl(0 60% 96%); border: 1px solid hsl(0 50% 88%);">{exc}</div>',
                status_code=200,
            )
    else:
        # 2) URL-only path: try fetching. On failure, show the manual-paste form.
        try:
            page_text = fetch_page_text(job_url)
        except UrlFetchError as exc:
            return templates.TemplateResponse(
                request,
                "partials/from_url_manual.html",
                {"job_url": job_url, "reason": str(exc)},
            )
        try:
            job_dict = extract_job_from_text(page_text, source_url=job_url, client=client)
        except UrlExtractError as exc:
            return templates.TemplateResponse(
                request,
                "partials/from_url_manual.html",
                {"job_url": job_url, "reason": str(exc)},
            )

    # 3) Persist to jobs table so scoring + tailoring see it
    db.upsert_jobs([job_dict])
    events.track(
        events.SEARCH_URL_IMPORT,
        job_id=job_dict["id"],
        source=job_dict.get("site", ""),
        used_manual=bool(manual_text),
    )

    # 4) Score against current resume, if we have one
    resume = db.get_current_resume()
    if resume:
        try:
            result = score_single_no_cache(
                resume_text=resume["parsed"].get("raw_text", ""),
                job=job_dict,
                client=client,
            )
            if result is not None:
                db.save_scores(int(resume["id"]), [result.to_dict()])
        except Exception:
            # Non-fatal — the analyzed page can render without a score
            pass

    return Response(
        status_code=200,
        headers={"HX-Redirect": f"/jobs/analyzed/{job_dict['id']}"},
    )


@router.get("/jobs/analyzed/{job_id}")
async def jobs_analyzed(request: Request, job_id: str):
    """Full-page single-job view for a URL-imported job. Uses the existing
    job_detail partial + tailor drawer plumbing — no new UI needed."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    resume = db.get_current_resume()
    ai = None
    if resume:
        cached = db.get_cached_scores(int(resume["id"]), [job_id])
        row = cached.get(job_id)
        if row:
            import json as _json
            ai = {
                "score": row["score"],
                "verdict": row["verdict"],
                "reasoning": row["reasoning"],
                "matched": _json.loads(row["matched_json"]),
                "gaps": _json.loads(row["gaps_json"]),
            }

    app = db.get_application_by_job(job_id)
    job["_app_status"] = app["status"] if app else None

    return templates.TemplateResponse(
        request,
        "pages/jobs_analyzed.html",
        {
            "active_tab": "jobs",
            "job": job,
            "ai": ai,
            "has_resume": bool(resume),
        },
    )


# ─────────────────────────────────────────────────────────────
# Save-as-interested (HTMX action, returns fragment)
# ─────────────────────────────────────────────────────────────

@router.get("/jobs/detail/{job_id}")
@limiter.limit("200/hour")
async def jobs_detail(request: Request, job_id: str):
    """Job detail fragment for the split-viewport right pane. Loaded by
    HTMX when a card is clicked on the results page — and by the mobile
    "Show description" button (via `hx-select`) so descriptions are no
    longer inlined into the results HTML.

    Rate-limited per IP so bulk scrapers can't loop the whole cache
    through this endpoint. 200/hour comfortably covers real browsing
    (a heavy session opens ~30-60 cards)."""
    job = db.get_job(job_id)
    if not job:
        return HTMLResponse(
            '<div class="text-body-muted text-sm p-4">Job not found — was it deleted?</div>',
            status_code=200,
        )

    resume = db.get_current_resume()
    ai = None
    if resume:
        cached = db.get_cached_scores(int(resume["id"]), [job_id])
        row = cached.get(job_id)
        if row:
            import json as _json
            ai = {
                "score": row["score"],
                "verdict": row["verdict"],
                "reasoning": row["reasoning"],
                "matched": _json.loads(row["matched_json"]),
                "gaps": _json.loads(row["gaps_json"]),
            }

    app = db.get_application_by_job(job_id)
    job["_app_status"] = app["status"] if app else None

    events.track(
        events.JOB_DETAIL_VIEWED,
        job_id=job_id,
        score=(ai or {}).get("score"),
        verdict=(ai or {}).get("verdict"),
    )

    return templates.TemplateResponse(
        request,
        "partials/job_detail.html",
        {"job": job, "ai": ai},
    )


@router.post("/jobs/dismiss/{job_id}")
@limiter.limit("300/hour")
async def jobs_dismiss(request: Request, job_id: str):
    """Mark a job as dismissed ("not interested"). Fired by the
    swipe-left gesture on mobile cards. Idempotent, 204 no-content."""
    if not db.get_job(job_id):
        return Response(status_code=404)
    db.mark_dismissed(job_id)
    events.track("job.dismissed", job_id=job_id)
    return Response(status_code=204)


@router.post("/jobs/undismiss/{job_id}")
@limiter.limit("300/hour")
async def jobs_undismiss(request: Request, job_id: str):
    """Undo a dismissal. Wired to the "Undo" button in the swipe toast
    (planned follow-up) and to a manual "restore" affordance in the
    filter panel."""
    if not db.get_job(job_id):
        return Response(status_code=404)
    db.unmark_dismissed(job_id)
    return Response(status_code=204)


@router.post("/jobs/viewed/{job_id}")
@limiter.limit("600/hour")
async def jobs_mark_viewed(request: Request, job_id: str):
    """Mark a job as viewed. Fired by the client-side 3-second
    detail-pane timer — the "I actually read this" signal, not an
    accidental click.

    Idempotent (INSERT ... ON CONFLICT DO UPDATE), so repeat POSTs from a
    stale tab or duplicate timer are harmless. Returns 204 — nothing to
    render, the client already knows what changed.

    Rate limit generous (10/min) because a heavy browsing session opens
    dozens of cards; the endpoint is cheap (one UPSERT).
    """
    if not db.get_job(job_id):
        return Response(status_code=404)
    db.mark_viewed(job_id)
    return Response(status_code=204)


@router.post("/jobs/save/{job_id}")
async def jobs_save(request: Request, job_id: str, status: str = Form("interested")):
    if status not in db.VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    resume = db.get_current_resume()
    app_id = db.create_or_get_application(
        job_id, status=status,
        resume_id=int(resume["id"]) if resume else None,
    )
    existing = db.get_application(app_id)
    if existing and existing["status"] != status:
        db.update_application(app_id, status=status)

    events.track(events.JOB_SAVED, job_id=job_id, status=status)

    return templates.TemplateResponse(
        request,
        "partials/save_action.html",
        {"job_id": job_id, "current_status": status},
    )


@router.post("/jobs/unsave/{job_id}")
async def jobs_unsave(request: Request, job_id: str):
    """Remove a job from Applications ONLY if it's still in 'interested' state.
    If the user has already advanced the status (applied/interviewing/etc),
    we don't blow away the data — they'd need to delete from the Applications
    tab explicitly."""
    app = db.get_application_by_job(job_id)
    if app and app["status"] == "interested":
        db.delete_application(app["id"])
        events.track(events.JOB_UNSAVED, job_id=job_id)
    return templates.TemplateResponse(
        request,
        "partials/save_action.html",
        {"job_id": job_id, "current_status": None if (app and app["status"] == "interested") else (app["status"] if app else None)},
    )


# ─────────────────────────────────────────────────────────────
# Tailor — panel + generate + save + download
# ─────────────────────────────────────────────────────────────

@router.get("/jobs/tailor/{job_id}")
async def jobs_tailor_panel(request: Request, job_id: str):
    """Return the tailor drawer content: past-runs list + generate form."""
    job = db.get_job(job_id)
    if not job:
        # Return a 200 with a visible error so HTMX swaps it into the open
        # drawer — otherwise a raw 404 makes the drawer stay silently empty
        # and the user thinks "nothing happened".
        return HTMLResponse(
            '<div class="rounded-lg p-4 text-sm" style="background: hsl(0 60% 96%); '
            'border: 1px solid hsl(0 50% 88%);">'
            f'<div class="font-semibold">Couldn\'t open tailor</div>'
            f'<div class="text-body-muted mt-1">Job <code>{job_id}</code> not found in the database. '
            'Try re-importing it — the ID may have changed.</div></div>',
            status_code=200,
        )

    resume = db.get_current_resume()
    api_key = resolve_api_key()

    return templates.TemplateResponse(
        request,
        "partials/tailor_panel.html",
        {
            "job": job,
            "has_resume": bool(resume),
            "has_api_key": bool(api_key),
            "levels": [
                ("conservative", "Conservative", "Light edits. Never adds skills."),
                ("balanced", "Balanced", "Real tailoring. Drops irrelevant bullets."),
                ("aggressive", "Aggressive", "Max keyword alignment using JD vocab."),
            ],
            "default_level": "balanced",
            "runs": list_runs(job_id),   # past tailor runs, newest first
        },
    )


@router.post("/jobs/tailor/{job_id}")
@limiter.limit("10/hour;40/day")
async def jobs_tailor_generate(
    request: Request,
    job_id: str,
    level: Level = Form("balanced"),
):
    if feature_flags.is_tailor_disabled():
        return _tailor_disabled_response()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    resume = db.get_current_resume()
    api_key = resolve_api_key()
    if not resume or not api_key:
        return HTMLResponse(
            '<div class="alert alert-warning text-sm">Need a resume + Gemini key. '
            'Add both on the Profile tab.</div>',
            status_code=200,
        )

    try:
        client = GeminiClient(api_key=api_key)
        tailored = rewrite_resume(
            resume["parsed"],
            job.get("description") or "",
            level,
            client,
        )
    except GeminiError as exc:
        return HTMLResponse(
            f'<div class="alert alert-error text-sm">Tailoring failed: {exc}</div>',
            status_code=200,
        )

    # Re-score the tailored resume against this job so we can show the
    # before/after match improvement — the "you moved from Workable to Strong
    # fit" payoff. Uses no-cache single-shot scoring (we don't want tailored
    # resumes in the score cache, which is keyed on the original resume_id).
    # If the before-score is missing (job wasn't scored yet) or the after-score
    # fails (quota / model error), we degrade gracefully: no match block shown.
    resume_id = int(resume["id"])
    before_row = db.get_cached_scores(resume_id, [job_id]).get(job_id)
    after_result = score_single_no_cache(
        resume_text=tailored_to_text(tailored),
        job=job,
        client=client,
    )
    if after_result is not None:
        after = {"score": after_result.score, "verdict": after_result.verdict}
        if before_row:
            before = {"score": int(before_row["score"]), "verdict": before_row["verdict"]}
            delta = after["score"] - before["score"]

            # Auto-fallback (1A): if the tailoring didn't beat the original,
            # revert the resume SECTIONS to the original (LLM-non-determinism
            # or over-aggressive editing means occasional negative deltas that
            # ship a worse resume). We KEEP the cover letter though — that's
            # always specific-to-role value the original didn't have.
            # The template surfaces this via `fallback_to_original`.
            if delta <= 0:
                original_sections = (resume.get("parsed") or {}).get("sections") or {}
                # Stash the discarded LLM version in case we ever add a
                # "Use tailored anyway" button — cheap and non-breaking.
                tailored["_tailored_sections_rejected"] = tailored.get("sections") or {}
                tailored["sections"] = original_sections
                tailored["fallback_to_original"] = True
                tailored["tailoring_notes"] = (
                    "Your resume already scored well for this role — we kept "
                    "it as-is. The cover letter below is still tailored to "
                    "this specific posting."
                )
                # Overwrite the change summary so the meta line doesn't lie
                # about a % change that no longer applies.
                tailored["tailoring_change"] = {
                    "overall_pct": 0,
                    "per_section": [],
                    "one_liner": "kept original resume",
                }
                # After == before now (we're using the original)
                after = before
                delta = 0

            tailored["tailoring_match"] = {
                "before": before,
                "after": after,
                "delta": delta,
                "verdict_jumped": before["verdict"] != after["verdict"],
            }
        else:
            # No baseline — still worth showing the tailored score so the user
            # sees what their tailored version scored, just without a comparison.
            tailored["tailoring_match"] = {
                "before": None,
                "after": after,
                "delta": None,
                "verdict_jumped": False,
            }

    # Persist to history — user can revisit past runs without re-generating
    run_index = record_tailor(job_id, tailored)

    _match = tailored.get("tailoring_match") or {}
    _before = _match.get("before") or {}
    _after = _match.get("after") or {}
    events.track(
        events.TAILOR_GENERATED,
        job_id=job_id,
        level=str(level),
        before_verdict=_before.get("verdict"),
        after_verdict=_after.get("verdict"),
        before_score=_before.get("score"),
        after_score=_after.get("score"),
        delta=_match.get("delta"),
        verdict_jumped=bool(_match.get("verdict_jumped")),
        change_pct=(tailored.get("tailoring_change") or {}).get("overall_pct"),
        fallback_to_original=bool(tailored.get("fallback_to_original")),
    )

    return templates.TemplateResponse(
        request,
        "partials/tailor_result.html",
        {
            "job_id": job_id,
            "tailored": tailored,
            "job": job,
            "run_index": run_index,
            # Include the updated runs list so tailor_result.html can OOB-swap
            # it into #tailor-runs-{job.id} — no page reload needed to see the
            # new entry.
            "runs": list_runs(job_id),
        },
    )


@router.get("/jobs/tailor/{job_id}/view/{run_index}")
async def jobs_tailor_view(request: Request, job_id: str, run_index: int):
    """Render a specific past run (from history) into the drawer result area
    without hitting Gemini again."""
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    tailored = get_tailored(job_id, run_index)
    if tailored is None:
        return HTMLResponse(
            '<div class="text-error text-sm">Run not found (may have been evicted).</div>',
            status_code=200,
        )
    return templates.TemplateResponse(
        request,
        "partials/tailor_result.html",
        {"job_id": job_id, "tailored": tailored, "job": job, "run_index": run_index},
    )


@router.post("/jobs/tailor/{job_id}/save")
async def jobs_tailor_save(request: Request, job_id: str, status: str = Form("interested")):
    if status not in db.VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")

    tailored = get_tailored(job_id)  # latest run
    if not tailored:
        return HTMLResponse(
            '<div class="text-error text-sm">Nothing to save — generate first.</div>',
            status_code=200,
        )

    import json as _json
    resume = db.get_current_resume()
    resume_id = int(resume["id"]) if resume else None

    app_id = db.create_or_get_application(job_id, status=status, resume_id=resume_id)
    db.update_application(
        app_id,
        status=status,
        resume_id=resume_id,
        tailoring_level=tailored.get("tailoring_level"),
        tailored_resume_json=_json.dumps(
            {"sections": tailored.get("sections", {})}, ensure_ascii=False,
        ),
        tailored_cover_letter=tailored.get("cover_letter") or "",
    )

    label = {"interested": "Saved as interested",
             "applied": "Marked applied"}.get(status, f"Saved as {status}")
    return HTMLResponse(
        f'<div class="pill" style="background: hsl(155 40% 92%); '
        f'color: hsl(165 60% 25%); border-color: hsl(155 40% 82%);">'
        f'<span class="pill-dot live"></span>{label}</div>',
        status_code=200,
    )


@router.get("/jobs/tailor/{job_id}/download")
async def jobs_tailor_download(job_id: str, run: int = -1):
    """Download the tailored DOCX. `run` selects a past run; default is latest.

    Filename convention: `{name}_{company}_{position}_{level}.docx`, sanitized
    to alphanumerics + underscores. Falls back gracefully if any piece is missing.
    """
    tailored = get_tailored(job_id, run)
    if not tailored:
        raise HTTPException(status_code=404, detail="Nothing tailored yet")

    docx_bytes = render_docx(tailored)
    level = tailored.get("tailoring_level", "tailored")

    # Build a friendly filename from the components we have on hand.
    job = db.get_job(job_id) or {}
    name_part = slugify(tailored.get("contact", {}).get("name", "")) or "resume"
    company_part = slugify(job.get("company", ""))
    position_part = slugify(job.get("title", ""))

    pieces = [name_part]
    if company_part:
        pieces.append(company_part)
    if position_part:
        pieces.append(position_part)
    pieces.append(slugify(level))
    filename = "_".join(pieces) + ".docx"

    events.track(events.TAILOR_RESUME_DOWNLOAD, job_id=job_id, level=str(level), run=run)

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/jobs/tailor/{job_id}/cover-letter")
async def jobs_tailor_cover_letter_download(job_id: str, run: int = -1):
    """Download the tailored cover letter as a DOCX. `run` selects a past
    run; default is latest. Styling mirrors the resume for a cohesive package.

    Filename: `{name}_{company}_{position}_cover-letter.docx`.
    """
    tailored = get_tailored(job_id, run)
    if not tailored:
        raise HTTPException(status_code=404, detail="Nothing tailored yet")

    cover_letter = (tailored.get("cover_letter") or "").strip()
    if not cover_letter:
        raise HTTPException(status_code=404, detail="This run has no cover letter")

    job = db.get_job(job_id) or {}

    # Use the current-resume contact from DB as source of truth for the name
    # — the tailoring pass sometimes drops it, and the parsed dict on disk is
    # authoritative for identity fields anyway.
    resume_row = db.get_current_resume()
    resume_contact = (
        (resume_row.get("parsed", {}) or {}).get("contact", {}) if resume_row else {}
    )
    name_source = (
        resume_contact.get("name")
        or tailored.get("contact", {}).get("name", "")
    )
    contact = dict(tailored.get("contact", {}) or {})
    if not (contact.get("name") or "").strip() and name_source:
        contact["name"] = name_source

    docx_bytes = render_cover_letter_docx(
        cover_letter=cover_letter,
        contact=contact,
        company=job.get("company", "") or "",
        position=job.get("title", "") or "",
    )

    # Filename without a name-fallback that collides with the "cover-letter"
    # suffix we always append (previous fallback "cover-letter" produced
    # "cover-letter_..._cover-letter").
    name_part = slugify(name_source)
    company_part = slugify(job.get("company", ""))
    position_part = slugify(job.get("title", ""))
    pieces = [p for p in [name_part, company_part, position_part] if p]
    pieces.append("cover-letter")
    filename = "_".join(pieces) + ".docx"

    events.track(events.TAILOR_CL_DOWNLOAD, job_id=job_id, run=run)

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _find_cached_by_key(cache_key: str):
    """Find a cached search by its key without needing the params.

    Delegates to `jobs_cache.load_by_key` which handles both the pointer
    format (job_ids resolved via db.get_jobs) and the legacy inline format.
    """
    return jobs_cache.load_by_key(cache_key)


def _load_cache_params(cache_key: str) -> Optional[dict]:
    """Return the raw params dict from a cache file, or None if missing."""
    for path in jobs_cache.CACHE_DIR.glob("*.json"):
        if path.stem != cache_key:
            continue
        try:
            import json as _json
            data = _json.loads(path.read_text(encoding="utf-8"))
            if data.get("params"):
                return data
        except Exception:
            return None
    return None
