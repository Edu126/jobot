"""AtsAdapter protocol + shared utilities every adapter uses.

Every adapter's `fetch()` MUST call `guarded_get()` (or otherwise validate
the URL host via `core.net.safety.is_safe_public_ip`) before making the
network call. Skipping this reopens the SSRF hole that `fetch_page_text`
guards against — a malicious paste could otherwise let a caller read
internal admin pages or cloud metadata via the model's output.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any, Optional, Protocol
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, NavigableString

from core.net.safety import is_safe_public_ip


# Firefox on macOS UA — some ATSes (Workday especially) refuse "requests" default.
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) "
    "Gecko/20100101 Firefox/126.0"
)
DEFAULT_TIMEOUT_S = 15


class AdapterFetchError(RuntimeError):
    """Adapter matched the URL but couldn't retrieve the posting.

    Dispatch catches this and falls through — callers should not see it."""


class AtsAdapter(Protocol):
    """Contract every per-ATS adapter must satisfy.

    `matches(url)` is cheap (regex / host check) — called for every
    incoming URL, so keep it O(1).

    `fetch(url)` performs network I/O and returns a Job-shaped dict with
    the same keys `_to_job_dict` produces (title, company, location, site,
    date_posted, job_url, job_url_direct, description, is_remote,
    min_salary, max_salary, detected_language, french_required, id).
    Raises AdapterFetchError (or any Exception) on failure — dispatch
    turns that into an `extract.failed` event and falls through.
    """

    name: str

    def matches(self, url: str) -> bool: ...

    def fetch(self, url: str) -> dict: ...


def guarded_get(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    method: str = "GET",
    json_body: Any = None,
) -> requests.Response:
    """SSRF-guarded HTTP request. Rejects private-IP hosts pre-request
    AND re-checks after redirects.

    Raises AdapterFetchError on host validation failure, HTTP error, or
    network exception."""
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        raise AdapterFetchError(f"Unsupported scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise AdapterFetchError("URL has no hostname.")
    if not is_safe_public_ip(host):
        raise AdapterFetchError(
            f"'{host}' resolves to a private or internal address."
        )

    merged_headers = {"User-Agent": DEFAULT_UA, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        merged_headers.update(headers)

    try:
        resp = requests.request(
            method,
            url,
            headers=merged_headers,
            timeout=timeout,
            allow_redirects=True,
            json=json_body,
        )
    except requests.RequestException as exc:
        raise AdapterFetchError(f"Network error fetching {url}: {exc}") from exc

    final = urlparse(resp.url or url)
    if final.hostname and not is_safe_public_ip(final.hostname):
        raise AdapterFetchError(
            f"Redirect landed on private address: {final.hostname!r}"
        )

    if resp.status_code >= 400:
        raise AdapterFetchError(f"HTTP {resp.status_code} on {url}")

    return resp


def raw_to_job_dict(raw: dict, source_url: str, *, site_hint: Optional[str] = None) -> dict:
    """Shared converter from a partial job dict to the full Job schema.

    Adapters, JSON-LD parser, and LLM extractor all funnel through this so
    downstream code sees one shape. Applies the same language detection +
    French-required heuristics `search.py` uses so filters behave identically.

    `raw` fields recognized (all optional):
        title, company, location, description, is_remote, min_salary,
        max_salary, posted_date (YYYY-MM-DD or empty), job_url_direct.

    Raises ValueError if title AND company are both missing — the caller
    is responsible for turning that into a user-facing error."""
    # Local import to avoid a circular dep (search.py has no ats deps today
    # but might grow one; also keeps this module importable in isolation).
    from core.jobs.search import _detect_language, _french_required

    title = _clean(raw.get("title"))
    company = _clean(raw.get("company"))
    description = _clean(raw.get("description"))

    if not title and not company:
        raise ValueError("Missing both title and company — not a job posting")

    detected = _detect_language(f"{title}\n{description}")
    french_required = _french_required(description)

    site = site_hint or _site_from_url(source_url)
    posted = _clean(raw.get("posted_date")) or date.today().isoformat()

    return {
        "id": _stable_id(source_url, title, company, description),
        "title": title or "(no title)",
        "company": company or "(unknown company)",
        "location": _clean(raw.get("location")),
        "site": site,
        "date_posted": posted,
        "job_url": source_url,
        "job_url_direct": _clean(raw.get("job_url_direct")) or None,
        "description": description,
        "is_remote": bool(raw.get("is_remote")),
        "min_salary": _clean_num(raw.get("min_salary")),
        "max_salary": _clean_num(raw.get("max_salary")),
        "detected_language": detected,
        "french_required": french_required,
    }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stable_id(url: str, title: str, company: str, description: str) -> str:
    """Prefer URL-based id (stable across imports of the same URL); fall
    back to content hash for manual pastes. Prefixed with 'url-' to make
    the source visible in debug queries. Uses hyphens (not colons) so IDs
    are safe in URL path segments."""
    if url:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        return f"url-{h}"
    payload = f"{title}||{company}||{description[:500]}".encode("utf-8")
    return f"manual-{hashlib.sha1(payload).hexdigest()[:16]}"


def html_to_markdown_lite(html: str) -> str:
    """Convert HTML fragments (as ATS APIs return in description fields)
    to the markdown-lite dialect `jd_html` understands:
        **bold**, * bullet items, blank-line paragraph breaks.

    Every adapter that receives an HTML description passes it through
    this before returning, so the whole app has one description dialect
    reaching the Jinja `jd_html` filter. jd_html escapes its input, so we
    CANNOT ship raw HTML from adapters — it would render as literal
    `&lt;div&gt;` on screen.

    Not a general-purpose HTML→Markdown converter. Handles the tags ATS
    payloads actually use (p, div, br, strong, b, em, i, ul/ol/li, h1-6);
    unknown tags become plain text via BeautifulSoup's default get_text.
    """
    if not html:
        return ""
    if "<" not in html:
        # Already plain text / markdown-lite — nothing to convert.
        return html.strip()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    out_lines: list[str] = []

    def _inline(node: Any) -> str:
        """Render inline text with **bold** markers preserved."""
        if isinstance(node, NavigableString):
            return str(node)
        name = getattr(node, "name", "") or ""
        if name in ("strong", "b"):
            inner = "".join(_inline(c) for c in node.children).strip()
            return f"**{inner}**" if inner else ""
        if name == "br":
            return "\n"
        if name in ("em", "i", "u", "span", "a", "small", "sub", "sup"):
            return "".join(_inline(c) for c in node.children)
        return "".join(_inline(c) for c in getattr(node, "children", []))

    def _block(node: Any) -> None:
        name = getattr(node, "name", "") or ""
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                out_lines.append(text)
            return
        if name in ("ul", "ol"):
            for li in node.find_all("li", recursive=False):
                item = _inline(li).strip().replace("\n", " ")
                item = re.sub(r"\s+", " ", item)
                if item:
                    out_lines.append(f"* {item}")
            out_lines.append("")
            return
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            inner = _inline(node).strip()
            if inner:
                out_lines.append(f"**{inner}**")
                out_lines.append("")
            return
        if name in ("p", "div", "section", "article", "li"):
            inner = _inline(node).strip()
            # If the div wraps block children, recurse instead of flattening.
            children_blocks = [
                c for c in node.children
                if getattr(c, "name", None) in (
                    "p", "div", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
                    "section", "article",
                )
            ]
            if children_blocks:
                for c in node.children:
                    _block(c)
                return
            if inner:
                out_lines.append(inner)
                out_lines.append("")
            return
        # Unknown block-ish tag: recurse into children so we don't drop content.
        for c in getattr(node, "children", []):
            _block(c)

    root = soup.body or soup
    for c in root.children:
        _block(c)

    text = "\n".join(out_lines)
    # Collapse >2 blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse repeated whitespace on individual lines
    text = "\n".join(re.sub(r"[ \t]+", " ", line.rstrip()) for line in text.splitlines())
    return text.strip()


def _site_from_url(url: str) -> str:
    """Short site label from URL host. Adapters override via `site_hint`."""
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
    if "oraclecloud.com" in host:
        return "oracle_hcm"
    if "taleo.net" in host:
        return "taleo"
    return host or "url"
