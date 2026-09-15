"""Turn a fit SCORE into a decision (Eduardo, 2026-09-15).

EXP-001 established the 0-100 score is trustworthy (it tracks a recruiter,
ρ≈0.75-0.86, corroborated by an independent judge) — but a bare number doesn't
tell the user WHAT KIND of match a job is. "88" reads the same whether it's a
natural in-field role at your level or a cross-domain reach into a senior title.
This module adds that missing dimension, cheaply and deterministically — NO new
LLM call. It combines two relations the number hides:

  1. DOMAIN — is the job in the candidate's field, or a pivot? Derived from the
     candidate's `role_label`/`domain` (ai_summary, ADR-013) vs the job title,
     after stripping generic role words ("analyst", "manager") that carry level,
     not field.
  2. SENIORITY — does the job's title level match the candidate's? Ordinal
     junior<mid<senior<lead, job level parsed from the title.

Crossed into a human `fit_type` (in-lane / reach / pivot / long-shot), plus a
one-line `seniority_note`. The existing score `reasoning`/`matched`/`gaps` stay
the "why"; this is the "what kind". Heuristic by design — validated against the
adversarial harness's recruiter verdicts, upgradeable to an LLM field on the
score call if the heuristic proves too coarse.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

# Ordinal seniority. Everything the resume/JD says maps into one of these.
_SENIORITY_RANK = {"junior": 1, "mid": 2, "senior": 3, "lead": 4}

# Title tokens → a seniority tier. Management titles (manager/director) and IC
# senior titles (senior/lead/principal) both read "above mid" to a candidate.
_TITLE_SENIORITY = [
    (re.compile(r"\b(chief|vp|vice[\s-]?president|head\s+of|director)\b", re.I), 4),
    (re.compile(r"\b(senior|sr\.?|lead|principal|staff|manager|mgr)\b", re.I), 3),
    (re.compile(r"\b(junior|jr\.?|entry|intern|graduate|trainee|assistant)\b", re.I), 1),
]

# Generic role/level words that describe WHAT you do at any level, not the FIELD.
# Stripped from role_label so only field-carrying words remain for domain match.
_ROLE_NOISE = frozenset({
    "analyst", "analytics", "specialist", "manager", "coordinator", "associate",
    "consultant", "developer", "engineer", "officer", "representative", "rep",
    "director", "lead", "senior", "junior", "principal", "staff", "advisor",
    "administrator", "assistant", "professional", "expert", "generalist",
    "and", "of", "the", "for", "in", "&", "-", "sr", "jr",
})

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#]{1,}")

# Domain abbreviations — a title says "BI Analyst" while the candidate's domain
# reads "business intelligence". Expand both sides so the field can match.
_ABBREV = {
    "bi": "business intelligence", "ml": "machine learning",
    "ai": "artificial intelligence", "hr": "human resources",
    "qa": "quality assurance", "ux": "user experience",
    "sre": "site reliability", "fpa": "financial planning",
}

# Field words too generic to prove a domain match on their own — "business" is
# in "business intelligence" but also in "business operations", a different field.
_GENERIC_FIELD = frozenset({
    "business", "operations", "services", "solutions", "general",
    "corporate", "digital", "systems", "technology", "strategy",
})


@dataclass
class FitStory:
    fit_type: str          # code: "in_lane" | "reach" | "pivot" | "long_shot" | "weak"
    fit_label: str         # human: "In your lane", "Reach — level up", …
    seniority_note: str    # one line on the level relationship
    domain_relation: str   # "in_lane" | "adjacent"
    seniority_relation: str  # "at" | "up" | "down" | "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "")]


def _job_seniority_tier(job_title: str) -> int | None:
    for pat, tier in _TITLE_SENIORITY:
        if pat.search(job_title or ""):
            return tier
    return 2 if job_title else None   # a title with no level marker reads mid


def job_level_label(job_title: str) -> str:
    """Human tag for the VACANCY's level, read straight from its title. This is a
    fact about the JOB, not a guess about the candidate (Eduardo 2026-09-15: it's
    safer and more useful to assume about the role than the applicant — a person's
    self-read of 'mid' vs an inferred 'senior' is contentious; the JD's level is
    not). '' for an unmarked/mid title, which carries no useful signal."""
    return {4: "Leadership role", 3: "Senior-level role",
            1: "Junior-level role"}.get(_job_seniority_tier(job_title), "")


def seniority_relation(candidate_seniority: str, job_title: str) -> str:
    """'at' / 'up' / 'down' / 'unknown' — the job's title level vs the candidate."""
    cand = _SENIORITY_RANK.get((candidate_seniority or "").strip().lower())
    job = _job_seniority_tier(job_title)
    if cand is None or job is None:
        return "unknown"
    if job > cand:
        return "up"
    if job < cand:
        return "down"
    return "at"


def _expand(words: list[str]) -> set[str]:
    """Lower-cased token set with abbreviations expanded into their words —
    'bi' also contributes {business, intelligence}."""
    out: set[str] = set()
    for w in words:
        out.add(w)
        if w in _ABBREV:
            out.update(_ABBREV[w].split())
    return out


def _field_words(role_label: str, domain: str) -> set[str]:
    """Field-carrying words from role_label + domain: drop generic role/level
    words ('analyst', 'manager') AND ultra-generic field words ('business'), so a
    match needs the DISTINCTIVE field term ('intelligence'), not a shared filler."""
    raw = _expand(_words(role_label)) | _expand(_words(domain))
    return {w for w in raw
            if w not in _ROLE_NOISE and w not in _GENERIC_FIELD and len(w) > 2}


def domain_relation(role_label: str, domain: str, job_title: str) -> str:
    """'in_lane' if a distinctive field word shows up in the job title (abbrevs
    expanded on both sides), else 'adjacent'. 'adjacent' when no field words."""
    fields = _field_words(role_label, domain)
    if not fields:
        return "adjacent"
    title_words = _expand(_words(job_title))
    if fields & title_words:
        return "in_lane"
    return "adjacent"


# (domain, seniority) → (code, label). Kept as a table so the mapping is obvious.
_MATRIX = {
    ("in_lane", "at"):   ("in_lane", "In your lane"),
    ("in_lane", "down"): ("in_lane", "In your lane"),
    ("in_lane", "up"):   ("reach", "Reach — level up"),
    ("adjacent", "at"):   ("pivot", "Pivot — new field"),
    ("adjacent", "down"): ("pivot", "Pivot — new field"),
    ("adjacent", "up"):   ("long_shot", "Long shot — new field & level up"),
}


def build(
    *,
    role_label: str,
    domain: str,
    seniority: str,
    job_title: str,
    score: int,
    verdict: str,
) -> FitStory:
    """Compose the match story from the candidate summary + job title + the
    already-computed score. Pure/deterministic — safe to call on every card."""
    dom = domain_relation(role_label, domain, job_title)
    sen = seniority_relation(seniority, job_title)

    # A genuinely poor score overrides the geometry — no point calling a 0.30-fit
    # "in your lane". Below the stretch floor it's just weak.
    if verdict == "poor_fit" or score < 40:
        code, label = "weak", "Weak match"
    else:
        code, label = _MATRIX.get((dom, sen if sen != "unknown" else "at"),
                                  ("pivot", "Pivot — new field"))

    cand_s = (seniority or "").strip().lower() or "your"
    job_tier = _job_seniority_tier(job_title)
    tier_name = {1: "junior", 2: "mid", 3: "senior", 4: "leadership"}.get(job_tier, "")
    if sen == "up":
        note = f"A step up — this reads as a {tier_name}-level role and you read as {cand_s}."
    elif sen == "down":
        note = f"Below your level — you read as {cand_s}, this reads {tier_name}-level."
    elif sen == "at":
        note = "Matches your level."
    else:
        note = ""

    return FitStory(
        fit_type=code,
        fit_label=label,
        seniority_note=note,
        domain_relation=dom,
        seniority_relation=sen,
    )
