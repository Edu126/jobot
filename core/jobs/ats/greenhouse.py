"""Greenhouse job-board adapter.

Public JSON API, no auth. URL → board_token + job_id extraction is trivial
because Greenhouse's URLs are `boards.greenhouse.io/{token}/jobs/{id}`.

Iframe-embedded boards on customer domains aren't handled here — they need
board-token discovery from the parent page's iframe src. Adapter dispatch
falls through to JSON-LD / LLM for those.

Docs: https://developers.greenhouse.io/job-board.html
"""
from __future__ import annotations

import re

from .base import AdapterFetchError, guarded_get, html_to_markdown_lite, raw_to_job_dict


# `boards.greenhouse.io/stripe/jobs/6789012` — also `job-boards.greenhouse.io`
# (the 2024 rebrand host, currently 302s to boards but future-proofing).
_URL_RE = re.compile(
    r"^https?://(?:boards|job-boards)\.greenhouse\.io/"
    r"(?P<token>[a-zA-Z0-9_.-]+)/jobs/(?P<id>\d+)"
)


class GreenhouseAdapter:
    name = "greenhouse"

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url or ""))

    def fetch(self, url: str) -> dict:
        m = _URL_RE.match(url)
        if not m:
            raise AdapterFetchError(f"URL doesn't match Greenhouse pattern: {url}")
        token = m.group("token")
        job_id = m.group("id")
        api = (
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}"
            "?content=true"
        )
        resp = guarded_get(api, headers={"Accept": "application/json"})
        data = resp.json()

        location = ""
        loc_obj = data.get("location")
        if isinstance(loc_obj, dict):
            location = loc_obj.get("name") or ""

        raw = {
            "title": data.get("title"),
            "company": data.get("company_name") or token.replace("-", " ").title(),
            "location": location,
            "description": html_to_markdown_lite(data.get("content") or ""),
            "is_remote": _looks_remote(location, data.get("content", "")),
            "posted_date": (data.get("updated_at") or data.get("first_published"))[:10]
                if (data.get("updated_at") or data.get("first_published"))
                else "",
            "job_url_direct": data.get("absolute_url"),
        }
        return raw_to_job_dict(raw, source_url=url, site_hint="greenhouse")


def _looks_remote(location: str, description: str) -> bool:
    blob = f"{location} {description}".lower()
    return any(kw in blob for kw in ("remote", "work from home", "telework"))
