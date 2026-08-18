"""Profile tab routes — resume management, ATS report, config surface.

Route map:
    GET  /profile                            → main tab (current resume + ATS + history + api key + saved searches)
    POST /profile/resume/upload              → parse + save + set-as-current, HX-Refresh
    POST /profile/resume/{id}/switch         → mark as current, HX-Refresh
    POST /profile/resume/{id}/delete         → delete (promote next as current if this was), HX-Refresh
    GET  /profile/resume/{id}/download       → download original bytes

Notes:
- Uploads use HTMX with `hx-encoding="multipart/form-data"`. On success we
  return `HX-Refresh: true` so the whole page re-derives current state.
- Deleting a resume: FK constraints ON DELETE handle the cascade. Old
  application rows keep their job link but lose their resume link (SET NULL).
  Job scores for that resume get deleted (CASCADE). Both are correct.
- No API key editing yet — reads env only. Later slice adds DB-backed
  editing when we outgrow the "put it in .env once" workflow.
- Saved searches are read-only display. CRUD lands when we're bored of
  editing `core/jobs/saved_searches.py`.
"""
from __future__ import annotations

import io
import os
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import set_key
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from core import db, events, updater
from core.version import current as current_version
from core.llm.gemini import (
    DEFAULT_MODEL_CHAIN,
    MODEL_QUOTAS,
    GeminiClient,
    GeminiError,
    exhausted_models,
    request_counts_today,
    resolve_api_key,
)
from core.resume.anomalies import (
    analyze as analyze_anomalies,
    missing_sections,
    present_sections,
)
from core.resume.ai_regenerate import regenerate_sections
from core.resume.ats import run_checks
from core.resume.parser import parse_resume

from ..deps import templates


# Path we write the API key to when the user edits it from the UI. Sits at
# jobot-app/.env (already what resolve_api_key reads via python-dotenv).
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _mask_key(key: str) -> str:
    """Show only the last 4 chars — enough to confirm identity, not enough
    to leak the secret if someone glances at the screen."""
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 4:
        return "•" * len(key)
    return f"…{key[-4:]}"


router = APIRouter(tags=["profile"])


@router.get("/profile")
async def profile_page(request: Request, just_regenerated: int = 0):
    current = db.get_current_resume()
    if current:
        # raw_bytes is huge — strip before passing to template
        current.pop("raw_bytes", None)

    all_resumes = db.list_resumes()
    older = [r for r in all_resumes if not r["is_current"]]

    ats_report = run_checks(current["parsed"]) if current else None
    preview_report = analyze_anomalies(current["parsed"]) if current else None

    key = resolve_api_key()
    exhausted = set(exhausted_models())
    quota_rows = [
        {
            "model": m,
            "used": count,
            "limit": MODEL_QUOTAS.get(m, 0),
            "exhausted": m in exhausted,
        }
        for m, count in request_counts_today().items()
    ]

    return templates.TemplateResponse(
        request,
        "pages/profile.html",
        {
            "active_tab": "profile",
            "current": current,
            "older_resumes": older,
            "ats_report": ats_report,
            "preview_report": preview_report,
            "api_key_present": bool(key),
            "api_key_masked": _mask_key(key),
            "quota_rows": quota_rows,
            "saved_searches": db.list_saved_searches(),
            "jobot_version": current_version(),
            "just_regenerated": bool(just_regenerated),
        },
    )


# ── Saved-searches CRUD ────────────────────────────────────

@router.post("/profile/saved-search")
async def create_saved_search(
    name: str = Form(...),
    query: str = Form(...),
    location: str = Form("Ottawa, Ontario, Canada"),
    hours_old: int = Form(168),
    results_wanted: int = Form(30),
    from_: str = Form("", alias="from"),
):
    """Create a saved search. When called from a "suggested query" chip
    (`from=chip`), we swap the chip inline with a "✓ Saved" pill instead
    of triggering a full page refresh — so the user can keep clicking
    other suggestions without losing the list."""
    if not name.strip() or not query.strip():
        return HTMLResponse(
            '<div class="text-error text-sm">Name and query are both required.</div>',
            status_code=200,
        )
    db.add_saved_search(
        name=name, query=query, location=location,
        hours_old=hours_old, results_wanted=results_wanted,
    )
    if from_ == "chip":
        return HTMLResponse(
            '<span class="chip pill-success inline-flex items-center gap-1">'
            '<i class="ph-thin ph-check i-3"></i>Saved</span>',
            status_code=200,
        )
    return Response(status_code=200, headers={"HX-Refresh": "true"})


SUGGESTIONS_CACHE_DAYS = 7
SUGGESTIONS_MAX = 5


def _get_or_generate_suggestions(force: bool = False) -> tuple[list[str], Optional[str], Optional[int]]:
    """Return (queries, error, age_days). Uses 7-day cached suggestions if
    available AND not forcing refresh. Otherwise calls Gemini."""
    resume = db.get_current_resume()
    api_key = resolve_api_key()
    if not resume:
        return [], "Upload a resume first — suggestions come from your background.", None
    if not api_key:
        return [], "Add a Gemini API key first.", None

    resume_id = int(resume["id"])

    # Return cache if fresh AND not forcing
    if not force:
        cached = db.get_cached_suggestions(resume_id, max_age_days=SUGGESTIONS_CACHE_DAYS)
        if cached:
            return cached["queries"][:SUGGESTIONS_MAX], None, cached["age_days"]

    resume_text = (resume["parsed"].get("raw_text") or "")[:4000].strip()
    if not resume_text:
        return [], "Resume text is empty — try re-uploading.", None

    prompt = f"""You are helping a candidate broaden their job-search queries.
Read their resume and suggest exactly {SUGGESTIONS_MAX} distinct job title strings they could
search on LinkedIn or Indeed. Mix:
  - Exact-title variants of what they've done
  - One step down (Junior / Coordinator / Analyst variants)
  - One step up (Senior / Lead / Manager) if realistic
  - Adjacent roles they qualify for based on skills
Keep each 2-5 words — what a user would actually type into a search box.

RESUME:
---
{resume_text}
---

Return JSON: {{"queries": ["query 1", "query 2", ...]}}
"""
    try:
        client = GeminiClient(api_key=api_key)
        raw = client.generate_json(prompt)
        queries = raw.get("queries", [])
        if not isinstance(queries, list):
            queries = []
        queries = [str(q).strip() for q in queries if str(q).strip()][:SUGGESTIONS_MAX]
    except GeminiError as exc:
        return [], f"Failed to generate: {exc}", None
    except Exception as exc:  # noqa: BLE001
        return [], f"Unexpected: {exc}", None

    if not queries:
        return [], "Model returned no usable suggestions. Try again.", None

    db.save_suggestions(resume_id, queries)
    return queries, None, 0


SECTION_SUGGESTIONS_MAX = 3


def _maybe_generate_ai_summary(resume_id: int) -> Optional[dict]:
    """Role label + first-impression sentence + "worth adding?" judgment on
    missing standard sections, from a single Gemini call. Called from the
    lazy-load GET /profile/ai-summary fragment (hx-trigger="load", same
    pattern as the Updates check) — NOT from upload/switch directly, so the
    upload response stays instant and the fragment's own spinner covers the
    1-3s Gemini round-trip.

    Skipped (returns None) if a summary is already cached for this
    resume_id (then returns the cached one instead), if there's no API
    key, or on any failure — this must never raise, the block just doesn't
    render when it can't produce a summary.
    """
    cached = db.get_resume_ai_summary(resume_id)
    if cached:
        return cached
    try:
        api_key = resolve_api_key()
        if not api_key:
            return None

        resume = db.get_resume(resume_id)
        if not resume:
            return None
        parsed = resume["parsed"]
        resume_text = (parsed.get("raw_text") or "")[:4000].strip()
        if not resume_text:
            return None

        present = [t for _, t in present_sections(parsed)]
        missing = missing_sections(parsed)
        if not missing:
            missing_block = "(none — candidate already has every standard section)"
        else:
            missing_block = ", ".join(t for _, t in missing)
        location = (parsed.get("contact") or {}).get("location", "")

        prompt = f"""You are a experienced colleague — not a career coach, not an HR
department — glancing at someone's resume and telling them straight what
you think. You'll get their resume text and two facts: which standard
resume sections they already have, and which they don't. Do THREE things:

1. role_label: In 2-5 words, name the FIELD their experience is in (e.g.
   "civil construction coordination", "B2B sales", "BI / data analytics").
   Base this only on their work history — resumes get reused across
   different job applications, so don't assume this is a "target title,"
   just what their actual experience says they've been doing. Lowercase,
   no fluff, no corporate label-speak.

2. first_impression: ONE sentence (max 22 words), your real reaction
   reading this cold. Say whatever is actually true — could be all
   praise, all criticism, or noting something specific and unusual. Do
   NOT force a "here's what's good, but here's what's weak" sandwich
   every time — that pattern reads as a template, not an opinion.
   Write like you're texting a friend a quick honest take, not writing
   ad copy. Banned words/phrases (instant AI-slop tell, never use them):
   leverage, robust, seamless, dynamic, passionate, results-driven,
   metric-driven, spearhead, utilize, synergy, cutting-edge, elevate,
   unlock, game-changer, "stands out", "speaks volumes", em-dash chains.
   Use plain, specific words. Contractions are fine. If something is
   genuinely impressive, say so plainly ("this is solid") — don't dress
   it up.

3. section_suggestions: Of the MISSING sections listed below, which (if
   any) are actually worth this specific candidate adding? Be selective —
   most resumes don't need most of these. Consider their apparent field
   and, if the location suggests it, the Ottawa/Montreal bilingual job
   market (Languages section matters a LOT there). Almost never suggest
   "References" — modern resumes drop it; only suggest it if something in
   the resume suggests it's expected. Return at most {SECTION_SUGGESTIONS_MAX}
   suggestions, each with a reason under 15 words, same plain-language
   rule as above (no "leverage your robust skillset" nonsense). Empty
   list is a valid, often-correct answer.

TODAY'S DATE: {date.today().strftime("%B %Y")} — use this as "now" when
judging any dates in the resume (e.g. a role starting a few months ago is
current employment, not a typo or something impossible).
CANDIDATE LOCATION: {location or "unknown"}
SECTIONS ALREADY PRESENT: {", ".join(present) or "(none detected)"}
SECTIONS MISSING (only suggest from this list): {missing_block}

RESUME:
---
{resume_text}
---

Return JSON:
{{
  "role_label": "...",
  "first_impression": "...",
  "section_suggestions": [{{"section": "languages", "reason": "..."}}]
}}
"""
        client = GeminiClient(api_key=api_key)
        raw = client.generate_json(prompt)

        role_label = str(raw.get("role_label", "")).strip()[:60]
        first_impression = str(raw.get("first_impression", "")).strip()[:280]

        missing_keys = {k for k, _ in missing}
        suggestions_raw = raw.get("section_suggestions", [])
        suggestions: list[dict] = []
        if isinstance(suggestions_raw, list):
            for item in suggestions_raw:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("section", "")).strip().lower()
                reason = str(item.get("reason", "")).strip()[:160]
                if key in missing_keys and reason:
                    suggestions.append({"section": key, "reason": reason})
                if len(suggestions) >= SECTION_SUGGESTIONS_MAX:
                    break

        db.save_resume_ai_summary(
            resume_id,
            role_label=role_label,
            first_impression=first_impression,
            suggestions=suggestions,
        )
        return {
            "role_label": role_label,
            "first_impression": first_impression,
            "suggestions": suggestions,
        }
    except Exception:  # noqa: BLE001 — must never break the fragment render
        return None


@router.get("/profile/ai-summary")
async def get_ai_summary(request: Request):
    """Lazy-load fragment for the role label / first-impression / section-
    suggestion chips. Same hx-trigger="load" pattern as the Updates check —
    page paints instantly, this fragment resolves the 1-3s Gemini round-trip
    on its own and swaps in (or renders nothing if no key / no resume /
    call failed, all silent per _maybe_generate_ai_summary's contract)."""
    current = db.get_current_resume()
    if not current:
        return HTMLResponse("", status_code=200)
    summary = _maybe_generate_ai_summary(int(current["id"]))
    if not summary:
        return HTMLResponse("", status_code=200)
    return templates.TemplateResponse(
        request, "partials/ai_summary.html", {"summary": summary},
    )


@router.get("/profile/suggest-queries")
@router.post("/profile/suggest-queries")
async def suggest_queries(request: Request, force: int = 0):
    """Return AI-suggested search queries as chip HTML. Uses 7-day cache
    unless `force=1` is passed."""
    queries, error, age_days = _get_or_generate_suggestions(force=bool(force))
    if error:
        return HTMLResponse(f'<div class="text-sm text-body-muted">{error}</div>', status_code=200)
    if not queries:
        return HTMLResponse(
            '<div class="text-sm text-body-muted">No suggestions available.</div>',
            status_code=200,
        )
    return templates.TemplateResponse(
        request,
        "partials/suggested_queries.html",
        {"queries": queries, "age_days": age_days},
    )


@router.post("/profile/saved-search/{sid}/edit")
async def edit_saved_search(
    sid: int,
    name: str = Form(...),
    query: str = Form(...),
    location: str = Form(...),
    hours_old: int = Form(168),
    results_wanted: int = Form(30),
):
    if not db.get_saved_search(sid):
        raise HTTPException(status_code=404, detail="Saved search not found")
    db.update_saved_search(
        sid, name=name, query=query, location=location,
        hours_old=hours_old, results_wanted=results_wanted,
    )
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.post("/profile/saved-search/{sid}/delete")
async def delete_saved_search_route(sid: int):
    db.delete_saved_search(sid)
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.post("/profile/api-key")
async def update_api_key(request: Request, api_key: str = Form(...)):
    """Persist an API key to .env AND update os.environ so it takes effect
    immediately (subsequent GeminiClient() calls see the new key without
    a server restart). Returns an updated Profile page via HX-Refresh."""
    key = (api_key or "").strip()
    if not key:
        return HTMLResponse(
            '<div class="text-error text-sm">Please paste a non-empty API key.</div>',
            status_code=200,
        )

    # Basic sanity check — Google API keys are usually 39 chars starting with 'AIza'.
    # Don't hard-fail on format; just warn if it looks off.
    if len(key) < 20:
        return HTMLResponse(
            '<div class="text-error text-sm">Key looks too short. Double-check you pasted the whole thing.</div>',
            status_code=200,
        )

    # Ensure the .env file exists (set_key needs it)
    _ENV_FILE.touch(exist_ok=True)
    set_key(str(_ENV_FILE), "GOOGLE_API_KEY", key, quote_mode="never")

    # Update in-process env var so this request's downstream calls see the new key.
    os.environ["GOOGLE_API_KEY"] = key

    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.post("/profile/api-key/clear")
async def clear_api_key():
    """Remove the API key from both the .env and process env."""
    if _ENV_FILE.exists():
        # `set_key` with empty string effectively unsets. python-dotenv keeps the line
        # but with empty value — safe enough since our resolver treats "" as missing.
        set_key(str(_ENV_FILE), "GOOGLE_API_KEY", "", quote_mode="never")
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.post("/profile/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Accept a DOCX/PDF, parse it, save + set as current. Refreshes the
    page on success. On parse failure, return the error inline (no crash)."""
    if not file.filename:
        return HTMLResponse(
            '<div class="text-error text-sm">No file received.</div>',
            status_code=200,
        )
    lower = file.filename.lower()
    if not (lower.endswith(".docx") or lower.endswith(".pdf")):
        return HTMLResponse(
            '<div class="text-error text-sm">Only .docx and .pdf files are accepted.</div>',
            status_code=200,
        )

    raw = await file.read()
    if not raw:
        return HTMLResponse(
            '<div class="text-error text-sm">File is empty.</div>',
            status_code=200,
        )

    try:
        parsed = parse_resume(raw, file.filename)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(
            f'<div class="text-error text-sm">Could not parse: {exc}</div>',
            status_code=200,
        )

    db.save_resume(file.filename, parsed, raw, set_current=True)
    events.track(
        events.RESUME_UPLOADED,
        filename=file.filename,
        word_count=parsed.get("stats", {}).get("word_count"),
        page_estimate=parsed.get("stats", {}).get("page_estimate"),
    )
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.post("/profile/resume/{resume_id}/contact")
async def update_resume_contact(
    request: Request,
    resume_id: int,
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    linkedin: str = Form(""),
):
    """User-confirmed contact overrides. Full replace of the contact
    sub-dict (not sparse) — the form always sends all 5 fields, blank or
    not, so there's no ambiguity about "field omitted" vs "field cleared"."""
    if not db.get_resume(resume_id):
        raise HTTPException(status_code=404, detail="Resume not found")
    db.update_resume_contact(resume_id, {
        "name": name.strip(),
        "email": email.strip(),
        "phone": phone.strip(),
        "location": location.strip(),
        "linkedin": linkedin.strip(),
    })
    current = db.get_current_resume()
    if current:
        current.pop("raw_bytes", None)
    return templates.TemplateResponse(
        request, "partials/contact_verify.html", {"current": current},
    )


@router.post("/profile/resume/{resume_id}/regenerate")
async def regenerate_resume(resume_id: int):
    """LLM re-parse pass — asks Gemini to re-derive the parsed sections
    from raw_text when the deterministic parser got confused (PDF reflow,
    unusual layout). Overwrites parsed_json; raw_bytes are untouched, so
    the original file is still downloadable if the re-parse also disappoints."""
    resume = db.get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    api_key = resolve_api_key()
    if not api_key:
        return HTMLResponse(
            '<div class="text-error text-sm">Add a Gemini API key first (Profile → API key).</div>',
            status_code=200,
        )

    try:
        new_parsed = regenerate_sections(resume["parsed"], api_key)
    except GeminiError as exc:
        return HTMLResponse(
            f'<div class="text-error text-sm">Regeneration failed: {exc}</div>',
            status_code=200,
        )
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(
            f'<div class="text-error text-sm">Unexpected error: {exc}</div>',
            status_code=200,
        )

    db.update_resume_parsed(resume_id, new_parsed)
    # HX-Redirect (not HX-Refresh) so we can carry ?just_regenerated=1 —
    # the profile page reads that flag on load to reopen the modal on the
    # fresh parse and fire a success toast.
    return Response(status_code=200, headers={"HX-Redirect": "/profile?just_regenerated=1"})


@router.post("/profile/resume/{resume_id}/switch")
async def switch_resume(resume_id: int):
    if not db.get_resume(resume_id):
        raise HTTPException(status_code=404, detail="Resume not found")
    db.set_current_resume(resume_id)
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.post("/profile/resume/{resume_id}/delete")
async def delete_resume(resume_id: int):
    r = db.get_resume(resume_id)
    if not r:
        return Response(status_code=200, headers={"HX-Refresh": "true"})

    was_current = bool(r.get("is_current"))
    db.delete_resume(resume_id)

    # Promote the next-most-recent if we just killed the active one.
    if was_current:
        remaining = db.list_resumes()
        if remaining:
            db.set_current_resume(int(remaining[0]["id"]))

    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.get("/profile/resume/{resume_id}/download")
async def download_resume(resume_id: int):
    r = db.get_resume(resume_id)
    if not r:
        raise HTTPException(status_code=404, detail="Resume not found")
    raw = r.get("raw_bytes")
    if not raw:
        raise HTTPException(status_code=404, detail="Original bytes not stored")

    filename = r["filename"]
    media = (
        "application/pdf" if filename.lower().endswith(".pdf")
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return StreamingResponse(
        io.BytesIO(raw),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────
# In-app updater — check GitHub Releases, download the pending zip.
# Installing the update happens via the "Update Jobot.command" script
# (kills the server, extracts, pip installs, restarts).
# ─────────────────────────────────────────────────────────────

@router.get("/profile/updates/check")
async def profile_updates_check(request: Request):
    """HTMX-swappable status fragment for the 'Updates' card. Hits GitHub
    on every call — the API is generous enough (60/hr unauth) and users
    rarely mash this."""
    status = updater.check()
    return templates.TemplateResponse(
        request,
        "partials/update_status.html",
        {"status": status.to_dict()},
    )


@router.post("/profile/updates/download")
async def profile_updates_download(request: Request):
    """Downloads the pending release zip to dist/pending-update.zip so
    the Update.command script can pick it up. Returns the status fragment
    with a follow-up instruction (double-click Update.command)."""
    status = updater.check()
    if not status.has_update or not status.download_url:
        return templates.TemplateResponse(
            request,
            "partials/update_status.html",
            {"status": status.to_dict()},
        )
    try:
        updater.download(status.download_url)
    except Exception as exc:  # noqa: BLE001
        status.error = f"Download failed: {exc}"
        return templates.TemplateResponse(
            request,
            "partials/update_status.html",
            {"status": status.to_dict()},
        )
    # Re-check so the fragment reflects the new pending_downloaded=True
    refreshed = updater.check()
    return templates.TemplateResponse(
        request,
        "partials/update_status.html",
        {"status": refreshed.to_dict()},
    )


@router.post("/profile/updates/cancel")
async def profile_updates_cancel(request: Request):
    """Discard a pending downloaded update — user changed their mind."""
    updater.clear_pending()
    status = updater.check()
    return templates.TemplateResponse(
        request,
        "partials/update_status.html",
        {"status": status.to_dict()},
    )


# ─────────────────────────────────────────────────────────────
# Analytics — beacon endpoint + Insights view
# ─────────────────────────────────────────────────────────────

@router.post("/events/track")
async def events_track(
    request: Request,
    type: str = Form(...),
    payload: str = Form("{}"),
):
    """Frontend beacon endpoint. Fired via `navigator.sendBeacon()` on
    tab visibility changes so we can measure real time-on-tab. Payload
    is a JSON string. Never returns 5xx — bad payloads become empty dicts."""
    import json as _json
    try:
        parsed = _json.loads(payload) if payload else {}
        if not isinstance(parsed, dict):
            parsed = {"raw": str(parsed)[:200]}
    except Exception:
        parsed = {}
    events.track(type, **parsed)
    return Response(status_code=204)


@router.get("/profile/insights")
async def profile_insights(request: Request):
    """Insights tab content — swapped into the Settings hub when the
    'Insights' seg-tab is clicked. Aggregates from the events table +
    applications table."""
    counts = events.counts_by_type_last_week()
    daily = events.daily_activity(days=14)
    hourly = events.hour_of_day_histogram(days=14)
    funnel = events.funnel_last_month()
    total = events.total_events()
    active_days = events.days_with_activity(days=14)
    median_seconds = events.median_time_to_download_seconds(days=30)

    # Simple key numbers pre-computed for template convenience
    key_metrics = {
        "sessions_week": counts.get(events.PAGE_VIEW, 0),
        "searches_broad": counts.get(events.SEARCH_BROAD, 0),
        "searches_url": counts.get(events.SEARCH_URL_IMPORT, 0),
        "jobs_viewed": counts.get(events.JOB_DETAIL_VIEWED, 0),
        "tailors_generated": counts.get(events.TAILOR_GENERATED, 0),
        "resumes_downloaded": counts.get(events.TAILOR_RESUME_DOWNLOAD, 0),
    }

    return templates.TemplateResponse(
        request,
        "partials/insights.html",
        {
            "total_events": total,
            "active_days_14d": active_days,
            "key_metrics": key_metrics,
            "daily": daily,
            "hourly": hourly,
            "hourly_max": max(hourly) if hourly else 1,
            "funnel": funnel,
            "median_seconds_to_download": median_seconds,
        },
    )


@router.post("/profile/insights/clear")
async def profile_insights_clear(request: Request):
    """Wipe all events. Behind a hx-confirm on the client."""
    n = events.clear_all()
    return HTMLResponse(
        f'<div class="pill pill-success inline-flex items-center gap-1.5">'
        f'<i class="ph-thin ph-trash i-3"></i>Cleared {n} events</div>',
        status_code=200,
    )
