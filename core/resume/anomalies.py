"""Per-section anomaly detection for the parsed resume preview.

Complements ats.py (whole-resume scoring) and section_presence.py (does the
section exist at all?). This module answers: "for each section that IS
present, does the parsed content look sane, or did the parser choke?"

The Profile preview panel renders one chip per section with a status dot:
    ✓ Summary        3 lines
    ✓ Experience    12 items
    ! Skills        47 items · looks like one-word-per-line
    ✓ Education      2 items

`analyze(parsed)` returns everything the template needs — item counts,
flags, and a short preview snippet — so we don't re-derive it in Jinja.

Deterministic, zero LLM, sub-millisecond. Called on every /profile GET.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Per-section thresholds. Tuned against real-world resumes seen so far
# (mostly PDF exports where line reflow breaks in the parser).
_WORD_PER_LINE_RATIO = 0.5       # 50%+ of items are ≤2 words → parser choked
_WORD_PER_LINE_MIN_ITEMS = 6     # only flag when there's enough to be significant
_TOO_LONG_ITEMS = 30             # >30 items → parser probably absorbed a neighbor
_DUPLICATE_LINE_MIN_REPEAT = 3   # same line repeated 3+ times = extraction bug


# Flag → human-friendly label used by the template. Kept centralized so the
# UI stays consistent and we can add flags without touching the template.
FLAG_LABELS: dict[str, str] = {
    "empty":            "no content parsed",
    "word_per_line":    "looks like one-word-per-line (parser reflow issue)",
    "too_long":         "unusually long — parser may have absorbed a neighbor",
    "no_dates":         "no date ranges — experience entries usually have them",
    "duplicates":       "duplicate lines detected",
    "too_short":        "very short — may be truncated",
}


@dataclass
class TokenGroup:
    """A category line flattened into individual tokens, e.g. one skills/
    languages/interests line "Software: AutoCAD, Revit, Bluebeam" becomes
    label="Software", tokens=["AutoCAD", "Revit", "Bluebeam"]."""
    label: str | None                # category label, or None if ungrouped
    tokens: list[str]


@dataclass
class Line:
    """One rendered line in the expanded, non-grouped view. `bold` marks
    job-title / project-name lines (experience, projects) so they read as
    a heading over their bullets, mirroring the actual resume's structure
    instead of flattening everything into one run-on paragraph."""
    text: str
    bold: bool = False


@dataclass
class SectionReport:
    key: str                        # canonical section key: "summary", "experience", ...
    title: str                      # display title: "Summary", "Experience", ...
    count: int                      # display count — see note below for "skills"/"experience"
    flags: list[str] = field(default_factory=list)
    groups: list[TokenGroup] | None = None   # set for skills/languages/interests
    lines: list[Line] | None = None          # set for everything else — one item per line,
                                              # NOT joined into a single blob (that read as an
                                              # unreadable wall of text — see anomalies.py history)
    count_label: str | None = None  # overrides raw "{count}" badge when set
                                     # (e.g. "5 roles · 17 bullets", "142 words")

    @property
    def is_anomalous(self) -> bool:
        return bool(self.flags)

    @property
    def flag_messages(self) -> list[str]:
        return [FLAG_LABELS.get(f, f) for f in self.flags]


# Sections we report on, aligned with the JSON Resume standard schema
# (https://jsonresume.org/schema — basics/summary/work/education/skills/
# projects/publications/volunteer/awards/certificates/languages/interests/
# references) minus "basics" (that's the separate Contact-verify block).
# Order matches display order in the preview panel.
#
# This list must stay a superset of core.resume.parser.SECTION_PATTERNS —
# a key detected by the parser but missing here is invisible in the
# preview even though it round-trips fine through tailoring/rendering.
_REPORT_SECTIONS = [
    ("summary",        "Summary"),
    ("experience",     "Experience"),
    ("education",      "Education"),
    ("skills",         "Skills"),
    ("certifications", "Certifications"),
    ("projects",       "Projects"),
    ("publications",   "Publications"),
    ("volunteer",      "Volunteer"),
    ("awards",         "Awards"),
    ("languages",      "Languages"),
    ("interests",      "Interests"),
    ("references",     "References"),
]

# Sections written as a handful of comma-dense lines rather than one entry
# per line ("Software: AutoCAD, Revit, Bluebeam"). These get the flatten
# treatment (TokenGroup chips) instead of a raw item count.
_FLATTEN_SECTIONS = {"skills", "languages", "interests"}

# Sections shaped as "title line, then bullets underneath" (job title +
# achievements, project name + description). Title-looking lines render
# bold in the expanded view so the hierarchy is visible.
_TITLED_LIST_SECTIONS = {"experience", "projects"}


def missing_sections(parsed: dict[str, Any]) -> list[tuple[str, str]]:
    """Canonical (key, title) pairs the candidate does NOT have. Used to
    scope the LLM "worth adding?" call to only the sections that are
    actually absent — never asks about (or shows suggestions for) a
    section that's already there."""
    sections_dict = parsed.get("sections") or {}
    return [(k, t) for k, t in _REPORT_SECTIONS if not sections_dict.get(k)]


def present_sections(parsed: dict[str, Any]) -> list[tuple[str, str]]:
    """Canonical (key, title) pairs the candidate DOES have — complement of
    missing_sections(). Used as context for the LLM summary call."""
    sections_dict = parsed.get("sections") or {}
    return [(k, t) for k, t in _REPORT_SECTIONS if sections_dict.get(k)]


def analyze(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return the full preview report for a parsed resume.

    Shape:
        {
          "sections":     [SectionReport, ...],   # ordered, only present sections
          "anomaly_count": int,
          "banner":       str | None,             # one-line summary if any flags
        }
    """
    sections_dict = parsed.get("sections") or {}
    reports: list[SectionReport] = []

    for key, title in _REPORT_SECTIONS:
        raw = sections_dict.get(key)
        if not raw:
            continue  # section absent — handled by section_presence, skip here
        items = _clean_items(raw)

        # Flags always run against the raw parsed lines — that's what
        # detects parser reflow issues (word-per-line, duplicates, etc),
        # regardless of how we choose to DISPLAY the section below.
        flags = _detect_flags(key, items)

        if key in _FLATTEN_SECTIONS:
            # Resumes commonly write these as a few category/comma-dense
            # lines ("Software: AutoCAD, Revit, ...") rather than one entry
            # per line. A raw item count ("3") badly undersells what's
            # there and reads as broken parsing. Flatten into individual
            # tokens for both the count and the display.
            groups = _build_token_groups(items, section_title=title)
            count = sum(len(g.tokens) for g in groups)
            report = SectionReport(
                key=key, title=title, count=count, groups=groups,
            )
        elif key in _TITLED_LIST_SECTIONS:
            # Parser flattens job-title/project-name lines and their
            # bullets into one list. A flat count ("22") reads as "22
            # jobs", which is wrong — it's usually N roles + M bullets.
            # Show both when we can tell them apart, and bold the title
            # lines in the expanded view so the hierarchy is visible
            # instead of 22 lines at the same visual weight.
            n_titles, n_bullets = _split_titled_list(items)
            label = None
            if n_titles and key == "experience":
                role_word = "role" if n_titles == 1 else "roles"
                bullet_word = "bullet" if n_bullets == 1 else "bullets"
                label = f"{n_titles} {role_word} · {n_bullets} {bullet_word}"
            lines = [Line(text=it, bold=bool(_TITLE_LINE_RE.search(it))) for it in items]
            report = SectionReport(
                key=key, title=title, count=len(items),
                lines=lines, count_label=label,
            )
        elif key == "summary":
            # "1" (one paragraph) isn't a meaningful count. Word count is.
            word_count = len(" ".join(items).split())
            report = SectionReport(
                key=key, title=title, count=len(items),
                lines=[Line(text=it) for it in items],
                count_label=f"{word_count} words",
            )
        else:
            # Plain one-entry-per-line sections (Education, Certifications,
            # Volunteer, Awards, Publications, References) — each item is
            # already a complete, atomic fact. Render as a real list, not a
            # "·"-joined blob (that reads as an unreadable wall of text,
            # especially on narrow screens).
            report = SectionReport(
                key=key, title=title, count=len(items),
                lines=[Line(text=it) for it in items],
            )

        report.flags = flags
        reports.append(report)

    anomaly_count = sum(1 for r in reports if r.is_anomalous)
    banner = _build_banner(reports)

    return {
        "sections": reports,
        "anomaly_count": anomaly_count,
        "banner": banner,
    }


# ─────────────────────────────────────────────────────────────
# Flag detectors — order in list dictates precedence when we
# build the summary banner
# ─────────────────────────────────────────────────────────────

def _detect_flags(section_key: str, items: list[str]) -> list[str]:
    flags: list[str] = []
    if not items:
        flags.append("empty")
        return flags

    # word_per_line / too_long both approximate "did the parser shred a
    # paragraph into garbage fragments?" — a signal that makes sense for
    # prose/bullet sections (experience, summary). It does NOT apply to
    # skills/languages/interests: those are LEGITIMATELY short per raw line
    # ("Python", "SQL") and can legitimately run long (30+ real skills is
    # normal). Flagging those as broken parsing is a false positive that
    # trains users to ignore the warning banner — see smoke-test case
    # "sparse_reflow" (8 one-word skills wrongly flagged) and "pathological"
    # (35 real skills wrongly flagged as too-long).
    if section_key not in _FLATTEN_SECTIONS:
        if _looks_word_per_line(items):
            flags.append("word_per_line")

        if len(items) > _TOO_LONG_ITEMS:
            flags.append("too_long")

    if _has_duplicate_lines(items):
        flags.append("duplicates")

    if section_key == "experience" and not _has_any_dates(items):
        flags.append("no_dates")

    if section_key == "summary" and _summary_too_short(items):
        flags.append("too_short")

    return flags


def _looks_word_per_line(items: list[str]) -> bool:
    if len(items) < _WORD_PER_LINE_MIN_ITEMS:
        return False
    short = sum(1 for it in items if len(it.split()) <= 2)
    return (short / len(items)) >= _WORD_PER_LINE_RATIO


def _has_duplicate_lines(items: list[str]) -> bool:
    seen: dict[str, int] = {}
    for it in items:
        key = it.strip().lower()
        if len(key) < 8:
            continue  # ignore short lines (bullet markers etc.)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= _DUPLICATE_LINE_MIN_REPEAT:
            return True
    return False


_MONTHS = {
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}


def _has_any_dates(items: list[str]) -> bool:
    """True if ANY item mentions a 4-digit year OR a month token. Deliberately
    permissive — we're flagging total absence of any date-shape signal, not
    validating format."""
    for it in items:
        lo = it.lower()
        if any(str(y) in lo for y in range(1990, 2031)):
            return True
        if any(m in lo for m in _MONTHS):
            return True
    return False


def _summary_too_short(items: list[str]) -> bool:
    joined = " ".join(items).strip()
    return len(joined.split()) < 8


# ─────────────────────────────────────────────────────────────
# Skills / Languages / Interests — category-line flattening
# ─────────────────────────────────────────────────────────────

import re as _re

# Matches a leading category label before a colon, e.g. "Software: ..." or
# "Construction Management: ...". Capped length so we don't misfire on a
# skill phrase that happens to contain a colon deep in the line.
_CATEGORY_LABEL_RE = _re.compile(r"^([A-Z][\w &/'\-]{1,40}):\s*(.+)$")


def _build_token_groups(items: list[str], *, section_title: str = "") -> list["TokenGroup"]:
    """Turn parsed category/comma-dense lines into (label, tokens) groups.

    Each raw line is either "Category: item, item, item" (label set) or a
    bare comma-separated list (label=None). Splitting only on comma/semi-
    colon — NOT on " and " — because compound names ("Health and Safety",
    "Reading and Writing") would be wrongly split. This slightly undercounts
    list-final items phrased "X and Y", an acceptable trade-off vs breaking
    legitimate compound names.

    A line like "Languages: English, French" under the Languages section
    heading extracts label="Languages" — showing it again right below the
    section's own title ("Languages > Languages > English, French") is
    redundant, so a label matching the section title (singular/plural
    tolerant) is dropped.
    """
    section_norm = section_title.strip().lower().rstrip("s")
    groups: list[TokenGroup] = []
    for line in items:
        label = None
        rest = line
        m = _CATEGORY_LABEL_RE.match(line)
        if m:
            label, rest = m.group(1).strip(), m.group(2).strip()
            if label.lower().rstrip("s") == section_norm:
                label = None
        tokens = [t.strip() for t in _re.split(r"[,;]", rest) if t.strip()]
        if tokens:
            groups.append(TokenGroup(label=label, tokens=tokens))
    return groups


# ─────────────────────────────────────────────────────────────
# Experience / Projects — split title lines from bullets underneath
# ─────────────────────────────────────────────────────────────

# Mirrors writer.py's _TITLE_LINE_RE heuristic: a line is a title if it has
# a year AND a separator commonly used in "Title — Company (dates)" lines.
# Kept as a local copy rather than importing writer.py's private regex —
# this module and writer.py each own a small, self-contained pattern
# rather than sharing a cross-module private symbol.
_TITLE_LINE_RE = _re.compile(
    r"\d{4}.*[—–|/]|[—–|/].*\d{4}|\bat\b.*\d{4}|\(.*\d{4}.*\)",
    _re.IGNORECASE,
)


def _split_titled_list(items: list[str]) -> tuple[int, int]:
    """Return (title_count, bullet_count). title_count is 0 if no line
    matches the title-line shape — callers should treat 0 as "can't tell,
    don't show a broken-down count"."""
    titles = sum(1 for it in items if _TITLE_LINE_RE.search(it))
    return titles, len(items) - titles


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _clean_items(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _build_banner(reports: list[SectionReport]) -> str | None:
    """One-line summary of anomalies for the banner. Names the worst offender
    by section so the user knows where to look."""
    anomalous = [r for r in reports if r.is_anomalous]
    if not anomalous:
        return None
    if len(anomalous) == 1:
        r = anomalous[0]
        return f"{r.title} looks off — {r.flag_messages[0]}."
    names = ", ".join(r.title for r in anomalous[:3])
    plural = "sections" if len(anomalous) > 1 else "section"
    suffix = f" (+{len(anomalous) - 3} more)" if len(anomalous) > 3 else ""
    return f"{len(anomalous)} {plural} look off: {names}{suffix} — click to review."
