"""Shared dependencies for the FastAPI app.

`templates` is the singleton Jinja2 environment reused by every route.
Routes import from here rather than instantiating their own — a single
config point for filters, globals, and auto-reload.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.templating import Jinja2Templates

from core.timeutil import humanize


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"

templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))
templates.env.auto_reload = True


def static_url(rel_path: str) -> str:
    """Build a /static/{path} URL with a cache-buster derived from the file's
    mtime. Keeps browsers from serving a stale CSS/JS when we edit it —
    without needing hard-refreshes. Missing files fall back to the plain URL.
    """
    p = STATIC_ROOT / rel_path
    try:
        v = int(p.stat().st_mtime)
    except OSError:
        return f"/static/{rel_path}"
    return f"/static/{rel_path}?v={v}"


templates.env.globals["static_url"] = static_url

# i18n — `{{ _('key') }}` in templates. Reads the current UI language
# from a ContextVar set by IdentityMiddleware; falls back to English
# when unset (background renders, tests). See ui_web/i18n.py.
from . import i18n as _i18n  # noqa: E402
templates.env.globals["_"] = _i18n.translate
templates.env.globals["current_ui_language"] = _i18n.current_ui_language

# Settings accessor — `{{ get_setting('home_country') }}` in templates.
# Cheap (in-process cache). Used by base.html to gate the first-visit
# geography banner without threading the value through every route.
from core import settings as _app_settings  # noqa: E402
templates.env.globals["get_setting"] = _app_settings.get


def _settings_ctx() -> dict:
    """Snapshot of user-facing settings for the floating settings panel.
    Available in every template via `{% set ctx = settings_ctx() %}` so
    the panel (included in base.html) renders on any page without each
    route having to thread the values through its context dict."""
    ui = _i18n.current_ui_language() or _app_settings.DEFAULT_LANGUAGE
    out = _app_settings.get("output_language", "") or ui
    return {
        "ui_language": ui,
        "output_language": out,
        "home_country": _app_settings.get("home_country", ""),
        "home_city": _app_settings.get("home_city", ""),
    }


templates.env.globals["settings_ctx"] = _settings_ctx

# Jinja filters — mirror what the Streamlit UI uses so templates read the same.
templates.env.filters["humanize"] = humanize


def verdict_label(v: str) -> str:
    """Pretty-print a verdict slug for display."""
    return {
        "strong_fit": "Strong fit",
        "workable": "Workable",
        "stretch": "Stretch",
        "poor_fit": "Poor fit",
    }.get(v or "", v or "—")


templates.env.filters["verdict_label"] = verdict_label


# Detect lines that are role/company/date headers rather than bullet content.
# Broader regex than v1 — catches many more formats seen in real LLM output.
_TITLE_LINE_RE = re.compile(
    r"\d{4}.*[—–|/]|[—–|/].*\d{4}"        # "2020 — ACME" or "ACME | 2020"
    r"|\bat\b.*\d{4}|\(.*\d{4}.*\)"        # "at ACME from 2019", "(2019-2023)"
    r"|\bpresent\b"                        # "Coordinator, ACME | Present"
    r"|—\s*[A-Z]|[A-Z].*\s—\s",           # em-dash separator + capital start
    re.IGNORECASE,
)

# Verbs that commonly START an achievement bullet. Presence at the start
# strongly suggests bullet content, not a header.
_BULLET_VERB_STARTS = (
    "achieved", "authored", "built", "collaborated", "conducted", "coordinated",
    "created", "delivered", "designed", "developed", "drove", "engineered",
    "established", "executed", "generated", "grew", "implemented", "improved",
    "increased", "initiated", "launched", "led", "leveraged", "managed",
    "maintained", "mentored", "orchestrated", "organized", "owned", "partnered",
    "performed", "planned", "presented", "produced", "programmed", "provided",
    "reduced", "researched", "resolved", "reviewed", "scaled", "shipped",
    "solved", "spearheaded", "streamlined", "supervised", "supported",
    "taught", "trained", "translated", "utilized", "worked", "wrote",
    "assisted", "handled", "monitored", "prepared", "processed",
)


def is_title_line(text: str) -> bool:
    """True if this looks like a job/role/date header rather than a bullet.

    Uses multiple signals: regex for date/separator patterns, common-verb
    detection for bullet openers, and length. When in doubt, false (bullet
    format is a safer default).
    """
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > 100:
        return False   # too long to be a header

    # If it starts with a common bullet verb, it's clearly a bullet.
    first_word = stripped.split(None, 1)[0].lower().rstrip(".,;:") if stripped else ""
    if first_word in _BULLET_VERB_STARTS:
        return False

    if _TITLE_LINE_RE.search(stripped):
        return True
    # Short + no ending period + starts with capital — probably a heading
    if (
        len(stripped) < 70
        and stripped[0].isupper()
        and not stripped.rstrip().endswith((".", "!"))
        and any(c.isupper() for c in stripped[1:])  # more than one capital
    ):
        return True
    return False


templates.env.filters["is_title_line"] = is_title_line


def slugify(text: str, max_length: int = 40) -> str:
    """Filename-safe slug: alphanum + underscores, capped length."""
    if not text:
        return ""
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text[:max_length].strip("_")


templates.env.filters["slugify"] = slugify


# ── JD renderer ────────────────────────────────────────────
# jobspy converts scraped HTML to plaintext with markdown-ish markers
# (`**bold**`, `* bullet`, `- bullet`, blank lines between paragraphs).
# Rendering that raw in monospace looks like an unformatted dump. This
# filter converts the common patterns to structured HTML.
import html as _html
from markupsafe import Markup

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BULLET_RE = re.compile(r"^\s*[\*\-]\s+(.+)$")
_HEADER_LINE_RE = re.compile(r"^\*\*(.+?)\*\*\s*:?\s*$")


def _inline_bold(text: str) -> str:
    return _BOLD_RE.sub(r"<strong>\1</strong>", text)


def jd_html(text: str) -> "Markup":
    """Convert jobspy-style plaintext to safe, structured HTML.

    Supported patterns:
        **bold text**       → <strong>
        * item / - item     → <ul><li>
        **Header line**     → <h4>
        blank line          → paragraph break

    All user content is HTML-escaped BEFORE our markers get replaced, so
    injected job descriptions can never break out into unsafe HTML.
    """
    if not text:
        return Markup("")
    text = _html.escape(str(text).strip())

    blocks = re.split(r"\n\s*\n+", text)
    out: list[str] = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")

        # Full-block header case: "**Position Summary**"
        if len(lines) == 1 and _HEADER_LINE_RE.match(lines[0]):
            content = _HEADER_LINE_RE.match(lines[0]).group(1)
            out.append(f'<h4 class="jd-h">{_inline_bold(content)}</h4>')
            continue

        # List detection: majority of lines look like bullets
        bullet_matches = [_BULLET_RE.match(l) for l in lines]
        bullet_count = sum(1 for m in bullet_matches if m)
        if bullet_count >= max(1, len(lines) * 0.5):
            items: list[str] = []
            for l, m in zip(lines, bullet_matches):
                if m:
                    items.append(f"<li>{_inline_bold(m.group(1).strip())}</li>")
                else:
                    stripped = l.strip()
                    if stripped and items:
                        items[-1] = items[-1][:-5] + " " + _inline_bold(stripped) + "</li>"
            out.append('<ul class="jd-list">' + "".join(items) + "</ul>")
            continue

        # Plain paragraph, honoring inline bold and inline line-breaks
        joined = "<br>".join(_inline_bold(l.strip()) for l in lines if l.strip())
        out.append(f'<p class="jd-p">{joined}</p>')

    return Markup("\n".join(out))


templates.env.filters["jd_html"] = jd_html
