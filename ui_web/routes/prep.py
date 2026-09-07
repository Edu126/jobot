"""Prep tab — the post-callback "land it" kit (REQ-023).

A prep session is a per-VACANCY workspace (ADR-026), created at the callback
moment. Entry ladder: paste a link/JD or type company+role → we try to match it
to a job we already hold (tailored set first) so the kit reuses the stored JD /
score / gaps / defense hooks; an exact URL auto-binds, a fuzzy match asks for a
one-tap confirm, nothing matches → a fresh unbound session. The detail view
lazy-loads the company outlook (ADR-027) and the STAR/reverse kit (ADR-028).
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import db, events
from core.jobs.from_url import (
    UrlExtractError,
    extract_job_from_text,
    job_from_url,
)
from core.llm.gemini import GeminiClient, resolve_api_key
from core.matching.semantic_score import score_single_no_cache
from core.prep import company_outlook as co
from core.prep import fit
from core.prep import kit as prep_kit
from core.prep import matching
from core.settings import get_output_language

from ..deps import templates

router = APIRouter(tags=["prep"])


def _current():
    """(resume dict, resume_hash, resume_id, resume_text) or (None, ...)."""
    r = db.get_current_resume()
    if not r:
        return None, "", 0, ""
    return (r, r.get("text_hash") or "", int(r["id"]),
            (r["parsed"].get("raw_text") or "").strip())


def _looks_like_url(s: str) -> bool:
    s = (s or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://") or s.startswith("www.")


# ---------- the tab: list + entry ----------

@router.get("/prep")
async def prep_list(request: Request):
    resume, resume_hash, _rid, _txt = _current()
    sessions = db.list_prep_sessions(resume_hash) if resume_hash else []
    # A qualitative band (not a bare %) for each card — same honesty/esteem
    # treatment as the detail context bar (REQ-025).
    for s in sessions:
        s["band"] = fit.band_from_score(s.get("match_score"))
    autocomplete = db.recent_companies_and_titles()
    return templates.TemplateResponse(
        request,
        "pages/prep_list.html",
        {"active_tab": "prep", "has_resume": resume is not None, "sessions": sessions,
         "ac_companies": autocomplete["companies"], "ac_titles": autocomplete["titles"]},
    )


@router.post("/prep/start")
async def prep_start(
    request: Request,
    company: str = Form(""),
    role_title: str = Form(""),
    vacancy: str = Form(""),   # a link OR pasted JD text
):
    _resume, resume_hash, resume_id, resume_text = _current()
    if not resume_hash:
        return HTMLResponse('<div class="text-error text-sm">Upload a résumé first.</div>')

    vacancy = vacancy.strip()
    url = vacancy if _looks_like_url(vacancy) else ""
    text = "" if url else vacancy
    lang = get_output_language()

    # 1. Try a job we ALREADY hold (best grounding: it's scored, maybe
    #    gap-enhanced). Exact URL auto-binds; fuzzy hits ask for a one-tap
    #    confirm among our own postings.
    result = matching.find_matches(
        resume_hash, url=url, text=text, company=company.strip(),
        role_title=role_title.strip(),
    )
    if result.bound_job_id:
        sid = _create_bound(resume_hash, result.bound_job_id, lang)
        return _redirect_to_session(sid)
    if result.candidates:
        return templates.TemplateResponse(
            request,
            "partials/prep_confirm.html",
            {"candidates": result.candidates,
             "company": company.strip(), "role_title": role_title.strip(),
             "jd_text": text},
        )

    # 2. Not in our DB, but we have a link or a pasted JD → IMPORT the posting
    #    (scrape/extract) + score it, then show a confirm preview (ADR-030 —
    #    what we grabbed is not guaranteed to be the role the user meant).
    if url or text:
        client = GeminiClient(api_key=resolve_api_key())
        job, err = await asyncio.to_thread(
            _import_and_score, url, text, resume_text, resume_id, client, lang)
        if err:
            return templates.TemplateResponse(
                request, "partials/prep_import_error.html", {"message": err})
        return templates.TemplateResponse(
            request,
            "partials/prep_import_confirm.html",
            {"job": job, "match_score": job.get("_score"),
             "band": fit.band_from_score(job.get("_score")),
             "match_brief_json": json.dumps(job.get("_brief") or {}),
             "source": "pasted_link" if url else "pasted_text"},
        )

    # 3. Only a typed company/role (weakest grounding) → straight to a session.
    if not company.strip():
        return HTMLResponse(
            '<div class="text-error text-sm">Add a company name, a job link, or '
            'paste the job description so we can build your prep.</div>')
    sid = db.create_prep_session(
        resume_hash, company.strip(), role_title.strip(), "", lang, "typed")
    events.track("prep_session_created", source="typed", bound=False)
    return _redirect_to_session(sid)


@router.post("/prep/confirm")
async def prep_confirm(
    request: Request,
    job_id: str = Form(""),
    company: str = Form(""),
    role_title: str = Form(""),
    jd_text: str = Form(""),
    match_score: str = Form(""),        # carried from the import preview
    match_brief: str = Form(""),        # JSON {reasoning, matched, gaps}
    source: str = Form("pasted_text"),
):
    _resume, resume_hash, _rid, _txt = _current()
    if not resume_hash:
        return HTMLResponse('<div class="text-error text-sm">Upload a résumé first.</div>')
    lang = get_output_language()

    if job_id.strip():   # confirmed one of the proposed matches
        sid = _create_bound(resume_hash, job_id.strip(), lang)
    else:                # confirmed an import / "None of these" → fresh session
        if not (company.strip() or jd_text.strip()):
            return HTMLResponse('<div class="text-error text-sm">Add a company or paste the JD.</div>')
        ms = _parse_score(match_score)
        src = source if source in ("pasted_link", "pasted_text") else "pasted_text"
        brief = _clean_brief_json(match_brief)
        sid = db.create_prep_session(
            resume_hash, company.strip(), role_title.strip(), jd_text.strip(),
            lang, src, match_score=ms, match_brief=brief)
        events.track("prep_session_created", source=src, bound=False)
    return _redirect_to_session(sid)


def _parse_score(raw: str) -> Optional[int]:
    """Parse the round-tripped match_score form field to an int, or None. A bare
    try/except (not an `isdigit` guard) so odd inputs like '--5' or '72.5' return
    None instead of crashing int()."""
    try:
        return int((raw or "").strip())
    except (ValueError, TypeError):
        return None


def _clean_brief_json(raw: str) -> Optional[str]:
    """Validate the fit brief carried through the confirm form: re-parse and
    run it through the ONE size contract (fit.sanitize_brief), re-serialize.
    None if unusable — never trust the round-tripped blob verbatim."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    clean = fit.sanitize_brief(d)
    if not (clean["reasoning"] or clean["matched"] or clean["gaps"]):
        return None
    return json.dumps(clean)


def _link_help(url: str, base: str) -> str:
    """Directionally-correct failure copy (the paste box is ABOVE the error).
    Adds a LinkedIn-specific tip: a search/collections URL isn't a posting — the
    user needs the job's Share → Copy link. (A graphic how-to is a future hint,
    REQ-025.)"""
    if "linkedin.com" in (url or "").lower():
        return (base + " Tip: on LinkedIn, open the specific job and use "
                "Share → Copy link — a search or feed URL isn't a posting we can read.")
    return base


def _import_and_score(url, text, resume_text, resume_id, client, lang):
    """Import a posting we don't hold — scrape a URL (`job_from_url` waterfall)
    or extract pasted JD text — then take a one-shot fit read (no tailoring;
    Prep is post-apply). Returns (job_dict_with_`_score`, None) or (None, msg).
    Grounded-or-honest: a scrape failure returns a message, never a fake job."""
    try:
        if url:
            job = job_from_url(url, client)
        else:
            job = extract_job_from_text(text, source_url="", client=client)
    except UrlExtractError:
        return None, _link_help(url,
            "We couldn't find a job posting at that link. Paste the job "
            "description text in the box above instead.")
    except Exception:  # noqa: BLE001 — network/parse blowups degrade to paste
        return None, _link_help(url,
            "We couldn't read that link — the site may block scrapers. Paste "
            "the job description in the box above instead.")
    job["_score"] = None
    job["_brief"] = fit.sanitize_brief({})
    if resume_text and job:
        res = score_single_no_cache(
            resume_text, job, client, lang=lang, resume_id=resume_id)
        if res is not None:
            job["_score"] = res.score
            job["_brief"] = fit.sanitize_brief(
                {"reasoning": res.reasoning, "matched": res.matched, "gaps": res.gaps})
    return job, None


@router.post("/prep/from-job/{job_id}")
async def prep_from_job(request: Request, job_id: str):
    """'Prep from here' — get-or-create one bound session per (candidate, job)."""
    _resume, resume_hash, _rid, _txt = _current()
    if not resume_hash:
        return _redirect_to("/prep")
    existing = db.get_prep_session_for_job(resume_hash, job_id)
    sid = existing["id"] if existing else _create_bound(resume_hash, job_id, get_output_language())
    return _redirect_to_session(sid)


def _create_bound(resume_hash: str, job_id: str, lang: str) -> int:
    """Create a session bound to a job, copying its stored JD/company/role so
    the session stays self-contained even if the job is later deleted."""
    job = db.get_job(job_id) or {}
    sid = db.create_prep_session(
        resume_hash,
        job.get("company", ""), job.get("title", ""), job.get("description", ""),
        lang, "from_job", job_id=job_id,
    )
    events.track("prep_session_created", source="from_job", bound=True)
    return sid


# ---------- the detail view ----------

@router.get("/prep/{session_id}")
async def prep_detail(request: Request, session_id: int):
    session = db.get_prep_session(session_id)
    if not session:
        return _redirect_to("/prep")
    db.touch_prep_session(session_id)
    # Prep-stage fit brief (REQ-025): band + narrative + strengths/gaps instead
    # of a bare %. Imported sessions carry their own (ADR-030); bound derive it.
    brief = fit.brief_for_session(session)
    return templates.TemplateResponse(
        request,
        "pages/prep_detail.html",
        {"active_tab": "prep", "session": session, "brief": brief},
    )


@router.get("/prep/{session_id}/outlook")
async def prep_outlook(request: Request, session_id: int, refresh: int = 0):
    session = db.get_prep_session(session_id)
    if not session:
        return HTMLResponse("")
    outlook = await _load_outlook(session, use_cache=not refresh)
    return templates.TemplateResponse(
        request,
        "partials/prep_outlook.html",
        {"session_id": session_id, "outlook": outlook,
         "company": session.get("company", "")},
    )


@router.get("/prep/{session_id}/kit")
async def prep_kit_fragment(request: Request, session_id: int):
    session = db.get_prep_session(session_id)
    if not session:
        return HTMLResponse("")
    _resume, _rh, resume_id, resume_text = _current()
    lang = session.get("lang") or get_output_language()
    kit = None
    if resume_text:
        api_key = resolve_api_key()
        client = GeminiClient(api_key=api_key)
        kit = await asyncio.to_thread(
            prep_kit.get_or_generate_kit, session, resume_id, resume_text, client,
            lang=lang,
        )
    # The real layers the kit stands on — surfaced so the user trusts it isn't
    # generic (REQ-025): résumé always, plus role/JD, company, and the gaps it
    # actually turned into defensive questions (counted from the kit, so we don't
    # re-read the gap cache the kit generation already consulted).
    gaps_count = sum(1 for q in kit.star_qa if q.kind == "defensive_gap") if kit else 0
    layers = {
        "resume": bool(resume_text),
        "jd": bool((session.get("jd_text") or "").strip()),
        "role": bool((session.get("role_title") or "").strip()),
        "company": (session.get("company") or "").strip(),
        "gaps": gaps_count,
    }
    return templates.TemplateResponse(
        request,
        "partials/prep_kit.html",
        {"kit": kit, "session_id": session_id, "layers": layers},
    )


@router.post("/prep/{session_id}/qa-feedback")
async def prep_qa_feedback(
    request: Request,
    session_id: int,
    kind: str = Form(""),
    question: str = Form(""),
    vote: str = Form(""),
):
    """Thumbs up/down on a STAR answer → BI-loop signal (vision non-negotiable
    #5). No new table: it rides the `events` stream (shows in /admin/pulse) so
    we learn which AI questions land and which are 'bizarre'."""
    if vote in ("up", "down"):
        events.track("prep_qa_feedback", session_id=session_id, kind=kind,
                     question=question[:160], vote=vote)
    return HTMLResponse("")


@router.delete("/prep/{session_id}")
async def prep_delete(request: Request, session_id: int):
    db.delete_prep_session(session_id)
    return HTMLResponse("", headers={"HX-Redirect": "/prep"})


async def _load_outlook(session: dict, *, use_cache: bool):
    client = GeminiClient(api_key=resolve_api_key())
    return await asyncio.to_thread(
        co.get_or_generate, session.get("company", ""), session.get("role_title", ""),
        client, lang=session.get("lang") or None, use_cache=use_cache,
    )


# ---------- helpers ----------

def _redirect_to_session(sid: int) -> HTMLResponse:
    return HTMLResponse("", headers={"HX-Redirect": f"/prep/{sid}"})


def _redirect_to(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
