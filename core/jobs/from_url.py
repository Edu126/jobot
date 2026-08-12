"""URL-based single job import.

Given a URL to a job posting anywhere on the web, fetch the page and extract
a structured job dict (matching core.jobs.search.Job) via Gemini. Falls back
to a manual-paste flow when fetching fails (Cloudflare, JS-heavy pages,
403s) — the same extractor runs on user-pasted text.

Design notes:
- Not tied to specific ATSes (Greenhouse, Workday, etc). The LLM extractor
  handles arbitrary layouts. This trades a bit of extraction precision for
  massive coverage. If specific ATSes need dedicated parsers later, add
  them upstream of `_extract_job_fields`.
- We keep description as markdown-lite (**bold** + *bullets*) so the
  `jd_html` Jinja filter renders it the same way JobSpy-sourced jobs render.
- ID is derived from the URL (stable across imports of the same URL); when
  no URL is available (manual paste), a hash of title+company+description.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from core.jobs.search import _detect_language, _french_required
from core.llm.gemini import GeminiClient, GeminiError


# Firefox on macOS UA — some ATSes (Workday especially) refuse "requests" default.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) "
    "Gecko/20100101 Firefox/126.0"
)
_MAX_PAGE_CHARS = 20_000     # cap page text sent to LLM (cost + latency)
_FETCH_TIMEOUT_S = 15


class UrlFetchError(RuntimeError):
    """Raised when we can't fetch the page (network, HTTP error, blocked)."""


class UrlExtractError(RuntimeError):
    """Raised when the LLM couldn't extract usable fields from the page."""


def fetch_page_text(url: str) -> str:
    """Download the page and return plain text (nav/script/style stripped).

    Raises UrlFetchError on any HTTP/network failure. Successful returns
    are truncated to _MAX_PAGE_CHARS to keep the LLM prompt reasonable.
    """
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=_FETCH_TIMEOUT_S,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise UrlFetchError(f"Network error fetching {url}: {exc}") from exc

    if resp.status_code >= 400:
        raise UrlFetchError(
            f"HTTP {resp.status_code} fetching page. "
            "Site may be blocking automated access — paste the description manually."
        )

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse repeated blank lines the stripping leaves behind
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:_MAX_PAGE_CHARS]


def extract_job_from_text(
    text: str,
    source_url: str,
    client: GeminiClient,
) -> dict:
    """Ask Gemini to extract job fields from arbitrary page text or a
    user-pasted job description. Returns a dict matching Job schema.

    Raises UrlExtractError if the LLM refuses or returns malformed data.
    """
    text = (text or "").strip()
    if not text:
        raise UrlExtractError("Empty text — nothing to extract from.")

    prompt = _build_extraction_prompt(text[:_MAX_PAGE_CHARS])
    try:
        raw = client.generate_json(prompt)
    except GeminiError as exc:
        raise UrlExtractError(f"LLM extraction failed: {exc}") from exc

    return _to_job_dict(raw, source_url)


def job_from_url(url: str, client: GeminiClient) -> dict:
    """End-to-end: fetch + extract. Convenience wrapper."""
    text = fetch_page_text(url)
    return extract_job_from_text(text, source_url=url, client=client)


# ---------- prompt + normalization ----------

def _build_extraction_prompt(page_text: str) -> str:
    return f"""You are extracting a single job posting from the text below. The text is scraped from a webpage and may contain navigation menus, footers, or unrelated content. Your job is to identify the actual job posting and return its fields.

Rules:
- If the text does not contain a real job posting (e.g. it's a search results page, a company homepage, or a 404), set title/company to empty strings — the caller will detect this and show an error.
- description = the FULL job description, preserving structure. Use markdown-lite: **Bold Headers**, * bullet items on their own line. Keep responsibilities, requirements, and qualifications in the order the posting presents them.
- If salary is a range like "$60k–$80k", set min_salary=60000, max_salary=80000. If a single value, set both to it. If unspecified, both null.
- posted_date: only fill if the text explicitly states a date; else null. Do NOT invent.
- is_remote: true only if the posting explicitly says remote/work-from-home/telework. "Hybrid" = false.

Return JSON with this exact schema — no prose:
{{
  "title": "<string>",
  "company": "<string>",
  "location": "<string>",
  "is_remote": <true|false>,
  "min_salary": <number|null>,
  "max_salary": <number|null>,
  "description": "<full markdown-lite text>",
  "posted_date": "<YYYY-MM-DD|null>"
}}

PAGE TEXT:
---
{page_text}
---
"""


def _to_job_dict(raw: dict, source_url: str) -> dict:
    """Coerce Gemini's response into a Job-shaped dict. Applies the same
    French-detection heuristics search.py uses so filters behave identically."""
    title = _clean_str(raw.get("title"))
    company = _clean_str(raw.get("company"))
    description = _clean_str(raw.get("description"))

    if not title and not company:
        raise UrlExtractError(
            "Couldn't identify a job posting on that page — the page may not "
            "be a direct job link, or the site blocks scrapers. Try pasting the "
            "job description manually below."
        )

    detected = _detect_language(f"{title}\n{description}")
    french_required = _french_required(description)

    site = _site_from_url(source_url) if source_url else "manual"
    posted = _clean_str(raw.get("posted_date")) or date.today().isoformat()

    return {
        "id": _stable_id(source_url, title, company, description),
        "title": title or "(no title)",
        "company": company or "(unknown company)",
        "location": _clean_str(raw.get("location")),
        "site": site,
        "date_posted": posted,
        "job_url": source_url,
        "description": description,
        "is_remote": bool(raw.get("is_remote")),
        "min_salary": _clean_num(raw.get("min_salary")),
        "max_salary": _clean_num(raw.get("max_salary")),
        "detected_language": detected,
        "french_required": french_required,
    }


def _clean_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_num(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stable_id(url: str, title: str, company: str, description: str) -> str:
    """Prefer URL-based id (stable across imports of the same URL); fall
    back to content hash for manual pastes. Prefixed with 'url:' to make
    the source visible in debug queries."""
    # Use dashes (not colons) so IDs are safe in URL path segments. HTMX
    # + FastAPI + browser URL bars all agree on hyphens; colons trigger
    # weird encoding edge cases in some intermediate layers.
    if url:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        return f"url-{h}"
    payload = f"{title}||{company}||{description[:500]}".encode("utf-8")
    return f"manual-{hashlib.sha1(payload).hexdigest()[:16]}"


def _site_from_url(url: str) -> str:
    """Extract a short site label from the URL host. Falls back to full
    host when we don't recognize the domain — so a Workday URL becomes
    'workday' but a small firm's careers page becomes 'company.com'."""
    if not url:
        return "manual"
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return "url"
    host = host.lower().lstrip("www.")
    known = {
        "linkedin.com": "linkedin",
        "indeed.com": "indeed",
        "ca.indeed.com": "indeed",
        "glassdoor.com": "glassdoor",
        "glassdoor.ca": "glassdoor",
        "ziprecruiter.com": "ziprecruiter",
        "greenhouse.io": "greenhouse",
        "lever.co": "lever",
        "ashbyhq.com": "ashby",
    }
    for domain, label in known.items():
        if host == domain or host.endswith("." + domain):
            return label
    if "myworkdayjobs.com" in host or "workday.com" in host:
        return "workday"
    if "taleo.net" in host:
        return "taleo"
    return host or "url"
