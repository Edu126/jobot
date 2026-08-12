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
from pathlib import Path
from typing import Optional

from dotenv import set_key
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from core import db, updater
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
async def profile_page(request: Request):
    current = db.get_current_resume()
    if current:
        # raw_bytes is huge — strip before passing to template
        current.pop("raw_bytes", None)

    all_resumes = db.list_resumes()
    older = [r for r in all_resumes if not r["is_current"]]

    ats_report = run_checks(current["parsed"]) if current else None

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
            "api_key_present": bool(key),
            "api_key_masked": _mask_key(key),
            "quota_rows": quota_rows,
            "saved_searches": db.list_saved_searches(),
            "jobot_version": current_version(),
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
            '<span class="chip" style="background: hsl(155 40% 92%); color: hsl(165 60% 25%); border-color: hsl(155 40% 82%);">✓ Saved</span>',
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
    return Response(status_code=200, headers={"HX-Refresh": "true"})


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
