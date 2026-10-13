"""In-app nudges (REQ-058, ADR-086): one calm next step at a time.

Rules live here in code, so a change ships to every tester at once. State
lives in the events table: `nudge.shown`, `nudge.clicked` and
`nudge.dismissed` with `{"id": ...}`. A dismissed nudge never comes back.
/admin/nudges lists every rule with its counts. Turn one off without a
deploy: `JOBOT_NUDGES_OFF=add_resume,first_search`.

Kinds:
  banner   : a callout above the page, with one action. `spotlight` is a
             CSS selector Driver.js lights up when the action is on the
             same page.
  feedback : the feedback button introduces itself once (a soft pulse
             and a short note), no banner.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Optional

from core import db


@dataclass(frozen=True)
class Ctx:
    has_resume: bool
    has_search: bool
    has_scores: bool


@dataclass(frozen=True)
class Nudge:
    id: str
    kind: str                       # banner | feedback
    when: Callable[[Ctx], bool]
    pages: tuple[str, ...] = ()     # active_tab values; () = any page
    href: Optional[str] = None      # action goes to another page
    spotlight: Optional[str] = None  # or lights up an element on this page
    note: str = ""                  # for the admin list: why it exists


NUDGES: tuple[Nudge, ...] = (
    Nudge("add_resume", "banner", lambda c: not c.has_resume,
          pages=("jobs", "journey", "prep"), href="/profile",
          note="No résumé yet. Every score starts there."),
    Nudge("first_search", "banner", lambda c: c.has_resume and not c.has_search,
          pages=("jobs",), spotlight="#q-input",
          note="Résumé in, no search yet: light up the search box."),
    Nudge("feedback_intro", "feedback", lambda c: c.has_scores,
          note="After the first fit score, the feedback button says hello once."),
)
BY_ID = {n.id: n for n in NUDGES}
ACTIONS = ("shown", "clicked", "dismissed")


def _off() -> set[str]:
    return {x.strip() for x in (os.getenv("JOBOT_NUDGES_OFF") or "").split(",") if x.strip()}


def _context(conn) -> Ctx:
    one = lambda sql: conn.execute(sql).fetchone() is not None  # noqa: E731
    return Ctx(
        has_resume=one("SELECT 1 FROM resumes WHERE is_current = 1 LIMIT 1"),
        has_search=one("SELECT 1 FROM search_tasks LIMIT 1") or one("SELECT 1 FROM saved_searches LIMIT 1"),
        has_scores=one("SELECT 1 FROM job_scores LIMIT 1"),
    )


def _done(conn) -> set[str]:
    """Ids the user dismissed (banners) or already saw once (feedback intro)."""
    rows = conn.execute(
        "SELECT type, payload_json FROM events WHERE type IN ('nudge.dismissed', 'nudge.shown')").fetchall()
    out = set()
    for r in rows:
        try:
            nid = json.loads(r["payload_json"] or "{}").get("id")
        except ValueError:
            continue
        n = BY_ID.get(nid)
        if n and (r["type"] == "nudge.dismissed" or n.kind == "feedback"):
            out.add(nid)
    return out


def pick(active_tab: str = "", kind: str = "banner") -> Optional[Nudge]:
    """The one nudge of `kind` to show on this page now, or None. Never raises:
    a nudge must never break a page."""
    try:
        with db.connect() as conn:
            ctx, done = _context(conn), _done(conn)
    except Exception:  # noqa: BLE001
        return None
    off = _off()
    for n in NUDGES:
        if n.kind != kind or n.id in off or n.id in done:
            continue
        if n.pages and active_tab not in n.pages:
            continue
        if n.when(ctx):
            return n
    return None


def stats() -> list[dict]:
    """Every rule with on/off and shown/clicked/dismissed counts, for admin."""
    counts = {n.id: dict.fromkeys(ACTIONS, 0) for n in NUDGES}
    with db.connect() as conn:
        for r in conn.execute("SELECT type, payload_json FROM events WHERE type LIKE 'nudge.%'").fetchall():
            try:
                nid = json.loads(r["payload_json"] or "{}").get("id")
            except ValueError:
                continue
            act = r["type"].split(".", 1)[1]
            if nid in counts and act in counts[nid]:
                counts[nid][act] += 1
    off = _off()
    return [{"id": n.id, "kind": n.kind, "pages": n.pages, "note": n.note,
             "on": n.id not in off, **counts[n.id]} for n in NUDGES]
