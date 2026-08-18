"""Lever postings adapter.

Public JSON API, no auth. URL → company_slug + posting_id extraction from
`jobs.lever.co/{slug}/{id}`.

Some Lever customers disable the public feed or use vanity domains;
adapter dispatch falls through to JSON-LD / LLM for those.

Docs: https://hire.lever.co/developer/documentation
"""
from __future__ import annotations

import re

from .base import AdapterFetchError, guarded_get, html_to_markdown_lite, raw_to_job_dict


# `jobs.lever.co/stripe/abcdef01-2345-6789-abcd-ef0123456789`
# posting ids are UUIDs — 32 hex with 4 dashes.
_URL_RE = re.compile(
    r"^https?://jobs\.lever\.co/"
    r"(?P<slug>[a-zA-Z0-9_.-]+)/"
    r"(?P<id>[0-9a-fA-F-]{20,})"
)


class LeverAdapter:
    name = "lever"

    def matches(self, url: str) -> bool:
        return bool(_URL_RE.match(url or ""))

    def fetch(self, url: str) -> dict:
        m = _URL_RE.match(url)
        if not m:
            raise AdapterFetchError(f"URL doesn't match Lever pattern: {url}")
        slug = m.group("slug")
        post_id = m.group("id")
        api = f"https://api.lever.co/v0/postings/{slug}/{post_id}?mode=json"
        resp = guarded_get(api, headers={"Accept": "application/json"})
        data = resp.json()

        cats = data.get("categories") or {}
        location = cats.get("location") or ""
        commitment = cats.get("commitment") or ""

        # Lever returns `description` as HTML including the intro + close.
        # `descriptionPlain` is a text version. Prefer HTML so bullet
        # structure survives, then convert to the markdown-lite dialect
        # `jd_html` renders (which escapes HTML input).
        description = html_to_markdown_lite(
            data.get("description") or data.get("descriptionPlain") or ""
        )

        # createdAt is ms since epoch
        posted = ""
        created = data.get("createdAt")
        if isinstance(created, (int, float)):
            from datetime import datetime, timezone
            posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).date().isoformat()

        raw = {
            "title": data.get("text"),
            "company": slug.replace("-", " ").title(),
            "location": " · ".join(x for x in [location, commitment] if x),
            "description": description,
            "is_remote": _looks_remote(location, description),
            "posted_date": posted,
            "job_url_direct": data.get("hostedUrl") or data.get("applyUrl"),
        }
        return raw_to_job_dict(raw, source_url=url, site_hint="lever")


def _looks_remote(location: str, description: str) -> bool:
    blob = f"{location} {description}".lower()
    return any(kw in blob for kw in ("remote", "work from home", "telework"))
