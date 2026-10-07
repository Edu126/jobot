"""Interviews — the rebuilt Prep module (REQ-041, ADR-047).

The Interview is the central object (one role + one company + one round). This
router owns the New-Interview flow (Flow A) and the Brief screen (Screen 2):

    GET  /interviews/new            → A1 entry choice (from a match / link / JD)
    GET  /interviews/new/form       → A2 details form (prefilled), HTMX partial
    POST /interviews/create         → create the Interview → generating screen
    GET  /interviews/{id}/generating→ A3 generating screen (checklist)
    POST /interviews/{id}/build     → run research + P1 Brief, warm the toolkit
    GET  /interviews/{id}           → Brief (Screen 2)

Built at `/interviews` alongside the old `/prep` kit, which stays live until the
new screens reach parity (ADR-047 — no big-bang deletion). The nav still points
at `/prep`; it flips to `/interviews` at parity.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from core import db
from core.llm.gemini import GeminiClient, resolve_api_key
from core.prep import brief as prep_brief
from core.prep import audio_metrics as prep_audio_metrics
from core.prep import audio_score as prep_audio_score
from core.prep import live as prep_live
from core.prep import pipeline
from core.prep import practice as prep_practice
from core.prep import toolkit as prep_toolkit
from core.prep import readiness as prep_readiness
from core.prep import session_score as prep_session_score
from core.prep import voice_lab as prep_voice_lab
from core.prep import story_bank as prep_story_bank
from core.prep import tavily
from core import settings as app_settings
from core.settings import get_output_language

PRACTICE_CONSENT_KEY = "prep_practice_consent"

from ..deps import templates
from ..deps import current_resume as _current, see_other as _redirect, error_snippet as _error
from ..i18n import translate as _t

router = APIRouter(tags=["interviews"])

# Keep a strong ref to background toolkit warm-up tasks so they aren't GC'd
# mid-flight (asyncio only holds a weak reference to a bare create_task).
_warmups: set[asyncio.Task] = set()


def _make_client_factory():
    """A factory the orchestrator calls once per pipeline stage — each stage its
    own client so concurrent fan-out calls don't clobber `last_model_used`
    (see pipeline.build_toolkit). Resolves the key once, up front."""
    api_key = resolve_api_key()
    return lambda: GeminiClient(api_key=api_key)


# ---------- Home (Screen 1): My Interviews ----------

@router.get("/interviews")
async def interviews_home(request: Request):
    """Home — "What's next, and am I ready?" The soonest interview is the hero;
    the rest are compact rows. Each carries its readiness band (D9) + a when
    display. Empty → one clear CTA."""
    resume, resume_hash, _rid, _txt = _current()
    rows = db.list_interviews(resume_hash) if resume_hash else []
    lang = get_output_language()
    enriched = [_enrich_for_home(iv, lang) for iv in rows]
    hero = enriched[0] if enriched else None
    rest = enriched[1:]
    return templates.TemplateResponse(
        request,
        "pages/interview_home.html",
        {"active_tab": "prep", "has_resume": resume is not None,
         "hero": hero, "rest": rest, "any": bool(enriched)},
    )


def _enrich_for_home(interview: dict, lang: str) -> dict:
    """Attach readiness + a parsed 'when' for Home. `at` is the validated local
    'YYYY-MM-DDTHH:MM' the browser uses for the urgent cue (see _fmt_when)."""
    readiness = prep_readiness.compute(interview, lang=interview.get("lang") or lang)
    when, at = _fmt_when(interview.get("interview_at"))
    has_brief = prep_brief.read_cached_brief(
        interview["id"], lang=interview.get("lang") or lang) is not None
    return {"iv": interview, "readiness": readiness, "when": when,
            "at": at, "has_brief": has_brief}


def _fmt_when(interview_at: Optional[str]) -> tuple[str, str]:
    """(display string, validated 'YYYY-MM-DDTHH:MM') from the stored local time.
    The 'red = urgent, within 48h' cue (§5) is decided in the BROWSER: the time
    is the user's local time and the server clock is UTC, so only the browser
    can compare them. Empty/bad → (raw, '')."""
    raw = (interview_at or "").strip()
    if not raw:
        return "", ""
    try:
        dt = datetime.strptime(raw[:16], "%Y-%m-%dT%H:%M")
    except ValueError:
        return raw, ""
    return dt.strftime("%a, %b %-d · %-I:%M %p"), dt.strftime("%Y-%m-%dT%H:%M")


# ---------- Flow A: New Interview ----------

@router.get("/interviews/new")
async def interview_new(request: Request):
    """A1 — entry choice. Three ways in: a Jobot match (status Interviewing), a
    pasted link, or pasted JD text. No resume → a nudge to Profile first."""
    resume, _rh, _rid, _txt = _current()
    matches = db.list_applications(statuses=["interviewing"]) if resume else []
    return templates.TemplateResponse(
        request,
        "pages/interview_new.html",
        {"active_tab": "prep", "has_resume": resume is not None, "matches": matches},
    )


@router.get("/interviews/new/form")
async def interview_new_form(
    request: Request,
    source: str = "paste_text",
    job_id: str = "",
):
    """A2 — the details form, prefilled. `source` ∈ from_match | paste_link |
    paste_text; a from_match `job_id` pulls the stored JD/company/role."""
    prefill = {"company": "", "role_title": "", "jd_text": "", "job_id": ""}
    if source == "from_match" and job_id:
        job = db.get_job(job_id) or {}
        prefill = {
            "company": job.get("company", ""),
            "role_title": job.get("title", ""),
            "jd_text": job.get("description", ""),
            "job_id": job_id,
        }
    return templates.TemplateResponse(
        request,
        "partials/interview_form.html",
        {"source": source, "prefill": prefill,
         "round_types": db.VALID_ROUND_TYPES},
    )


@router.post("/interviews/create")
async def interview_create(
    request: Request,
    company: str = Form(""),
    role_title: str = Form(""),
    jd_text: str = Form(""),
    source_url: str = Form(""),
    job_id: str = Form(""),
    interview_at: str = Form(""),
    round_type: str = Form("screening"),
    round_length_min: str = Form("45"),
    interviewer_title: str = Form(""),
    recruiter_notes: str = Form(""),
    source: str = Form("paste_text"),
):
    """Create the Interview row, then hand off to the generating screen. Company
    OR a JD is the floor — without either there's nothing to build a brief from."""
    _resume, resume_hash, resume_id, _txt = _current()
    if not resume_hash:
        return _error("prep2.err.need_resume")
    company = company.strip()
    jd_text = jd_text.strip()
    source_url = source_url.strip()
    if not company and not jd_text and not source_url:
        return _error("prep2.err.need_input")

    src = source if source in ("from_match", "paste_link", "paste_text") else "paste_text"
    interview_id = db.create_interview(
        resume_hash, company, role_title.strip(), jd_text,
        get_output_language(), src,
        job_id=job_id.strip() or None,
        resume_id=resume_id or None,
        source_url=source_url,
        interview_at=interview_at.strip() or None,
        round_type=round_type.strip(),
        round_length_min=_parse_int(round_length_min, 45),
        interviewer_title=interviewer_title.strip(),
        recruiter_notes=recruiter_notes.strip(),
    )
    return HTMLResponse("", headers={"HX-Redirect": f"/interviews/{interview_id}/generating"})


@router.get("/interviews/{interview_id}/generating")
async def interview_generating(request: Request, interview_id: int):
    """A3 — the generating screen. A checklist ticks client-side while the
    build POST (hx-trigger=load) runs research + P1 and redirects to the Brief."""
    interview = db.get_interview(interview_id)
    if not interview:
        return _redirect("/interviews/new")
    # Already built (revisit / back button) → straight to the brief.
    if prep_brief.read_cached_brief(interview_id) is not None:
        return _redirect(f"/interviews/{interview_id}")
    return templates.TemplateResponse(
        request,
        "pages/interview_generating.html",
        {"active_tab": "prep", "interview": interview},
    )


@router.post("/interviews/{interview_id}/build")
async def interview_build(request: Request, interview_id: int):
    """Fetch company research (Tavily) then P1 Brief, and redirect to the Brief.
    On failure (quota / no résumé), render a retry state in place."""
    interview = db.get_interview(interview_id)
    if not interview:
        return _redirect("/interviews/new")
    _resume, _rh, _rid, resume_text = _current()
    if not resume_text:
        return templates.TemplateResponse(
            request, "partials/interview_build_error.html",
            {"interview_id": interview_id, "reason": "no_resume"})

    lang = interview.get("lang") or get_output_language()

    # "Reading the job": a pasted link with no JD yet → scrape it now and
    # backfill the interview (company/role only when the user left them blank).
    if not (interview.get("jd_text") or "").strip() and (interview.get("source_url") or "").strip():
        interview = await asyncio.to_thread(_scrape_into_interview, interview)

    research = await asyncio.to_thread(
        tavily.search_company_hits, interview.get("company", ""),
        interview.get("role_title", ""))

    make_client = _make_client_factory()
    brief = await pipeline.build_brief(
        interview, resume_text, make_client=make_client, research=research, lang=lang)
    if brief is None:
        return templates.TemplateResponse(
            request, "partials/interview_build_error.html",
            {"interview_id": interview_id, "reason": "generation_failed"})

    # No background toolkit warm-up any more (ADR-057): the ONE toolkit call
    # waits for the candidate's answers to the Brief's fact questions, so it can
    # write specific answers instead of vague ones.
    return HTMLResponse("", headers={"HX-Redirect": f"/interviews/{interview_id}"})


# ---------- the Brief (Screen 2) ----------

@router.get("/interviews/{interview_id}")
async def interview_brief(request: Request, interview_id: int):
    """Brief (Screen 2). Cache-only read — a miss means it was never built, so
    bounce to the generating screen rather than block the page on an LLM call."""
    interview = db.get_interview(interview_id)
    if not interview:
        return _redirect("/interviews/new")
    brief = prep_brief.read_cached_brief(interview_id, lang=interview.get("lang") or None)
    if brief is None:
        return _redirect(f"/interviews/{interview_id}/generating")
    db.touch_interview(interview_id)
    return templates.TemplateResponse(
        request,
        "pages/interview_brief.html",
        {"active_tab": "prep", "interview": interview, "brief": brief,
         "facts": prep_toolkit.read_facts(interview_id), "step": "brief"},
    )


@router.post("/interviews/{interview_id}/facts")
async def interview_facts(request: Request, interview_id: int):
    """Get Ready's Clarify step (ADR-058): save the candidate's answers to the
    clarifying questions (all optional; "Skip" posts none) and go back to Get
    Ready, which then writes the toolkit."""
    if not db.get_interview(interview_id):
        return _redirect("/interviews/new")
    form = await request.form()
    interview = db.get_interview(interview_id)
    lang = interview.get("lang") or None
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    clarify = [q.question for q in (brief.clarify_questions if brief else [])]
    # field ids → facts keys: the Brief's questions (by TEXT — ids are re-used on a
    # rebuild) and the cards' ✎ gaps (gap_key — same key as the inline card field)
    toolkit = prep_toolkit.read_cached_toolkit(
        interview_id, db.list_stories(interview.get("resume_hash", ""), status="saved"), lang=lang, fresh=False)
    keys = {st["id"]: st["key"] for st in (_checkin_steps(brief, toolkit, {}) if brief else [])}
    # Answers MERGE into what's saved: the check-in may show only the open gaps,
    # and Skip never erases anything (a skip wiped Eduardo's answers, 2026-09-29).
    answers = prep_toolkit.read_facts(interview_id)
    if not form.get("skip"):
        for k, v in form.items():
            if k.startswith("fact_") and k[5:] in keys and str(v).strip():
                answers[keys[k[5:]]] = str(v)
    prep_toolkit.save_facts(interview_id, answers, asked=clarify, skipped=bool(form.get("skip")),
                            comps=_gap_competencies(toolkit))
    return RedirectResponse(f"/interviews/{interview_id}/get-ready", status_code=303)


@router.post("/interviews/{interview_id}/facts/add")
async def interview_facts_add(interview_id: int, key: str = Form(""), answer: str = Form("")):
    """Fill one ✎ gap right on an answer card: append {"<card question> — <hint>":
    answer} to the facts, keeping every existing answer and the asked-marker.
    The cards use it on the next rebuild ("Update my cards")."""
    interview = db.get_interview(interview_id)
    if not interview or not key.strip() or not answer.strip():
        return Response(status_code=400)
    lang = interview.get("lang") or None
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    toolkit = prep_toolkit.read_cached_toolkit(
        interview_id, db.list_stories(interview.get("resume_hash", ""), status="saved"), lang=lang, fresh=False)
    facts = prep_toolkit.read_facts(interview_id)
    facts[key.strip()[:300]] = answer.strip()
    prep_toolkit.save_facts(interview_id, facts,
                            asked=[q.question for q in (brief.clarify_questions if brief else [])],
                            comps=_gap_competencies(toolkit))
    return Response(status_code=204)


@router.get("/interviews/{interview_id}/get-ready")
async def interview_get_ready(request: Request, interview_id: int):
    """Get Ready (Screen 3) — three tabs (Answer cards · Your stories · Questions
    to ask) from ONE cached toolkit (ADR-057), rendered in full. Not built yet →
    the page shows one loading state that POSTs /toolkit/build and reloads."""
    interview = db.get_interview(interview_id)
    if not interview:
        return _redirect("/interviews/new")
    lang = interview.get("lang") or get_output_language()
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    if brief is None:
        return _redirect(f"/interviews/{interview_id}/generating")
    db.touch_interview(interview_id)
    stories = db.list_stories(interview["resume_hash"], status="saved")
    # The quick questions come first (ADR-058 rev. 2026-10-01): until this set is
    # answered or skipped, Get Ready hands off to the focused check-in page.
    # (?clarify=1 is the old "Edit clarifications" link — same destination.)
    if request.query_params.get("clarify") == "1" or (
            brief.clarify_questions and not prep_toolkit.facts_submitted(
                interview_id, [q.question for q in brief.clarify_questions])):
        return _redirect(f"/interviews/{interview_id}/check-in")
    toolkit = prep_toolkit.read_cached_toolkit(interview_id, stories, lang=lang)
    ctx = {"active_tab": "prep", "interview": interview, "step": "get_ready", "toolkit": toolkit,
           "brief": brief}
    if toolkit is not None:
        ctx.update(_get_ready_ctx(interview, brief, toolkit, stories))
    return templates.TemplateResponse(request, "pages/interview_get_ready.html", ctx)


@router.get("/interviews/{interview_id}/check-in")
async def interview_checkin(request: Request, interview_id: int):
    """A few quick questions (ADR-058 rev.) — the bridge from the Brief to the
    answer cards: one question at a time, about the HOW behind résumé items.
    Also the target of "Improve my answers" (prefilled; rewrites the cards)."""
    interview = db.get_interview(interview_id)
    if not interview:
        return _redirect("/interviews/new")
    lang = interview.get("lang") or get_output_language()
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    if brief is None:
        return _redirect(f"/interviews/{interview_id}/generating")
    if not brief.clarify_questions:
        return _redirect(f"/interviews/{interview_id}/get-ready")
    stories = db.list_stories(interview["resume_hash"], status="saved")
    toolkit = prep_toolkit.read_cached_toolkit(interview_id, stories, lang=lang, fresh=False)
    facts = prep_toolkit.read_facts(interview_id)
    steps = _checkin_steps(brief, toolkit, facts)
    return templates.TemplateResponse(request, "pages/interview_checkin.html", {
        "active_tab": "prep", "interview": interview, "step": "get_ready", "brief": brief,
        "checkin_steps": steps, "facts": facts, "improving": toolkit is not None})


def _gap_competencies(toolkit) -> dict[str, str]:
    """{gap key: competency id of its card} for the current cards."""
    if not toolkit:
        return {}
    comp = {q.text: q.competency_id for q in toolkit.questions}
    return {g["key"]: comp.get(g["card"]) or "" for g in prep_toolkit.card_gaps(toolkit)}


def _checkin_steps(brief, toolkit, facts: dict) -> list[dict]:
    """What the check-in asks (2026-10-01): the Brief's questions not answered
    yet + every ✎ gap still open on the cards — so "Improve my answers · n gaps"
    opens exactly those n. Nothing open → all the Brief's questions, prefilled
    (edit mode). Each step: {id, key, question, example, card}."""
    clar = [{"id": q.id, "key": q.question, "question": q.question, "example": q.example, "card": ""}
            for q in brief.clarify_questions]
    gaps = [{"id": f"g{i + 1}", **g} for i, g in enumerate(prep_toolkit.card_gaps(toolkit))] if toolkit else []
    open_steps = [st for st in clar + gaps if not facts.get(st["key"])]
    return open_steps or clar


@router.post("/interviews/{interview_id}/toolkit/build")
async def toolkit_build(request: Request, interview_id: int):
    """Write the toolkit (the one call) then reload Get Ready. A failure renders
    an honest retry state in place."""
    interview = db.get_interview(interview_id)
    if not interview:
        return _redirect("/interviews/new")
    lang = interview.get("lang") or get_output_language()
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    _resume, _rh, _rid, resume_text = _current()
    if brief is None or not resume_text:
        return _toolkit_unavailable(request)
    stories = db.list_stories(interview["resume_hash"], status="saved")
    toolkit = await pipeline.run_toolkit(
        interview, brief, resume_text, make_client=_make_client_factory(),
        stories=stories, lang=lang)
    if toolkit is None:
        return _toolkit_unavailable(request)
    return HTMLResponse("", headers={"HX-Redirect": f"/interviews/{interview_id}/get-ready"})


def _get_ready_ctx(interview: dict, brief, toolkit, stories: list[dict]) -> dict:
    """Join the toolkit with the Story Bank, the brief and the candidate's card
    ratings for the three tabs."""
    reviews = db.latest_card_reviews(interview["id"])
    frame_tpl = templates.env.get_template("partials/answer_frame.html")
    cards = []
    for q in toolkit.questions:
        r = reviews.get(q.id)
        cards.append({
            "id": q.id, "text": q.text, "type": _t("prep2.qtype." + q.type),
            "why": q.why_they_ask, "follow_up": q.follow_up,
            # the skeleton back, rendered once server-side (escaped; hints → chips)
            "frame_html": frame_tpl.render(frame=q.frame, point=q.point_to_land) if q.frame else "",
            "needs_input": q.needs_input, "point": q.point_to_land,
            # a rating only counts for the SAME question text (a rebuild re-uses ids)
            "rating": r["rating"] if r and r["question_text"] == q.text else None,
        })
    story_by_id = {str(s["id"]): s for s in stories}
    picks = {p.competency_id: p for p in toolkit.stories}
    story_rows = []
    for c in brief.competencies:
        p = picks.get(c.id)
        story = story_by_id.get(p.story_id) if (p and p.story_id) else None
        star = story or (p.draft if p else None)
        story_rows.append({
            "competency": c, "pick": p, "story": story, "draft": None if story else (p.draft if p else None),
            "strength": prep_story_bank.strength_check(star) if star else None,
        })
    # open gaps = ✎ slots not answered yet — the same list the check-in will show
    facts = prep_toolkit.read_facts(interview["id"])
    gaps = sum(1 for g in prep_toolkit.card_gaps(toolkit) if not facts.get(g["key"]))
    return {"cards": cards, "story_rows": story_rows, "ask": toolkit.questions_to_ask, "gaps": gaps}


@router.post("/interviews/{interview_id}/cards/{question_id}/review")
async def card_review(interview_id: int, question_id: str,
                      rating: str = Form(""), question_text: str = Form("")):
    """Self-rating of one answer card (ADR-056) — data for the candidate's weak
    spots and the "practice what I missed" session."""
    if not db.get_interview(interview_id):
        return Response(status_code=404)
    ok = db.save_card_review(interview_id, question_id, question_text, rating)
    return Response(status_code=204 if ok else 400)


def _missed_question_ids(interview_id: int, questions: list[dict]) -> set[str]:
    """Question ids whose latest self-rating is "missed" (same text only)."""
    texts = {q.get("id"): q.get("text") for q in questions}
    return {qid for qid, r in db.latest_card_reviews(interview_id).items()
            if r["rating"] == "missed" and texts.get(qid) == r["question_text"]}


def _toolkit_unavailable(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "partials/toolkit_unavailable.html", {})


# ---------- Practice (Screen 4) — turn-based session (voice layer lands later) ----------

@router.get("/interviews/{interview_id}/practice")
async def practice_entry(request: Request, interview_id: int):
    """C1 consent (once, account-level) then C2 pre-session setup. Brief must
    exist; a miss bounces to generating."""
    interview = db.get_interview(interview_id)
    if not interview:
        return _redirect("/interviews/new")
    lang = interview.get("lang") or None
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    if brief is None:
        return _redirect(f"/interviews/{interview_id}/generating")
    if app_settings.get(PRACTICE_CONSENT_KEY, "") != "1":
        return templates.TemplateResponse(
            request, "pages/practice_consent.html",
            {"active_tab": "prep", "interview": interview, "step": "practice"})
    # Answer cards rated "missed" in Get Ready (ADR-056) → a pre-selected focus.
    # Cache-only read of P2: setup must never trigger a generation.
    cached = prep_toolkit.read_cached_toolkit(
        interview_id, db.list_stories(interview["resume_hash"], status="saved"), lang=lang, fresh=False)
    qlist = [q.to_dict() for q in cached.questions] if cached else []
    missed_count = len(_missed_question_ids(interview_id, qlist))
    focus_q = request.query_params.get("focus", "")
    if focus_q in {c.id for c in brief.competencies}:
        focus_default = focus_q    # "Drill <weakest>" from Feedback (ADR-059)
    else:
        focus_default = "__missed__" if (missed_count and focus_q != "all") else ""
    return templates.TemplateResponse(
        request, "pages/practice_setup.html",
        {"active_tab": "prep", "interview": interview, "step": "practice",
         "missed_count": missed_count, "focus_default": focus_default,
         "competencies": [c.to_dict() for c in brief.competencies],
         "voice_enabled": prep_live.is_enabled(),
         "voices": prep_live.VOICES, "default_voice": prep_live.DEFAULT_VOICE,
         "personalities": prep_live.PERSONALITIES, "default_personality": prep_live.DEFAULT_PERSONALITY})


@router.post("/interviews/{interview_id}/practice/consent")
async def practice_consent(request: Request, interview_id: int):
    """C1 — record consent (account-level) and go to setup."""
    app_settings.set(PRACTICE_CONSENT_KEY, "1")
    return HTMLResponse("", headers={"HX-Redirect": f"/interviews/{interview_id}/practice"})


@router.get("/interviews/practice/voice-sample/{voice}")
async def practice_voice_sample(request: Request, voice: str):
    """A short WAV sample of a coach voice, so the picker can preview it. Cached
    on disk after the first generation (ADR-051)."""
    wav = await prep_live.voice_sample_wav(voice)
    if wav is None:
        return HTMLResponse("", status_code=404)
    return Response(content=wav, media_type="audio/wav",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.post("/interviews/{interview_id}/practice/start")
async def practice_start(
    request: Request,
    interview_id: int,
    mode: str = Form("simulate"),
    length: str = Form("standard"),
    focus: str = Form(""),
    channel: str = Form("text"),
    voice: str = Form(""),
    personality: str = Form(""),
):
    """C2 → create the session with a frozen picked question set (from cached P2),
    then go to the runner (voice when chosen + enabled, else text)."""
    interview = db.get_interview(interview_id)
    if not interview:
        return _redirect("/interviews/new")
    lang = interview.get("lang") or get_output_language()
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    if brief is None:
        return _error("prep2.err.need_brief")
    competencies = [c.to_dict() for c in brief.competencies]
    # The toolkit's questions (ADR-057); build it on a cold miss so Practice
    # always has a set.
    stories = db.list_stories(interview["resume_hash"], status="saved")
    toolkit = prep_toolkit.read_cached_toolkit(interview_id, stories, lang=lang, fresh=False)
    if toolkit is None:
        _resume, _rh, _rid, resume_text = _current()
        toolkit = await pipeline.run_toolkit(
            interview, brief, resume_text, make_client=_make_client_factory(),
            stories=stories, lang=lang)
    qdicts = [q.to_dict() for q in (toolkit.questions if toolkit else [])]
    if not qdicts:
        return _error("prep2.err.questions_failed")
    missed = focus.strip() == "__missed__"
    picked = prep_practice.pick_session_questions(
        qdicts, length=length,
        focus_competency=None if missed else (focus.strip() or None),
        prefer_ids=_missed_question_ids(interview_id, qdicts) if missed else None)
    # Voice + personality are decoupled: `persona` column stores the personality id.
    personality_id = personality if personality in prep_live.PERSONALITIES else prep_live.DEFAULT_PERSONALITY
    voice_id = voice if voice in prep_live.VOICES else prep_live.DEFAULT_VOICE
    sid = db.create_practice_session(
        interview_id, mode=mode, length=length,
        focus_competency=None if missed else (focus.strip() or None),
        persona=personality_id, voice=voice_id,
        questions=picked)
    dest = "voice" if (channel == "voice" and prep_live.is_enabled()) else str(sid)
    tail = f"{sid}/voice" if dest == "voice" else str(sid)
    return HTMLResponse("", headers={"HX-Redirect": f"/interviews/{interview_id}/practice/{tail}"})


@router.get("/interviews/{interview_id}/practice/{session_id}")
async def practice_run(request: Request, interview_id: int, session_id: int):
    """C3 — the runner. Renders the current (first unanswered) question, or the
    'building' hand-off once every question is answered."""
    interview = db.get_interview(interview_id)
    session = db.get_practice_session(session_id)
    if not interview or not session or session["interview_id"] != interview_id:
        return _redirect(f"/interviews/{interview_id}")
    if session["status"] == "done":
        return _redirect(f"/interviews/{interview_id}/practice/{session_id}/feedback")
    return templates.TemplateResponse(
        request, "pages/practice_run.html",
        {"active_tab": "prep", "interview": interview, "session": session,
         "step": "practice", "turn": _current_turn(interview, session)})


@router.get("/interviews/{interview_id}/practice/{session_id}/voice")
async def practice_voice(request: Request, interview_id: int, session_id: int):
    """The live-voice runner (ADR-052) — the browser connects directly to Gemini
    Live. Falls back to the text runner if voice isn't enabled."""
    interview = db.get_interview(interview_id)
    session = db.get_practice_session(session_id)
    if not interview or not session or session["interview_id"] != interview_id:
        return _redirect(f"/interviews/{interview_id}")
    if session["status"] == "done":
        return _redirect(f"/interviews/{interview_id}/practice/{session_id}/feedback")
    if not prep_live.is_enabled():
        return _redirect(f"/interviews/{interview_id}/practice/{session_id}")
    lab = prep_voice_lab.live_override()   # REQ-046: -edu voice playground override
    return templates.TemplateResponse(
        request, "pages/practice_live.html",
        {"active_tab": "prep", "interview": interview, "session": session,
         "step": "practice", "live_model": prep_live.live_model(),
         "coach_name": prep_live.coach_name(lab["voice"] if lab else (session.get("voice") or prep_live.DEFAULT_VOICE)),
         "lab": lab, "lab_line": prep_voice_lab.delivery_line(lab) if lab else "",
         "keep_coach_audio": prep_live.save_audio_enabled()})


@router.post("/interviews/{interview_id}/practice/{session_id}/live-token")
async def practice_live_token(request: Request, interview_id: int, session_id: int):
    """Mint a single-use ephemeral token so the browser can connect directly to
    Gemini Live with our pinned config (ADR-052). 404 → the page falls back to
    the text runner."""
    interview = db.get_interview(interview_id)
    session = db.get_practice_session(session_id)
    if not interview or not session or session["interview_id"] != interview_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    lang = interview.get("lang") or get_output_language()
    result = await asyncio.to_thread(
        prep_live.create_ephemeral_token, interview, session, lang=lang)
    if not result:
        return JSONResponse({"error": "voice_unavailable"}, status_code=404)
    token, context = result
    return JSONResponse({"token": token, "model": prep_live.live_model(), "context": context})


@router.post("/interviews/{interview_id}/practice/{session_id}/audio")
async def practice_audio(
    request: Request,
    interview_id: int,
    session_id: int,
    audio: UploadFile = File(None),
    coach_audio: UploadFile = File(None),
    turns: str = Form("[]"),
    candidate_seconds: str = Form("0"),
    answer_bounds: str = Form("[]"),
):
    """End of a voice session: store the conversation transcript, then build the
    debrief. Preferred path — score from the uploaded WAV (delivery + content read
    from the ACTUAL audio; the audio is sent to Gemini transiently + never stored,
    GOV-008). Falls back to the transcript-based debrief if there's no audio or
    audio scoring fails. Marks done → client redirects to Feedback."""
    interview = db.get_interview(interview_id)
    session = db.get_practice_session(session_id)
    if not interview or not session or session["interview_id"] != interview_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    feedback_url = f"/interviews/{interview_id}/practice/{session_id}/feedback"
    if session["status"] == "done":
        return JSONResponse({"redirect": feedback_url})

    turn_list = _clean_turns(_parse_json(turns))
    secs = _parse_int(candidate_seconds, 0)
    db.save_practice_transcript(session_id, turn_list)
    lang = interview.get("lang") or get_output_language()
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    competencies = [c.to_dict() for c in brief.competencies] if brief else []
    questions = session.get("questions") or []

    wav = await audio.read() if audio is not None else b""
    coach_wav = await coach_audio.read() if coach_audio is not None else b""
    # -edu-only debug persistence (ADR-055): keep the RAW coach WAV + candidate WAV so
    # Eduardo can A/B fidelity vs Google's playground and I can measure pacing. Off in prod.
    if prep_live.save_audio_enabled():
        _persist_practice_audio(session_id, coach_wav, wav)
    # Speaking time is measured from the recorded audio (ADR-070); the browser's
    # level-gated count is only a fallback when no audio arrived / none stood out.
    bounds = _parse_json(answer_bounds)
    measured, answer_secs = (await asyncio.to_thread(
        prep_audio_metrics.speaking_profile_wav, wav, bounds if isinstance(bounds, list) else [])
        if wav else (0, []))
    secs = measured or secs
    debrief = None
    if wav:
        debrief = await asyncio.to_thread(
            prep_audio_score.score_from_audio, wav, questions, competencies,
            turns=turn_list, candidate_seconds=secs, lang=lang)
    if debrief is None:
        # Fallback: transcript-based debrief + code delivery over the "you" turns.
        client = GeminiClient(api_key=resolve_api_key())
        d = await asyncio.to_thread(
            prep_practice.session_debrief_from_transcript,
            turn_list, questions, competencies, client, lang=lang)
        said = " ".join(t["text"] for t in turn_list if t["role"] == "you")
        debrief = {**(d.to_dict() if d else {}),
                   "delivery": prep_audio_score.code_delivery(said, secs)}
    if answer_secs and isinstance(debrief.get("delivery"), dict):
        debrief["delivery"]["answer_seconds"] = answer_secs   # per-answer length (ADR-071)
    db.save_practice_debrief(session_id, debrief)
    return JSONResponse({"redirect": feedback_url})


def _persist_practice_audio(session_id: int, coach_wav: bytes, candidate_wav: bytes) -> None:
    """Write the raw coach WAV + candidate WAV to the -edu volume (ADR-055). Best-effort:
    never let a debug save break the session end."""
    import datetime as _dt
    try:
        d = prep_live.saved_audio_dir()
        d.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        if coach_wav:
            (d / f"s{session_id}-{ts}-coach.wav").write_bytes(coach_wav)
        if candidate_wav:
            (d / f"s{session_id}-{ts}-candidate.wav").write_bytes(candidate_wav)
    except Exception:  # noqa: BLE001 — debug-only persistence, never fatal
        pass


@router.get("/interviews/practice/audio")
async def practice_audio_list(request: Request):
    """List saved practice audio (ADR-055, -edu debug). 404 when the flag is off."""
    if not prep_live.save_audio_enabled():
        return HTMLResponse("", status_code=404)
    d = prep_live.saved_audio_dir()
    files = sorted((f.name for f in d.glob("*.wav")), reverse=True) if d.exists() else []
    links = "".join(
        f'<li><a href="/interviews/practice/audio/{f}">{f}</a> '
        f'({(d / f).stat().st_size // 1024} KB)</li>' for f in files)
    return HTMLResponse(f"<h1>Saved practice audio</h1><ul>{links or '<li>none yet</li>'}</ul>")


@router.get("/interviews/practice/audio/{filename}")
async def practice_audio_download(request: Request, filename: str):
    """Serve one saved WAV (ADR-055, -edu debug). Name-sanitized; flag-gated."""
    if not prep_live.save_audio_enabled():
        return HTMLResponse("", status_code=404)
    from pathlib import Path as _P
    safe = _P(filename).name  # strip any path traversal
    fp = prep_live.saved_audio_dir() / safe
    if safe != filename or not fp.is_file() or fp.suffix != ".wav":
        return HTMLResponse("", status_code=404)
    return Response(content=fp.read_bytes(), media_type="audio/wav",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


def _parse_json(raw):
    try:
        import json as _json
        return _json.loads(raw)
    except (TypeError, ValueError):
        return None


def _clean_turns(raw) -> list[dict]:
    """Keep well-formed {role: coach|you, text} turns from the client body."""
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for it in raw:
        if not isinstance(it, dict):
            continue
        role = "coach" if it.get("role") == "coach" else "you"
        text = str(it.get("text", "")).strip()
        if text:
            out.append({"role": role, "text": text[:4000]})
    return out


@router.post("/interviews/{interview_id}/practice/{session_id}/answer")
async def practice_answer(
    request: Request,
    interview_id: int,
    session_id: int,
    transcript: str = Form(""),
    seconds: str = Form("0"),
):
    """Store one answer + code delivery metrics, then swap in the next turn (or
    the 'building' hand-off when the session is complete)."""
    interview = db.get_interview(interview_id)
    session = db.get_practice_session(session_id)
    if not interview or not session or session["interview_id"] != interview_id:
        return HTMLResponse("")
    answered = db.list_practice_answers(session_id)
    questions = session.get("questions") or []
    pos = len(answered)
    if pos < len(questions):
        q = questions[pos]
        secs = _parse_int(seconds, 0)
        target = prep_practice.target_seconds_for(q)
        delivery = prep_practice.delivery_metrics(transcript, secs, target)
        db.add_practice_answer(
            session_id, position=pos, question_id=str(q.get("id", "")),
            question_text=str(q.get("text", "")), competency_id=q.get("competency_id"),
            transcript=transcript.strip(), seconds=secs, delivery=delivery)
    # Re-read to decide the next turn.
    session = db.get_practice_session(session_id)
    turn = _current_turn(interview, session)
    if turn is None:
        db.set_practice_status(session_id, "building")
        return templates.TemplateResponse(
            request, "partials/practice_building.html",
            {"interview": interview, "session_id": session_id})
    return templates.TemplateResponse(
        request, "partials/practice_turn.html",
        {"interview": interview, "session": session, "turn": turn})


@router.post("/interviews/{interview_id}/practice/{session_id}/build")
async def practice_build(request: Request, interview_id: int, session_id: int):
    """C4 — run P8 on each answer then P9 for the debrief, persist, and redirect
    to Feedback. Never saves an empty debrief: on failure the session stays
    open and the user gets Retry. Never runs twice for one session."""
    interview = db.get_interview(interview_id)
    session = db.get_practice_session(session_id)
    if not interview or not session or session["interview_id"] != interview_id:
        return _redirect(f"/interviews/{interview_id}")
    feedback_url = f"/interviews/{interview_id}/practice/{session_id}/feedback"
    if session["status"] == "done":
        return HTMLResponse("", headers={"HX-Redirect": feedback_url})
    ctx = {"interview": interview, "session_id": session_id}
    if session_id in _BUILDS_IN_FLIGHT:   # a refresh mid-build → wait, don't pay twice
        return templates.TemplateResponse(request, "partials/practice_building.html", {**ctx, "wait": True})
    _BUILDS_IN_FLIGHT.add(session_id)
    try:
        debrief = await _build_typed_debrief(interview, session)
    finally:
        _BUILDS_IN_FLIGHT.discard(session_id)
    if debrief is None:
        return templates.TemplateResponse(request, "partials/practice_build_failed.html", ctx)
    db.save_practice_debrief(session_id, debrief.to_dict())
    return HTMLResponse("", headers={"HX-Redirect": feedback_url})


# Sessions whose typed debrief is being built right now (single-process app).
_BUILDS_IN_FLIGHT: set[int] = set()


async def _build_typed_debrief(interview: dict, session: dict):
    """P8 for each answer that has no evaluation yet (a Retry doesn't re-pay for
    the ones that worked), then P9. None when nothing could be evaluated."""
    interview_id, session_id = interview["id"], session["id"]
    lang = interview.get("lang") or get_output_language()
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    comp_by_id = {c.id: c.to_dict() for c in brief.competencies} if brief else {}
    stories = db.list_stories(interview["resume_hash"], status="saved")
    mapping = prep_toolkit.read_cached_mapping(interview_id, stories, lang=lang) or []
    story_by_comp = {m.competency_id: next((s for s in stories if str(s["id"]) == m.story_id), None)
                     for m in mapping if m.story_id}

    client = GeminiClient(api_key=resolve_api_key())
    # Keep the real question type per position (openers/technical have different
    # speaking targets) instead of assuming behavioral.
    q_by_pos = {i: q for i, q in enumerate(session.get("questions") or [])}
    answers = db.list_practice_answers(session_id)
    evals, deliveries = [], []
    for a in answers:
        if a.get("delivery"):
            deliveries.append(a["delivery"])
        if a.get("eval"):   # already evaluated on an earlier attempt
            evals.append(a["eval"])
            continue
        src_q = q_by_pos.get(a["position"], {})
        q = {"id": a["question_id"], "text": a["question_text"],
             "type": src_q.get("type", "behavioral"), "competency_id": a["competency_id"]}
        comp = comp_by_id.get(a["competency_id"])
        story = story_by_comp.get(a["competency_id"])
        ev = await asyncio.to_thread(
            prep_practice.evaluate_answer, q, comp, story, a["transcript"], client,
            answer_seconds=a["seconds"],
            target_seconds=prep_practice.target_seconds_for(q), lang=lang)
        if ev is not None:
            db.save_practice_eval(a["id"], ev.to_dict())
            evals.append(ev.to_dict())

    return await asyncio.to_thread(
        prep_practice.session_debrief, evals, deliveries,
        [c.to_dict() for c in brief.competencies] if brief else [], client, lang=lang,
        asked_ids=prep_practice.asked_competency_ids(session.get("questions") or []))


@router.get("/interviews/{interview_id}/practice/{session_id}/feedback")
async def practice_feedback(request: Request, interview_id: int, session_id: int):
    """Feedback (Screen 5) — debrief + per-answer evals + delivery strip + the
    readiness now."""
    interview = db.get_interview(interview_id)
    session = db.get_practice_session(session_id)
    if not interview or not session or session["interview_id"] != interview_id:
        return _redirect(f"/interviews/{interview_id}")
    if session["status"] != "done":
        return _redirect(f"/interviews/{interview_id}/practice/{session_id}")
    lang = interview.get("lang") or None
    brief = prep_brief.read_cached_brief(interview_id, lang=lang)
    comp_names = {c.id: c.name for c in brief.competencies} if brief else {}
    answers = db.list_practice_answers(session_id)
    readiness = prep_readiness.compute(interview, lang=lang)
    delta = prep_session_score.delta_vs_previous(
        db.list_practice_sessions(interview_id), session_id)
    gauges = _delivery_gauges(session, answers)
    return templates.TemplateResponse(
        request, "pages/practice_feedback.html",
        {"active_tab": "prep", "interview": interview, "session": session,
         "answers": answers, "comp_names": comp_names, "readiness": readiness,
         "delta": delta, "gauges": gauges, "step": "feedback"})


def _delivery_gauges(session: dict, answers: list[dict]) -> list[dict]:
    """REQ-043 — the Delivery panel's gauges from MEASURED numbers: voice uses the
    session-level code delivery; typed sums the per-answer deliveries."""
    dv = (session.get("debrief") or {}).get("delivery") or {}
    if session.get("transcript") and dv.get("word_count") is not None:
        per_answer = dv.get("answer_seconds")   # absent on sessions before ADR-071
        return prep_session_score.delivery_gauges(
            words=int(dv.get("word_count") or 0), seconds=int(dv.get("seconds") or 0),
            fillers=int(dv.get("filler_count") or 0),
            answer_seconds=[int(x) for x in per_answer if isinstance(x, (int, float))]
            if isinstance(per_answer, list) else [])
    ds = [a["delivery"] for a in answers if a.get("delivery")]
    return prep_session_score.delivery_gauges(
        words=sum(int(d.get("word_count") or 0) for d in ds),
        seconds=sum(int(d.get("seconds") or 0) for d in ds),
        fillers=sum(int(d.get("filler_count") or 0) for d in ds),
        answer_seconds=[int(d.get("seconds") or 0) for d in ds])


def _current_turn(interview: dict, session: dict) -> Optional[dict]:
    """The current question + its study cue, or None when all are answered.
    In Study mode the cue carries the competency's 'what good looks like' + the
    mapped story title; Simulate hides cues (design brief §Practice)."""
    questions = session.get("questions") or []
    answered = len(db.list_practice_answers(session["id"]))
    if answered >= len(questions):
        return None
    q = questions[answered]
    cue = None
    if session.get("mode") == "study":
        lang = interview.get("lang") or None
        brief = prep_brief.read_cached_brief(interview["id"], lang=lang)
        comp = next((c for c in (brief.competencies if brief else [])
                     if c.id == q.get("competency_id")), None)
        story_title = None
        if q.get("competency_id"):
            stories = db.list_stories(interview["resume_hash"], status="saved")
            mapping = prep_toolkit.read_cached_mapping(interview["id"], stories, lang=lang) or []
            m = next((m for m in mapping if m.competency_id == q.get("competency_id") and m.story_id), None)
            if m:
                s = next((s for s in stories if str(s["id"]) == m.story_id), None)
                story_title = s["title"] if s else None
        cue = {"what_good": comp.what_good_looks_like if comp else "",
               "competency": comp.name if comp else "", "story_title": story_title}
    return {"index": answered, "total": len(questions), "question": q, "cue": cue}


# ---------- helpers ----------

def _scrape_into_interview(interview: dict) -> dict:
    """Scrape the pasted posting URL and backfill jd_text (+ company/role when
    blank), persist, and return the refreshed row. On any scrape failure the
    interview is returned unchanged — P1 still builds from company/role alone
    (grounded-or-honest, never a fabricated JD)."""
    from core.jobs.from_url import UrlExtractError, job_from_url  # local: heavy import

    url = (interview.get("source_url") or "").strip()
    try:
        client = GeminiClient(api_key=resolve_api_key())
        job = job_from_url(url, client)
    except (UrlExtractError, Exception):  # noqa: BLE001 — degrade to JD-less brief
        return interview
    patch = {"jd_text": (job.get("description") or "").strip()}
    if not (interview.get("company") or "").strip() and job.get("company"):
        patch["company"] = job["company"].strip()
    if not (interview.get("role_title") or "").strip() and job.get("title"):
        patch["role_title"] = job["title"].strip()
    if not patch["jd_text"]:
        return interview
    db.update_interview_fields(interview["id"], patch)
    return db.get_interview(interview["id"]) or interview


def _parse_int(raw: str, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        return default
