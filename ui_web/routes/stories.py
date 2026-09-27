"""Story Bank — the account-level STAR-story assets (REQ-041, ADR-050, Flow B).

Stories live at the candidate level (resume_hash) and are reused across every
interview — P3 maps them to each interview's competencies. This router owns the
bank UI:

    GET    /stories               → B1 home (list · filter · empty state)
    GET    /stories/new           → B4 editor (blank — "write one")
    GET    /stories/{id}/edit     → B4 editor (existing story)
    POST   /stories               → create (from the editor)
    POST   /stories/{id}          → update
    DELETE /stories/{id}          → delete
    POST   /stories/strength      → live strength badge (editor side panel)
    GET    /stories/draft         → B2 draft-from-résumé (P5)
    POST   /stories/draft/accept  → save one accepted draft
    GET    /stories/voice         → B3 voice capture page
    POST   /stories/voice         → P6 transcript → STAR draft (into the editor)

The strength badge is computed in CODE (story_bank.strength_check) — deterministic,
so it stays honest as the user edits (ADR-050 / like delivery metrics).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import db
from core.llm.gemini import GeminiClient, resolve_api_key
from core.prep import story_bank
from core.settings import get_output_language

from ..deps import templates

router = APIRouter(tags=["stories"])


def _current():
    r = db.get_current_resume()
    if not r:
        return None, "", 0, ""
    return (r, r.get("text_hash") or "", int(r["id"]),
            (r["parsed"].get("raw_text") or "").strip())


def _with_strength(story: dict) -> dict:
    """Attach the code-computed strength badge to a story dict for rendering."""
    s = dict(story)
    s["strength"] = story_bank.strength_check(story)
    return s


def _parse_tags(raw: str) -> list[str]:
    """Editor tags arrive as a comma-separated string; keep only known ones so
    the bank stays taggable (same vocabulary P5/P6 draw from)."""
    valid = {t.lower(): t for t in story_bank.DEFAULT_COMPETENCY_TAGS}
    out: list[str] = []
    for part in (raw or "").split(","):
        canon = valid.get(part.strip().lower())
        if canon and canon not in out:
            out.append(canon)
    return out


# ---------- B1: the bank home ----------

@router.get("/stories")
async def stories_home(request: Request):
    resume, resume_hash, _rid, _txt = _current()
    stories = [_with_strength(s) for s in db.list_stories(resume_hash, status="saved")] if resume_hash else []
    # Distinct tags present in the bank → the filter row.
    tags: list[str] = []
    for s in stories:
        for t in s.get("tags", []):
            if t not in tags:
                tags.append(t)
    return templates.TemplateResponse(
        request,
        "pages/stories_home.html",
        {"active_tab": "prep", "has_resume": resume is not None,
         "stories": stories, "tags": sorted(tags)},
    )


# ---------- B4: the editor ----------

@router.get("/stories/new")
async def story_new(request: Request):
    return templates.TemplateResponse(
        request, "pages/story_editor.html",
        {"active_tab": "prep", "story": None, "all_tags": story_bank.DEFAULT_COMPETENCY_TAGS},
    )


@router.get("/stories/{story_id}/edit")
async def story_edit(request: Request, story_id: int):
    story = db.get_story(story_id)
    if not story:
        return _redirect("/stories")
    return templates.TemplateResponse(
        request, "pages/story_editor.html",
        {"active_tab": "prep", "story": _with_strength(story),
         "all_tags": story_bank.DEFAULT_COMPETENCY_TAGS},
    )


@router.post("/stories")
async def story_create(
    request: Request,
    title: str = Form(""),
    situation: str = Form(""),
    task: str = Form(""),
    action: str = Form(""),
    result: str = Form(""),
    metric: str = Form(""),
    tags: str = Form(""),
    source: str = Form("manual"),
):
    _resume, resume_hash, _rid, _txt = _current()
    if not resume_hash:
        return HTMLResponse('<div class="text-error text-sm">Upload a résumé first.</div>')
    if not title.strip() and not action.strip():
        return HTMLResponse('<div class="text-error text-sm">Give the story a title and an action.</div>')
    db.create_story(
        resume_hash, title=title.strip(), situation=situation.strip(),
        task=task.strip(), action=action.strip(), result=result.strip(),
        metric=metric.strip() or None, tags=_parse_tags(tags),
        source=source if source in db.VALID_STORY_SOURCES else "manual", status="saved")
    return HTMLResponse("", headers={"HX-Redirect": "/stories"})


@router.post("/stories/strength")
async def story_strength(
    request: Request,
    action: str = Form(""),
    result: str = Form(""),
    metric: str = Form(""),
):
    """Live strength badge for the editor side panel — the same code check the
    bank list uses, refreshed as the STAR fields change."""
    strength = story_bank.strength_check(
        {"action": action, "result": result, "metric": metric})
    return templates.TemplateResponse(
        request, "partials/story_strength.html", {"strength": strength})


# ---------- B2: draft from résumé (P5) ----------

@router.get("/stories/draft")
async def stories_draft(request: Request):
    _resume, _rh, _rid, resume_text = _current()
    drafts = []
    if resume_text:
        client = GeminiClient(api_key=resolve_api_key())
        drafts = await asyncio.to_thread(
            story_bank.draft_stories_from_resume, resume_text, client,
            lang=get_output_language())
    return templates.TemplateResponse(
        request, "pages/stories_draft.html",
        {"active_tab": "prep", "drafts": drafts},
    )


@router.get("/stories/suggested")
async def stories_suggested(request: Request):
    """HTMX partial for the empty-state Story Bank: AI-drafted STAR stories from
    the résumé, lazy-loaded so the bank never looks empty (Flow B1). Same P5
    generator as /stories/draft; returns just the draft cards."""
    _resume, _rh, _rid, resume_text = _current()
    drafts = []
    if resume_text:
        client = GeminiClient(api_key=resolve_api_key())
        drafts = await asyncio.to_thread(
            story_bank.draft_stories_from_resume, resume_text, client,
            lang=get_output_language())
    return templates.TemplateResponse(
        request, "partials/story_drafts.html", {"drafts": drafts})


@router.post("/stories/draft/accept")
async def stories_draft_accept(
    request: Request,
    title: str = Form(""),
    situation: str = Form(""),
    task: str = Form(""),
    action: str = Form(""),
    result: str = Form(""),
    metric: str = Form(""),
    tags: str = Form(""),
):
    """Save one accepted P5 draft into the bank. Returns an empty 200 so the
    card can remove itself in place (no full reload — the user keeps triaging)."""
    _resume, resume_hash, _rid, _txt = _current()
    if not resume_hash or not (title.strip() or action.strip()):
        return HTMLResponse("", status_code=204)
    db.create_story(
        resume_hash, title=title.strip(), situation=situation.strip(),
        task=task.strip(), action=action.strip(), result=result.strip(),
        metric=metric.strip() or None, tags=_parse_tags(tags),
        source="ai_resume", status="saved")
    return templates.TemplateResponse(request, "partials/story_accepted.html", {})


# ---------- B3: voice capture (P6) ----------

@router.get("/stories/voice")
async def stories_voice(request: Request):
    return templates.TemplateResponse(
        request, "pages/stories_voice.html", {"active_tab": "prep"})


@router.post("/stories/voice")
async def stories_voice_to_star(request: Request, transcript: str = Form("")):
    """P6 — turn a spoken/typed transcript into a STAR draft, then hand it to the
    editor (prefilled, source=voice) for review + save."""
    transcript = transcript.strip()
    if not transcript:
        return HTMLResponse('<div class="text-error text-sm">Say or type something first.</div>')
    client = GeminiClient(api_key=resolve_api_key())
    draft = await asyncio.to_thread(
        story_bank.story_from_voice, transcript, client, lang=get_output_language())
    if draft is None:
        return templates.TemplateResponse(request, "partials/story_voice_error.html", {})
    story = {
        "id": None, "title": draft.title, "situation": draft.situation,
        "task": draft.task, "action": draft.action, "result": draft.result or "",
        "metric": draft.metric or "", "tags": draft.tags,
        "follow_up_question": draft.follow_up_question,
    }
    return templates.TemplateResponse(
        request, "partials/story_editor_form.html",
        {"story": _with_strength(story), "all_tags": story_bank.DEFAULT_COMPETENCY_TAGS,
         "source": "voice", "embedded": True},
    )


# ---------- edit / delete (parameterized — declared LAST so literal paths like
# /stories/strength and /stories/voice aren't captured as {story_id}) ----------

@router.post("/stories/{story_id}")
async def story_update(
    request: Request,
    story_id: int,
    title: str = Form(""),
    situation: str = Form(""),
    task: str = Form(""),
    action: str = Form(""),
    result: str = Form(""),
    metric: str = Form(""),
    tags: str = Form(""),
):
    if not db.get_story(story_id):
        return _redirect("/stories")
    db.update_story(story_id, {
        "title": title.strip(), "situation": situation.strip(), "task": task.strip(),
        "action": action.strip(), "result": result.strip(),
        "metric": metric.strip() or None, "tags": _parse_tags(tags)})
    return HTMLResponse("", headers={"HX-Redirect": "/stories"})


@router.delete("/stories/{story_id}")
async def story_delete(request: Request, story_id: int):
    db.delete_story(story_id)
    return HTMLResponse("", headers={"HX-Redirect": "/stories"})


# ---------- helpers ----------

def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
