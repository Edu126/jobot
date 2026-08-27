"""Regression fixtures for REQ-004 (section-based scoring) and REQ-005
(remove AEC scoring bias / domain-neutral persona).

No live Gemini calls — same pattern as test_ai_summary_grounding.py: hand-
author the JSON a well-behaved model would return under the new rubric,
run it through the REAL parsing/backend-math/grounding code, and assert
the deterministic parts (weighted score, verdict band, grounding) behave.
What a model WOULD score a given resume/job pair is not something a unit
test can pin down; what the backend does with those section scores is —
that's the boundary ADR-006 draws (LLM=evidence, backend=math), so it's
the boundary these tests cover.

Fixtures are synthetic (no real user resume text) — see ADR-013 doc note
and the 2026-08-26 next-work.md kickoff entry for why: no real resume
text/fixtures exist in this repo/environment, and committing real user
resume text to git is a separate data-governance call from the ephemeral
per-request send to Gemini GOV-001 covers.

Runs without pytest:
    .venv/bin/python tests/test_section_scoring.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.matching import semantic_score as ss  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


JOB = {"id": "job1", "title": "Test Job", "company": "Acme",
       "description": "irrelevant for these fixtures — sections are hand-authored"}


def _score(sections: dict, hard_requirements: list | None = None, reasoning: str = "") -> ss.ScoreResult:
    raw = {
        "scores": [{
            "job_id": "job1",
            "sections": sections,
            "hard_requirements": hard_requirements or [],
            "reasoning": reasoning,
        }]
    }
    parsed = ss._parse_response(raw, [JOB], "gemini-test")
    _assert(len(parsed) == 1, "fixture must parse to exactly one ScoreResult")
    return parsed[0]


def _sec(score: int, matched: list[str] | None = None, gaps: list[str] | None = None, reasoning: str = "") -> dict:
    return {"score": score, "matched": matched or [], "gaps": gaps or [], "reasoning": reasoning}


# ---------- Fixture 1: AEC (no-regression proof) ----------
# Synthetic AEC candidate + AEC job, both genuinely well-matched. Proves
# the section-based rewrite doesn't regress the case the old hardcoded
# "AEC recruiter" persona was originally tuned for.
AEC_RESUME = """
Marco Ianni
Ottawa, Ontario

Experience:
- BIM Coordinator at Skyline Construction (2019-present). Managed clash
  detection across 12 commercial projects using Revit and Navisworks.
  Coordinated with structural and MEP teams on RFI resolution.
- Junior Drafter at BuildRight Engineering (2016-2019). AutoCAD 2D/3D
  drafting for civil site plans.

Education:
- BASc, Civil Engineering, Carleton University (2016)

Certifications: PMP (2021)
Skills: Revit, Navisworks, AutoCAD, Civil 3D, IFC, clash detection, RFI management
""".strip()

AEC_SECTIONS = {
    "experience": _sec(85, matched=["BIM Coordinator", "clash detection"], reasoning="direct role match"),
    "skills": _sec(90, matched=["Revit", "Navisworks"], reasoning="exact tool overlap"),
    "role": _sec(90, matched=["BIM Coordinator"], reasoning="same title, same scope"),
    "domain": _sec(90, matched=["construction"], reasoning="same industry"),
    "education": _sec(80, matched=["BASc Civil Engineering"], reasoning="relevant degree"),
}
AEC_HARD_REQS = [{"name": "PMP certification", "status": "met", "evidence": "PMP (2021)"}]


# ---------- Fixture 2: non-AEC, Sales (proves bias isn't relocated) ----------
# An equally strong candidate-job fit in a completely different domain.
# If the rewrite still privileged AEC, this fixture would land in a lower
# band than fixture 1 despite comparable underlying section scores.
SALES_RESUME = """
Elena Ruiz
Bogota, Colombia

Experience:
- Account Executive at CloudSuite SaaS (2019-present). Carried a $1.2M
  annual quota, managed full-cycle B2B sales using Salesforce and
  HubSpot. Closed 40+ mid-market accounts.
- SDR at DataFlow Inc (2017-2019). Outbound prospecting, pipeline
  generation for the enterprise sales team.

Education:
- BA, Business Administration, Universidad de los Andes (2017)

Skills: Salesforce, HubSpot, B2B sales, pipeline management, negotiation
""".strip()

SALES_SECTIONS = {
    "experience": _sec(85, matched=["Account Executive", "quota"], reasoning="direct role match"),
    "skills": _sec(88, matched=["Salesforce", "HubSpot"], reasoning="exact tool overlap"),
    "role": _sec(92, matched=["Account Executive"], reasoning="same title, same scope"),
    "domain": _sec(88, matched=["SaaS"], reasoning="same industry"),
    "education": _sec(80, matched=["BA Business Administration"], reasoning="relevant degree"),
}
SALES_HARD_REQS = [{"name": "Bachelor's degree", "status": "met", "evidence": "BA, Business Administration"}]


# ---------- Fixture 3: career-switcher vs. weak same-industry ----------
# REQ-005's explicit success criterion: "A career-switcher with strong
# transferable experience but no direct industry history scores higher
# than a same-industry candidate with weak relevant experience."
SWITCHER_RESUME = """
Jordan Lee
Toronto, Ontario

Experience:
- Logistics Officer, Canadian Armed Forces (2015-present, 8 years).
  Planned and executed multi-site material distribution for a 400-person
  unit. Owned inventory accuracy, vendor coordination, and a $2M annual
  procurement budget. Led a team of 6.
- Operations NCO (2012-2015). Scheduling, resource allocation, reporting.

Education:
- Diploma, Business Administration, Georgian College (2012)

Skills: Inventory management, vendor negotiation, Excel, team leadership,
budget planning
""".strip()

SWITCHER_SECTIONS = {
    "experience": _sec(80, matched=["8 years", "team of 6"], reasoning="strong scope, transferable"),
    "skills": _sec(75, matched=["inventory management", "budget planning"], reasoning="skills transfer well"),
    "role": _sec(78, matched=["logistics", "vendor coordination"], reasoning="responsibilities align closely"),
    "domain": _sec(35, gaps=["civilian supply chain experience"], reasoning="no direct industry history"),
    "education": _sec(70, matched=["Business Administration diploma"], reasoning="adjacent field"),
}

WEAK_SAME_INDUSTRY_RESUME = """
Sam Cole
Toronto, Ontario

Experience:
- Warehouse Clerk, FreightCo Logistics (2023-present, 1 year). Data
  entry for inbound shipments, filing.

Education:
- High school diploma

Skills: Data entry, filing
""".strip()

WEAK_SECTIONS = {
    "experience": _sec(30, matched=["1 year"], gaps=["analytical experience"], reasoning="brief, junior scope"),
    "skills": _sec(40, gaps=["inventory software", "vendor negotiation"], reasoning="minimal overlap"),
    "role": _sec(35, gaps=["analyst-level responsibility"], reasoning="clerical, not analyst scope"),
    "domain": _sec(85, matched=["logistics"], reasoning="same industry"),
    "education": _sec(60, gaps=["relevant degree"], reasoning="no post-secondary credential"),
}


def main() -> int:
    # ---- Fixture 1: AEC, no regression ----
    aec = _score(AEC_SECTIONS, AEC_HARD_REQS)
    expected_aec = round(85 * 0.30 + 90 * 0.25 + 90 * 0.20 + 90 * 0.15 + 80 * 0.10)
    _assert(aec.score == expected_aec, f"AEC fixture score mismatch: {aec.score} != {expected_aec}")
    _assert(aec.verdict == "strong_fit", f"AEC fixture should be strong_fit, got {aec.verdict}")
    _assert(aec.hard_requirements[0].status == "met", "AEC hard requirement should be met")

    # ---- Fixture 2: Sales, bias-not-relocated proof ----
    sales = _score(SALES_SECTIONS, SALES_HARD_REQS)
    expected_sales = round(85 * 0.30 + 88 * 0.25 + 92 * 0.20 + 88 * 0.15 + 80 * 0.10)
    _assert(sales.score == expected_sales, f"Sales fixture score mismatch: {sales.score} != {expected_sales}")
    _assert(sales.verdict == aec.verdict == "strong_fit",
            "Equivalently strong AEC and Sales fits must land in the SAME verdict band — "
            "proves the domain-neutral rewrite doesn't privilege AEC")

    # ---- Fixture 3: career-switcher beats weak same-industry ----
    switcher = _score(SWITCHER_SECTIONS)
    weak = _score(WEAK_SECTIONS)
    _assert(switcher.score > weak.score,
            f"Career-switcher ({switcher.score}) must outscore weak same-industry "
            f"candidate ({weak.score}) — REQ-005's transferable-experience proof")
    _assert(switcher.verdict in ("workable", "strong_fit"),
            f"Career-switcher with strong transferable experience should be workable+, got {switcher.verdict}")
    _assert(weak.verdict in ("poor_fit", "stretch"),
            f"Weak same-industry candidate should be stretch or worse, got {weak.verdict}")

    # ---- Grounding guard-rail: well-formed fixtures pass ----
    for resume_text, result, label in (
        (AEC_RESUME, aec, "AEC"),
        (SALES_RESUME, sales, "Sales"),
        (SWITCHER_RESUME, switcher, "switcher"),
        (WEAK_SAME_INDUSTRY_RESUME, weak, "weak-same-industry"),
    ):
        norm = ss._norm_text(resume_text)
        stems: set[str] = set()
        for w in norm.split():
            stems.update(ss._term_stems(w))
        _assert(ss._grounding_ok(result, norm, stems),
                f"{label} fixture's hand-authored matched/gaps should ground cleanly "
                f"against its own resume text")

    # ---- Grounding guard-rail: catches a hallucinated match ----
    bad_match = copy.deepcopy(aec)
    bad_match.sections["skills"].matched = ["Salesforce"]  # not in the AEC resume
    norm = ss._norm_text(AEC_RESUME)
    stems = set()
    for w in norm.split():
        stems.update(ss._term_stems(w))
    _assert(not ss._grounding_ok(bad_match, norm, stems),
            "a claimed match absent from the resume MUST fail grounding")

    # ---- Grounding guard-rail: catches a hallucinated (false-positive) gap ----
    bad_gap = copy.deepcopy(aec)
    bad_gap.sections["skills"].gaps = ["Revit"]  # IS in the AEC resume — false-positive gap
    _assert(not ss._grounding_ok(bad_gap, norm, stems),
            "a claimed gap that's actually present in the resume MUST fail grounding "
            "(the false-positive-gap bug REQ-005 targets)")

    # ---- Persona neutrality: same rubric, different persona, no leakage ----
    aec_persona = "a senior BIM coordination candidate with experience in construction"
    sales_persona = "a mid B2B sales candidate with experience in SaaS"
    p_aec = ss._build_prompt(AEC_RESUME, [JOB], persona=aec_persona, reasoning_language="en")
    p_sales = ss._build_prompt(AEC_RESUME, [JOB], persona=sales_persona, reasoning_language="en")

    _assert("AEC" not in p_sales, "a non-AEC persona must never see the literal 'AEC' string")
    _assert(sales_persona in p_sales, "the resolved persona must appear verbatim in its own prompt")

    anchor = "Below are"
    _assert(anchor in p_aec and anchor in p_sales, "prompt anchor missing — template changed?")
    _assert(p_aec[p_aec.index(anchor):] == p_sales[p_sales.index(anchor):],
            "the rubric/rules/schema must be BYTE-IDENTICAL regardless of persona — "
            "only the opening persona line may differ (REQ-005: same prompt, no domain privileged)")

    print("OK — section scoring + domain-neutral persona hold on all fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
