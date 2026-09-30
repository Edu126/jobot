"""Prep toolkit orchestrator (ADR-048, REQ-041) — sequences the P1–P4 fan-out
behind the New-Interview "generating" screen (Flow A3).

Order is load-bearing: **P1 Brief first** (the user waits on it — the Brief
screen appears when it's ready), then **P2 Questions ∥ P3 Story-mapping** off
P1's competencies, then **P4 Answer cards** — it answers the P2 questions using
the P3 stories, so it needs both (ADR-056). All in the background ("Toolkit
still loading"). The blocking Gemini calls run in threads (`asyncio.to_thread`)
so P2 and P3 overlap on network wait.

Each stage gets its OWN GeminiClient from `make_client` — a shared client has
mutable per-call state (`last_model_used`) that concurrent calls would clobber,
mis-attributing which model served which artifact. Separate instances still
share the DB-backed daily quota, so parallelism never bypasses the cap.

A sub-call that fails degrades to None (partial toolkit — some tabs empty),
matching each module's own grounded-or-none stance; it never sinks the whole
build. Status advances created → brief_ready → toolkit_ready as it goes.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Optional

from core import db
from core.llm.gemini import GeminiClient

from . import brief as p1
from . import flashcards as p4
from . import mapping as p3
from . import questions as p2

MakeClient = Callable[[], GeminiClient]


@dataclass
class ToolkitResult:
    brief: Optional[p1.Brief] = None
    questions: Optional[list[p2.Question]] = None
    mapping: Optional[list[p3.Mapping]] = None
    flashcards: Optional[p4.StudyKit] = None

    @property
    def brief_ready(self) -> bool:
        return self.brief is not None and not self.brief.is_empty()


async def build_toolkit(
    interview: dict,
    resume_text: str,
    *,
    make_client: MakeClient,
    stories: Optional[list[dict]] = None,
    research: Optional[list[dict]] = None,
    lang: Optional[str] = None,
    use_cache: bool = True,
    update_status: bool = True,
    path=db.DB_PATH,
) -> ToolkitResult:
    """Full build: P1, then P2 ∥ P3, then P4. Returns whatever succeeded.
    If P1 yields no usable brief, the fan-out is skipped (nothing to hang it
    on) and the result carries only `brief=None`."""
    brief = await _run_brief(
        interview, resume_text, make_client,
        research=research, lang=lang, use_cache=use_cache, path=path)
    if brief is None or brief.is_empty():
        return ToolkitResult(brief=None)

    if update_status and interview.get("id"):
        db.update_interview_status(interview["id"], "brief_ready", path=path)

    q, m, f = await fan_out_toolkit(
        interview, brief, resume_text, make_client=make_client,
        stories=stories, lang=lang, use_cache=use_cache, path=path)

    if update_status and interview.get("id"):
        db.update_interview_status(interview["id"], "toolkit_ready", path=path)

    return ToolkitResult(brief=brief, questions=q, mapping=m, flashcards=f)


async def build_brief(
    interview: dict,
    resume_text: str,
    *,
    make_client: MakeClient,
    research: Optional[list[dict]] = None,
    lang: Optional[str] = None,
    use_cache: bool = True,
    update_status: bool = True,
    path=db.DB_PATH,
) -> Optional[p1.Brief]:
    """Just P1 — the synchronous step the generating screen waits on before it
    shows the Brief and kicks the fan-out into the background. Advances status
    to brief_ready on success."""
    brief = await _run_brief(
        interview, resume_text, make_client,
        research=research, lang=lang, use_cache=use_cache, path=path)
    if brief is not None and not brief.is_empty() and update_status and interview.get("id"):
        db.update_interview_status(interview["id"], "brief_ready", path=path)
    return brief if (brief and not brief.is_empty()) else None


async def fan_out_toolkit(
    interview: dict,
    brief: p1.Brief,
    resume_text: str,
    *,
    make_client: MakeClient,
    stories: Optional[list[dict]] = None,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> tuple[Optional[list[p2.Question]], Optional[list[p3.Mapping]], Optional[p4.StudyKit]]:
    """P2 ∥ P3 off an already-built brief, then P4 on their output — the
    background stage. A route that already holds the brief (from cache) calls
    this directly. Returns (questions, mapping, answer_kit); any element is None
    if that call failed (P4 is skipped when P2 produced no questions)."""
    competencies = [c.to_dict() for c in brief.competencies]
    brief_dict = brief.to_dict_for_cache()
    story_list = stories or []

    results = await asyncio.gather(
        asyncio.to_thread(
            p2.get_or_generate_questions, interview, competencies, make_client(),
            lang=lang, use_cache=use_cache, path=path),
        asyncio.to_thread(
            p3.get_or_generate_mapping, interview, competencies, story_list, make_client(),
            lang=lang, use_cache=use_cache, path=path),
        return_exceptions=True,
    )
    # A raised exception in any branch degrades to None — a partial toolkit is
    # fine (the tab renders empty); one bad call must not sink the others.
    questions, mapping = (None if isinstance(r, BaseException) else r for r in results)

    kit = None
    if questions:
        try:
            kit = await asyncio.to_thread(
                p4.get_or_generate_answers, interview, brief_dict,
                [q.to_dict() for q in questions], [m.to_dict() for m in (mapping or [])],
                story_list, resume_text, make_client(),
                lang=lang, use_cache=use_cache, path=path)
        except Exception:  # noqa: BLE001 — same degrade-to-None contract
            kit = None
    return questions, mapping, kit  # type: ignore[return-value]


async def _run_brief(
    interview: dict,
    resume_text: str,
    make_client: MakeClient,
    *,
    research: Optional[list[dict]],
    lang: Optional[str],
    use_cache: bool,
    path,
) -> Optional[p1.Brief]:
    return await asyncio.to_thread(
        p1.get_or_generate_brief, interview, resume_text, make_client(),
        research=research or [], lang=lang, use_cache=use_cache, path=path)
