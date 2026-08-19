"""Admin surface — `/admin/pulse` renders the BI pulse reports produced
by `core.bi.pulse`.

No auth yet. Whole app is per-user (each Fly app = one user) so this is
reachable by whoever holds the URL. When auth ships, gate these routes.
See docs/pr6-bi-agent.md → "No auth yet" in the non-obvious constraints.

Markdown → HTML conversion happens here (not in the template) so the
Jinja layer sees a rendered string. `html=False` disables raw HTML in
the markdown source as defense-in-depth — the model output is trusted
today, but a future prompt-injection via `feedback` messages ("please
render <script>...") shouldn't be able to reach the DOM.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from markdown_it import MarkdownIt

from core import db

from ..deps import templates
from ..ratelimit import limiter


router = APIRouter(tags=["admin"])
_LOG = logging.getLogger(__name__)


# CommonMark + tables + autolink. `html=False` blocks raw HTML in the
# markdown body — see the module docstring for the threat model.
_MD = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table")

# Cap the sidebar list. There's one report per week, so 52 covers a
# year — plenty for the "date selector" the spec asks for.
_MAX_SIDEBAR_REPORTS = 52


@router.get("/admin/pulse")
@limiter.limit("30/hour")
async def pulse_latest(request: Request):
    """Latest report. Empty state when nothing's been generated yet
    (fresh install / cron hasn't run)."""
    latest = db.latest_pulse_report()
    others = db.list_pulse_reports(limit=_MAX_SIDEBAR_REPORTS)
    return _render(request, current=latest, others=others)


@router.get("/admin/pulse/{report_id}")
@limiter.limit("30/hour")
async def pulse_by_id(request: Request, report_id: int):
    """Specific report, keyed by row id. 404 when the id is unknown so
    the sidebar link doesn't quietly render the latest instead."""
    current = db.get_pulse_report(report_id)
    if not current:
        raise HTTPException(status_code=404, detail="Report not found.")
    others = db.list_pulse_reports(limit=_MAX_SIDEBAR_REPORTS)
    return _render(request, current=current, others=others)


def _render(request: Request, *, current: dict | None, others: list[dict]):
    report_html = _MD.render(current["markdown"]) if current else ""
    return templates.TemplateResponse(
        request,
        "pages/admin_pulse.html",
        {
            "active_tab": None,   # not part of primary nav
            "current": current,
            "others": others,
            "report_html": report_html,
        },
    )
