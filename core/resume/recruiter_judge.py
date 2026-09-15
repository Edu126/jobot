"""Adversarial recruiter judge (Eduardo, 2026-09-14).

A SEPARATE LLM call from `semantic_score` — different job. Scoring answers
"how well does this candidate cover the JD's requirements?" (a fit number
feeding the ring). This answers a harder, human question about the GENERATED
ARTIFACT: "if I were the recruiter screening this exact resume for this exact
role, would I advance it — and if not, why not?"

Why it exists: we generate tailored resumes and show a fit score, but we have
never adversarially checked whether the OUTPUT is any good — ATS-wise,
recruiter-wise, structure-wise. This is judge #2 of the offline
`scripts/adversarial_eval.py` harness (judge #1 = heuristic `ats.py`, judge #3
= `section_presence` / format checks).

CAVEAT (self-judging): today the only configured model is Gemini, which also
GENERATES the resume. A model grading its own output flatters itself. Two
mitigations, both here: (1) the prompt casts a fair-minded senior recruiter
with an evidence-first rubric that is CALIBRATED — it explicitly treats normal
career patterns (studying while working, pivots, short stints, reasonable gaps)
as fine and only flags genuinely impossible/contradictory signals, and it is
given today's date so it can't hallucinate "future-dated" roles (the v1 judge
did, 2026-09-14); (2) the harness labels every recruiter verdict as
Gemini-self-judged so the number is read with that discount. An independent second model (Claude/OpenAI) is the real fix when
we decide it's worth the key + cost.

Determinism: `temperature=0.0`, same contract as scoring (ADR-018) — a re-judge
of the same resume × JD reproduces instead of drifting.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.llm.sanitize import strip_md_escapes

MAX_JD_CHARS = 3000
MAX_RESUME_CHARS = 12000

# The five rubric axes, each scored 0-5 by the model. Kept as a constant so
# the harness report and the parser agree on the set without duplicating it.
RUBRIC_AXES = (
    "requirement_match",     # evidences the JD's must-have requirements
    "seniority_fit",         # scope/level matches what the role needs
    "impact_quantification", # bullets carry numbers/outcomes, not duties
    "clarity_structure",     # scannable in ~10s, standard sections, single-column-friendly
    "credibility",           # no fabrication smell, no fluff, gaps not papered over
)

# advance / maybe / reject → a coarse 0-100 for aggregation in the report only.
# Never shown to an end user; this is a diagnostic harness signal.
DECISION_SCORE = {"advance": 85, "maybe": 55, "reject": 20}


@dataclass
class RecruiterVerdict:
    decision: str                       # "advance" | "maybe" | "reject"
    axes: dict[str, int]                # RUBRIC_AXES → 0-5
    reject_reasons: list[str]           # concrete, fixable reasons (empty if advance)
    one_liner: str                      # the recruiter's one-sentence call
    model: str = ""

    @property
    def decision_score(self) -> int:
        return DECISION_SCORE.get(self.decision, 0)

    @property
    def rubric_total(self) -> int:
        """Sum of the five axes, 0-25 — a finer signal than the decision band."""
        return sum(self.axes.get(a, 0) for a in RUBRIC_AXES)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decision_score"] = self.decision_score
        d["rubric_total"] = self.rubric_total
        return d


def judge(
    resume_text: str,
    job: dict,
    client: GeminiClient,
    *,
    persona: str = "",
) -> RecruiterVerdict | None:
    """Screen one generated resume against one JD as a skeptical recruiter.

    Returns None if the model refuses / quota is out / response is malformed —
    the harness records that as a skipped cell rather than a fake pass.
    """
    if not resume_text.strip() or not job:
        return None
    if client.all_models_exhausted():
        return None
    prompt = _build_prompt(resume_text.strip()[:MAX_RESUME_CHARS], job, persona=persona)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (GeminiError, QuotaExhaustedError):
        return None
    model_used = client.last_model_used or client.model_name or "unknown"
    return _parse(raw, model_used)


def _build_prompt(resume: str, job: dict, *, persona: str) -> str:
    jd = (job.get("description") or "").strip()[:MAX_JD_CHARS]
    title = job.get("title") or "(unknown title)"
    company = job.get("company") or "(unknown company)"
    persona_line = f" The candidate reads as {persona}." if persona else ""
    today = date.today().isoformat()

    return f"""You are an experienced, fair-minded senior recruiter screening resumes for the role below. Today's date is {today}. You advance the candidates who could realistically do this job and pass on the ones who genuinely can't — you are discerning, not cynical. You judge the resume as written.{persona_line}

Be specific and FAIR. Never reject for normal, explainable career patterns. The following are NORMAL — treat them as fine and keep credibility HIGH:
- Studying while working, or finishing a program while employed — part-time, evening, online, or co-op study overlapping a job is common and completely fine. Overlapping school and work dates are NOT a red flag.
- Career changes or pivots between fields, and transferable experience.
- Short stints, contract/freelance roles, or a reasonable gap between jobs.
- Ambitious but plausible achievements and metrics.

Only flag something as odd when it is GENUINELY off — and even then, phrase it as a fixable question, never an accusation of fraud:
- An impossible timeline: a start date AFTER today ({today}), or two roles that truly cannot both be full-time at once.
- A large UNEXPLAINED gap (several years with nothing at all).
- A metric that is implausible on its face or could not have been produced in the stated role/time.
- A claim that directly contradicts another part of the resume.
If nothing on this list is present, there is no credibility problem — say so.

ROLE:
Title: {title}
Company: {company}
Description:
{jd}

RESUME UNDER REVIEW:
---
{resume}
---

Score each rubric axis from 0 (absent/broken) to 5 (excellent):
- requirement_match: does the resume EVIDENCE the JD's must-have requirements (skills, tools, credentials)? Credit equivalent evidence under different wording; don't credit what isn't there.
- seniority_fit: does the demonstrated scope/level match what this role needs? Both under- and over-qualification cost points.
- impact_quantification: do bullets carry concrete outcomes/numbers, or are they duty lists ("responsible for...")?
- clarity_structure: could you grasp the fit in ~10 seconds? Standard sections, clean single-column structure, no wall of text.
- credibility: is anything GENUINELY off per the list above? Normal career patterns keep this HIGH. 5 = nothing odd; drop points ONLY for a real anomaly, not for studying-while-working or a career change.

Then decide, based on whether this candidate could do THIS job:
- "advance": you would move this candidate to the next stage.
- "maybe": borderline — worth a second look.
- "reject": they genuinely can't do this role as shown.

reject_reasons: 1-4 concrete, FIXABLE reasons (empty list if you chose "advance"). Name a specific problem, phrased fairly; do not invent fraud.
one_liner: ONE sentence (max 25 words) — your actual call, citing the deciding factor.

Return JSON with this exact schema, no prose before or after:
{{
  "decision": "advance|maybe|reject",
  "axes": {{"requirement_match": 0, "seniority_fit": 0, "impact_quantification": 0, "clarity_structure": 0, "credibility": 0}},
  "reject_reasons": [],
  "one_liner": ""
}}
"""


def _parse(raw: dict, model: str) -> RecruiterVerdict | None:
    if not isinstance(raw, dict):
        return None

    decision = str(raw.get("decision", "")).strip().lower()
    if decision not in DECISION_SCORE:
        # Best-effort recovery from a fuzzy label before giving up.
        for key in DECISION_SCORE:
            if key in decision:
                decision = key
                break
        else:
            return None

    axes_raw = raw.get("axes") or {}
    axes: dict[str, int] = {}
    for ax in RUBRIC_AXES:
        try:
            v = int(axes_raw.get(ax, 0))
        except (TypeError, ValueError):
            v = 0
        axes[ax] = max(0, min(5, v))

    reasons: list[str] = []
    for r in raw.get("reject_reasons") or []:
        if isinstance(r, str) and r.strip():
            reasons.append(strip_md_escapes(r.strip()))
        if len(reasons) >= 4:
            break

    one_liner = strip_md_escapes(str(raw.get("one_liner", "")).strip())
    one_liner = re.sub(r"\s+", " ", one_liner)

    return RecruiterVerdict(
        decision=decision,
        axes=axes,
        reject_reasons=reasons,
        one_liner=one_liner,
        model=model,
    )
