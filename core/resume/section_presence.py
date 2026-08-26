"""Content-based detection of resume sections.

Heading-based detection (parser.SECTION_PATTERNS) is fragile — real
resumes use creative labels. This module looks at the actual content
to decide whether each canonical section is present, regardless of
how the candidate labeled it.

Used by ats.py so the report doesn't flag missing sections that are
clearly there under a non-standard heading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Evidence:
    present: bool
    via: str         # "heading" | "content" | "absent"
    note: str        # human-readable evidence

    def __bool__(self) -> bool:
        return self.present


# ---------- patterns ----------

# Date ranges, the classic experience marker.
# Examples matched:
#   2022 - Present
#   2022 – 2024
#   Jan 2022 - Dec 2024
#   01/2022 - 12/2024
#   May 2024 – Present
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATE_RANGE_RE = re.compile(
    rf"""
    \b(
        \d{{4}}\s*[-–—to]+\s*(?:\d{{4}}|Present|Current|Today|Now|Ongoing)
        |
        {_MONTH}\s+\d{{4}}\s*[-–—to]+\s*(?:{_MONTH}\s+\d{{4}}|Present|Current|Today|Now|Ongoing)
        |
        \d{{1,2}}/\d{{4}}\s*[-–—to]+\s*(?:\d{{1,2}}/\d{{4}}|Present|Current)
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# School / institution markers — "X University", "X College" etc.
_SCHOOL_RE = re.compile(
    r"\b[A-Z][\w&.,'\- ]{1,40}\s+(University|College|Institute|Polytechnic|Academy|School|Université|Collège)\b",
    re.IGNORECASE,
)

# Degree-name markers.
_DEGREE_RE = re.compile(
    r"""
    \b(
        Bachelor(?:'s)?(?:\s+of\s+[A-Za-z]+)?
        | Master(?:'s)?(?:\s+of\s+[A-Za-z]+)?
        | PhD | Ph\.D\. | Doctorate | Doctoral
        | B\.?A\.? | B\.?S\.? | B\.?Sc\.? | B\.?Eng\.? | B\.?Comm\.?
        | M\.?A\.? | M\.?S\.? | M\.?Sc\.? | M\.?B\.?A\.? | M\.?Eng\.?
        | Diploma | Certificate | Associate(?:\s+of\s+[A-Za-z]+)?
        | Graduate\s+Certificate | Postgraduate
        | Licence | Maîtrise | Baccalauréat
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Common tools/technologies. Broad on purpose — covers office, data,
# cloud, AEC, and more as peer domains (REQ-006: no single domain is the
# default). Used as a "did the candidate list ANY tools" signal.
_TOOL_KEYWORDS = {
    # Office / general
    "excel", "powerpoint", "outlook", "sharepoint", "ms office", "microsoft office",
    "google workspace", "google docs", "google sheets",
    # Programming / data
    "python", "sql", "javascript", "typescript", "java", "c#", "c++", "ruby", "php", " r ",
    "pandas", "numpy", "scikit", "tensorflow", "pytorch",
    "tableau", "power bi", "powerbi", "looker", "qlik",
    # Cloud / devops
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes",
    "terraform", "ansible", "git", "github", "gitlab", "jenkins",
    # Sales / CRM
    "salesforce", "hubspot", "crm", "zendesk", "hootsuite",
    # AEC / construction
    "autocad", "revit", "navisworks", "bluebeam", "sketchup", "tekla",
    "civil 3d", "bim 360", "bim360", "primavera", "p6", "ms project",
    "procore", "bluebeam revu", "ifc", "cobie",
    # Methodologies count as listed skills
    "agile", "scrum", "kanban", "lean", "six sigma", "waterfall", "itil",
    "pmp", "prince2",
}

# Certification markers.
_CERT_RE = re.compile(
    r"""
    \b(
        PMP | CAPM | PRINCE2 | ITIL | CISSP | CISA | CISM | CompTIA
        | AWS\s+Certified | Microsoft\s+Certified | Google\s+Certified
        | Azure\s+Certified | Oracle\s+Certified
        | Certified\s+(?:Scrum|ScrumMaster|Product|Associate|Professional|Solutions|Information)\s+\w+
        | Six\s+Sigma\s+(?:Green|Black|Yellow|White)\s+Belt
        | LEED\s+(?:AP|Green\s+Associate)
        | OSHA | WHMIS
        | CFA | CPA | CMA
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Action verbs commonly seen as the first word of an experience bullet.
_ACTION_VERBS = {
    "led", "managed", "developed", "designed", "implemented", "built",
    "created", "improved", "reduced", "increased", "delivered",
    "coordinated", "executed", "supervised", "trained", "established",
    "launched", "scaled", "deployed", "optimized", "streamlined",
    "spearheaded", "directed", "oversaw", "facilitated", "negotiated",
    "produced", "automated", "redesigned", "rebuilt", "introduced",
    "achieved", "analyzed", "presented", "owned", "drove", "shipped",
}


# ---------- per-section detectors ----------

def has_experience(raw_text: str, sections: dict) -> Evidence:
    if sections.get("experience"):
        return Evidence(True, "heading", "labeled section")
    date_ranges = _DATE_RANGE_RE.findall(raw_text)
    if len(date_ranges) >= 2:
        return Evidence(True, "content", f"{len(date_ranges)} date ranges detected")
    action_count = _count_action_verb_lines(raw_text)
    if action_count >= 3:
        return Evidence(True, "content", f"{action_count} action-verb bullets")
    return Evidence(False, "absent", "no dates and no action-verb bullets")


def has_education(raw_text: str, sections: dict) -> Evidence:
    if sections.get("education"):
        return Evidence(True, "heading", "labeled section")
    school_hit = _SCHOOL_RE.search(raw_text)
    degree_hit = _DEGREE_RE.search(raw_text)
    if school_hit and degree_hit:
        return Evidence(True, "content", "school name + degree keyword detected")
    if school_hit:
        return Evidence(True, "content", f"school name detected: '{school_hit.group(0).strip()}'")
    if degree_hit:
        return Evidence(True, "content", f"degree keyword detected: '{degree_hit.group(0).strip()}'")
    return Evidence(False, "absent", "no school or degree keywords")


def has_skills(raw_text: str, sections: dict) -> Evidence:
    if sections.get("skills"):
        return Evidence(True, "heading", "labeled section")
    text_lower = " " + raw_text.lower() + " "
    found = sorted({t.strip() for t in _TOOL_KEYWORDS if t in text_lower})
    if len(found) >= 3:
        sample = ", ".join(found[:5])
        return Evidence(True, "content", f"{len(found)} tool keywords ({sample}…)")
    return Evidence(False, "absent", "fewer than 3 recognized tool keywords")


def has_certifications(raw_text: str, sections: dict) -> Evidence:
    if sections.get("certifications"):
        return Evidence(True, "heading", "labeled section")
    cert_hit = _CERT_RE.search(raw_text)
    if cert_hit:
        return Evidence(True, "content", f"certification detected: '{cert_hit.group(0).strip()}'")
    return Evidence(False, "absent", "no certification keywords")


def has_summary(sections: dict) -> Evidence:
    # Summary is genuinely heading-defined — there's no content shape that
    # uniquely identifies "this is a summary paragraph." Skip content guess.
    if sections.get("summary"):
        return Evidence(True, "heading", "labeled section")
    return Evidence(False, "absent", "no summary heading found")


# ---------- shared helpers ----------

def _count_action_verb_lines(raw_text: str) -> int:
    count = 0
    for line in raw_text.splitlines():
        stripped = re.sub(r"^[\W_]+", "", line.strip())  # drop leading punctuation
        if not stripped:
            continue
        first_word = stripped.split(maxsplit=1)[0].rstrip(",.;:").lower()
        if first_word in _ACTION_VERBS:
            count += 1
    return count


# ---------- top-level convenience ----------

def analyze(parsed: dict) -> dict[str, Evidence]:
    """Run all detectors. Returns evidence per canonical section."""
    raw_text = parsed.get("raw_text", "")
    sections = parsed.get("sections", {})
    return {
        "experience":     has_experience(raw_text, sections),
        "education":      has_education(raw_text, sections),
        "skills":         has_skills(raw_text, sections),
        "certifications": has_certifications(raw_text, sections),
        "summary":        has_summary(sections),
    }
