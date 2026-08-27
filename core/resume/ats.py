"""Heuristic ATS-friendliness checks on a parsed resume.

These approximate what real ATS systems care about; they are not perfect,
but flagging these issues handles the most common reasons a resume gets
silently dropped.

Important design choice: section presence is detected from CONTENT, not
just from heading names. A resume that uses "Professional Background"
instead of "Experience" should not be penalized — modern ATS handle
creative headings fine. We only flag a section as truly missing when no
date ranges / school names / tool keywords are anywhere in the document.

Output schema:
    {
        "score": int,           # 0-100
        "issues": [
            {"severity": "critical"|"warning"|"info",
             "category": str,
             "message": str,
             "fix": str}
        ],
        "passed": [str],        # list of check names that passed
    }
"""
from __future__ import annotations

import re
from typing import Any

from . import section_presence


SEVERITY_PENALTY = {
    "critical": 15,
    "warning": 5,
    "info": 1,
}

# Characters that some older ATS parsers choke on.
PROBLEMATIC_CHARS = set("│┃║▌▐█▓▒░◆◇◈◉●○◎◐◑")
EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport
    "\U0001F1E0-\U0001F1FF"   # flags
    "\U00002700-\U000027BF"   # dingbats
    "\U0001F900-\U0001F9FF"   # supplemental symbols
    "]"
)


def run_checks(parsed: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    passed: list[str] = []

    # Use the current contact dict, which includes user-provided overrides
    # (phone, LinkedIn, etc. added via "What recruiters will see"). Those
    # fields are injected into every generated artifact, so if the user has
    # supplied them, the ATS score should reflect their presence.
    contact = parsed.get("contact", {})
    stats = parsed.get("stats", {})
    docx_meta = parsed.get("docx_meta", {})
    raw_text = parsed.get("raw_text", "")
    source_format = parsed.get("source_format", "")

    _check_contact(contact, issues, passed)
    _check_sections(parsed, issues, passed)
    _check_length(stats, issues, passed)
    _check_docx_layout(docx_meta, source_format, issues, passed)
    _check_problem_chars(raw_text, issues, passed)
    _check_file_format(source_format, issues, passed)

    score = max(0, 100 - sum(SEVERITY_PENALTY[i["severity"]] for i in issues))
    return {"score": score, "issues": issues, "passed": passed}


# ---------- individual checks ----------

def _check_contact(contact, issues, passed):
    if contact.get("email"):
        passed.append("Has email address")
    else:
        issues.append({
            "severity": "critical",
            "category": "contact",
            "message": "No email address detected.",
            "fix": "Add a professional email address near the top of the resume.",
        })

    if contact.get("phone"):
        passed.append("Has phone number")
    else:
        issues.append({
            "severity": "critical",
            "category": "contact",
            "message": "No phone number detected.",
            "fix": "Add a phone number near the top of the resume.",
        })

    if contact.get("location"):
        passed.append("Has location")
    else:
        issues.append({
            "severity": "warning",
            "category": "contact",
            "message": "No location detected. Canadian recruiters often filter by city.",
            "fix": "Add 'Ottawa, ON, Canada' (or your actual city) under your name.",
        })

    if contact.get("linkedin"):
        passed.append("Has LinkedIn URL")
    else:
        issues.append({
            "severity": "info",
            "category": "contact",
            "message": "No LinkedIn profile URL found.",
            "fix": "Add your LinkedIn URL to the contact line. Most ATS scrape it.",
        })


def _check_sections(parsed, issues, passed):
    """Use content-based presence detection. Penalty severity depends on:
       - heading found  → pass
       - content found but no standard heading → soft info (relabeling hint)
       - genuinely absent → real penalty
    """
    evidence = section_presence.analyze(parsed)

    # Severities used only when a section is genuinely absent (no content
    # signal at all). Modern ATS handle creative headings fine; we don't
    # punish for that.
    absent_severity = {
        "experience":     "critical",
        "education":      "warning",
        "skills":         "warning",
        "certifications": "info",
        "summary":        "info",
    }

    for sect, ev in evidence.items():
        title = sect.title()
        if ev.via == "heading":
            passed.append(f"{title} present (labeled section)")
        elif ev.via == "content":
            passed.append(f"{title} present ({ev.note})")
            # Soft hint: tell the user their heading is non-standard, but
            # don't ding them hard for it.
            issues.append({
                "severity": "info",
                "category": "structure",
                "message": (
                    f"{title} content was detected ({ev.note}), but not under a standard "
                    f"heading. Modern ATS (Workday, Greenhouse, Lever) handle this fine."
                ),
                "fix": (
                    f"If you're targeting older systems (government Taleo, large-enterprise "
                    f"PeopleSoft), consider renaming the section heading to '{title}'. "
                    f"Otherwise, this is cosmetic."
                ),
            })
        else:  # absent
            severity = absent_severity.get(sect, "info")
            verb = "Consider adding" if severity == "info" else "Add"
            issues.append({
                "severity": severity,
                "category": "structure",
                "message": f"No {title} content detected ({ev.note}).",
                "fix": f"{verb} a '{title}' section with the standard expected content.",
            })


def _check_length(stats, issues, passed):
    wc = stats.get("word_count", 0)
    if wc < 250:
        issues.append({
            "severity": "warning",
            "category": "length",
            "message": f"Resume is short ({wc} words). Recruiters expect 300–800.",
            "fix": "Expand bullets with measurable outcomes, or add a Summary section.",
        })
    elif wc > 1000:
        issues.append({
            "severity": "warning",
            "category": "length",
            "message": f"Resume is long ({wc} words). Aim for 1–2 pages (~400–800 words).",
            "fix": "Trim older roles to 1–2 bullets; remove irrelevant content.",
        })
    else:
        passed.append(f"Length is reasonable ({wc} words)")


def _check_docx_layout(docx_meta, source_format, issues, passed):
    if source_format != "docx":
        return
    if docx_meta.get("has_tables"):
        issues.append({
            "severity": "warning",
            "category": "layout",
            "message": (
                f"Resume uses {docx_meta.get('table_count', 0)} table(s). "
                "Many ATS parse tables in unpredictable order."
            ),
            "fix": "Re-flow content into a single column. Use the 'Download clean DOCX' button as a starting point.",
        })
    else:
        passed.append("No tables (good for ATS)")

    if docx_meta.get("has_images"):
        issues.append({
            "severity": "warning",
            "category": "layout",
            "message": (
                f"Resume contains {docx_meta.get('image_count', 0)} image(s). "
                "ATS skip images entirely — any text inside them is lost."
            ),
            "fix": "Remove logos, headshots, and icon graphics. Use text instead.",
        })
    else:
        passed.append("No images (good for ATS)")


def _check_problem_chars(raw_text, issues, passed):
    found = {c for c in raw_text if c in PROBLEMATIC_CHARS}
    emojis = EMOJI_RE.findall(raw_text)

    if found:
        issues.append({
            "severity": "info",
            "category": "characters",
            "message": f"Found decorative characters that may not render: {' '.join(found)}",
            "fix": "Replace with plain bullets ('•' or '-').",
        })
    if emojis:
        issues.append({
            "severity": "info",
            "category": "characters",
            "message": f"Found {len(emojis)} emoji character(s).",
            "fix": "Remove emojis — most ATS strip them and they look unprofessional in Canadian/government roles.",
        })
    if not found and not emojis:
        passed.append("No problematic characters")


def _check_file_format(source_format, issues, passed):
    if source_format == "docx":
        passed.append("File format is .docx (best for ATS)")
    elif source_format == "pdf":
        issues.append({
            "severity": "info",
            "category": "format",
            "message": "PDF is acceptable but DOCX parses more reliably across ATS.",
            "fix": "Most Canadian ATS handle PDF fine, but if a posting offers a choice, send DOCX.",
        })
