"""Universal fallback: parse schema.org/JobPosting from JSON-LD.

Google for Jobs incentivizes every ATS to emit JobPosting JSON-LD, so
most SSR job pages carry the full posting in a
`<script type="application/ld+json">` tag. This runs after per-ATS
adapters have been tried (or when the URL doesn't match any adapter) and
before the LLM fallback — it beats LLM extraction on cost, latency, AND
accuracy for pages that emit valid JSON-LD.

Not registered in the adapter registry: dispatch is called explicitly from
`from_url.job_from_url()` because the fetch shape differs (we need the
HTML, not a JSON endpoint).

Refs:
    https://schema.org/JobPosting
    https://developers.google.com/search/docs/appearance/structured-data/job-posting
"""
from __future__ import annotations

import re
from typing import Any, Optional

import extruct
from w3lib.html import get_base_url

from .base import AdapterFetchError, guarded_get, html_to_markdown_lite, raw_to_job_dict


def fetch_from_jsonld(url: str) -> Optional[dict]:
    """Fetch `url`, extract JobPosting JSON-LD, return a Job dict or None.

    Returns None (not raises) when no JobPosting is present or the extracted
    posting lacks title AND company — that's a normal fall-through to the
    LLM path, not an error worth logging as extract.failed.

    Raises AdapterFetchError only on network / HTTP failure so the caller
    can distinguish 'nothing to parse' from 'couldn't reach the page'."""
    resp = guarded_get(url)
    html = resp.text
    if not html:
        return None

    base = get_base_url(html, resp.url or url)
    try:
        data = extruct.extract(
            html,
            base_url=base,
            syntaxes=["json-ld", "microdata"],
            uniform=True,
        )
    except Exception:  # noqa: BLE001 — malformed markup is common; skip
        return None

    posting = _find_job_posting(data)
    if not posting:
        return None

    raw = _posting_to_raw(posting)
    if not raw.get("title") and not raw.get("company"):
        return None
    try:
        return raw_to_job_dict(raw, source_url=url, site_hint="jsonld")
    except ValueError:
        return None


# ── extraction ─────────────────────────────────────────────────────────

def _find_job_posting(extracted: dict) -> Optional[dict]:
    """Walk the extruct result and return the first `@type == JobPosting`
    node found. Handles both flat lists and nested `@graph` arrays."""
    for syntax in ("json-ld", "microdata"):
        for item in extracted.get(syntax) or []:
            hit = _match_job_posting(item)
            if hit:
                return hit
    return None


def _match_job_posting(node: Any) -> Optional[dict]:
    if isinstance(node, list):
        for entry in node:
            hit = _match_job_posting(entry)
            if hit:
                return hit
        return None
    if not isinstance(node, dict):
        return None
    t = node.get("@type") or node.get("type")
    if _is_job_posting_type(t):
        return node
    # Nested @graph — Google sometimes emits multiple entities in one blob.
    graph = node.get("@graph")
    if graph:
        return _match_job_posting(graph)
    return None


def _is_job_posting_type(t: Any) -> bool:
    if isinstance(t, str):
        return t.endswith("JobPosting")
    if isinstance(t, list):
        return any(isinstance(x, str) and x.endswith("JobPosting") for x in t)
    return False


def _posting_to_raw(posting: dict) -> dict:
    """Map schema.org/JobPosting → the partial dict shape raw_to_job_dict
    consumes. Tolerant to missing fields — job boards emit inconsistent
    subsets of the spec."""
    title = _first(posting.get("title"))

    org = posting.get("hiringOrganization") or {}
    if isinstance(org, list):
        org = org[0] if org else {}
    company = ""
    if isinstance(org, dict):
        company = _first(org.get("name")) or ""
    elif isinstance(org, str):
        company = org

    location = _extract_location(posting.get("jobLocation"))

    description = html_to_markdown_lite(_first(posting.get("description")) or "")
    # schema.org descriptions frequently contain HTML tags. jd_html
    # escapes its input, so we normalize to markdown-lite here.

    posted = _first(posting.get("datePosted")) or ""
    if isinstance(posted, str) and len(posted) >= 10:
        posted = posted[:10]

    min_sal, max_sal = _extract_salary(posting.get("baseSalary"))

    is_remote = _looks_remote(posting, location, description)

    return {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "is_remote": is_remote,
        "min_salary": min_sal,
        "max_salary": max_sal,
        "posted_date": posted,
    }


def _first(v: Any) -> str:
    """JSON-LD fields can be scalar or list. Return the first string."""
    if v is None:
        return ""
    if isinstance(v, list):
        for x in v:
            s = _first(x)
            if s:
                return s
        return ""
    if isinstance(v, dict):
        return _first(v.get("@value") or v.get("name") or "")
    return str(v).strip()


def _extract_location(loc: Any) -> str:
    """`jobLocation` can be a single Place, a list of Places, or nested
    with `address` → PostalAddress fields. Return a `City, Region, Country`
    string best-effort."""
    if not loc:
        return ""
    if isinstance(loc, list):
        parts = [_extract_location(x) for x in loc]
        return " · ".join(p for p in parts if p)
    if not isinstance(loc, dict):
        return _first(loc)
    addr = loc.get("address") or loc
    if isinstance(addr, list):
        addr = addr[0] if addr else {}
    if not isinstance(addr, dict):
        return _first(addr)
    bits = [
        _first(addr.get("addressLocality")),
        _first(addr.get("addressRegion")),
        _first(addr.get("addressCountry")),
    ]
    return ", ".join(b for b in bits if b)


def _extract_salary(base: Any) -> tuple[Optional[float], Optional[float]]:
    """`baseSalary` → (min, max). schema.org allows scalar `value`,
    MonetaryAmount.value, or QuantitativeValue with min/max."""
    if not base:
        return None, None
    if isinstance(base, list):
        base = base[0] if base else {}
    if not isinstance(base, dict):
        return None, None
    value = base.get("value")
    if isinstance(value, list):
        value = value[0] if value else {}
    if isinstance(value, dict):
        mn = _to_float(value.get("minValue"))
        mx = _to_float(value.get("maxValue"))
        if mn is None and mx is None:
            v = _to_float(value.get("value"))
            return v, v
        return mn, mx
    v = _to_float(value)
    return v, v


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_REMOTE_RE = re.compile(r"\b(remote|work from home|telework|wfh)\b", re.IGNORECASE)


def _looks_remote(posting: dict, location: str, description: str) -> bool:
    # Schema.org uses `jobLocationType == "TELECOMMUTE"` for remote roles.
    jlt = posting.get("jobLocationType")
    if isinstance(jlt, str) and "TELECOMMUTE" in jlt.upper():
        return True
    if isinstance(jlt, list) and any(
        isinstance(x, str) and "TELECOMMUTE" in x.upper() for x in jlt
    ):
        return True
    return bool(_REMOTE_RE.search(f"{location} {description}"))
