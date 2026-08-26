"""Prompt templates for the resume rewrite step.

Three levels of tailoring, ordered by how much the LLM is allowed to
deviate from the original resume. All three forbid fabrication of facts.

The LLM is constrained to return JSON matching the parsed-resume schema
(sections dict), so the writer can render it without further parsing.
"""
from __future__ import annotations

import json
from typing import Literal

from core.resume.ai_summary import GENERIC_PERSONA

Level = Literal["conservative", "balanced", "aggressive"]


LEVEL_RULES: dict[Level, str] = {
    "conservative": """
LEVEL: CONSERVATIVE — minimal changes.
- Allowed: reorder bullets to surface the most relevant ones first.
- Allowed: light rephrasing for clarity and grammar.
- Allowed: emphasize keywords from the job description IF they are already
  genuinely present (in any form) in the original resume.
- Forbidden: removing factual content (dates, company names, role titles).
- Forbidden: adding any skill, tool, certification, project, or claim
  that is not explicitly in the original resume.
- Bullet counts per role should stay roughly the same.
""".strip(),
    "balanced": """
LEVEL: BALANCED — meaningful tailoring.
- All Conservative rules apply, plus:
- Allowed: drop bullets that are clearly irrelevant to the job posting.
- Allowed: rewrite bullets for stronger action verbs and impact — but the
  underlying achievement must be unchanged.
- Allowed: re-order and re-phrase the summary to lead with skills the JD
  emphasizes (only if those skills exist in the resume).
- Forbidden: inventing metrics, scope, or seniority not present in the
  original resume.
""".strip(),
    "aggressive": """
LEVEL: AGGRESSIVE — maximum keyword alignment.
- All Balanced rules apply, plus:
- Allowed: substantially rewrite bullets using terminology from the JD,
  provided the underlying experience is real.
- Allowed: restructure the summary entirely to mirror the JD's framing.
- Allowed: collapse or expand bullets to better match the JD's level of
  detail.
- Allowed: re-order skills, group them, or pull skills mentioned inside
  experience bullets into the Skills section.
- Forbidden — under any circumstances: fabricating jobs, dates, schools,
  degrees, certifications, employer names, or tools the candidate has
  never used. If something is genuinely missing, leave it missing.
""".strip(),
}


def _system_preamble(persona: str) -> str:
    """Domain-neutral persona (ADR-007 + ADR-013): the recruiter/editor
    voice is anchored to the candidate's own resume (role/domain/
    seniority), not a hardcoded industry. `persona` comes from
    `core.resume.ai_summary.persona_line` — same source scoring uses, so
    a candidate reads as the same person across scoring and tailoring."""
    return f"""
You are an expert resume editor helping {persona} tailor their existing
resume to a specific job posting.

You will follow the LEVEL rules below, then return a JSON object with the
tailored content. NEVER fabricate experience, skills, dates, or
credentials. Honesty matters more than keyword match.
""".strip()


_OUTPUT_SCHEMA = """
OUTPUT — return ONLY this JSON object, no surrounding text:

{
  "sections": {
    "summary":        ["paragraph or bullet", "..."],
    "experience":     ["bullet or paragraph", "..."],
    "education":      ["..."],
    "skills":         ["..."],
    "certifications": ["..."],
    "projects":       ["..."],
    "publications":   ["..."],
    "volunteer":      ["..."],
    "awards":         ["..."],
    "languages":      ["..."],
    "interests":      ["..."],
    "references":     ["..."]
  },
  "cover_letter": "Full cover letter as a single string. 200-350 words. Plain text only — no markdown, no bullet glyphs, no decorative characters. Use \\n\\n between paragraphs. Address it 'Dear Hiring Manager,' unless the JD names someone specific. Reference 1-2 specific JD requirements and how the candidate's real experience matches. Close with a clear call to next steps (interview, conversation). Sign with the candidate's ACTUAL NAME from the CANDIDATE CONTACT block above — never use placeholders like [Your Name], Your Name, [Name], or [Candidate]. Match the same LEVEL of tailoring as the resume. Canadian professional tone — direct, not flowery.",
  "notes": "1–2 sentence summary of what you changed in the resume and why.",
  "warnings": ["any places where the JD asked for something the candidate lacks; leave empty if none"]
}

Rules for the sections dict:
- Use ONLY the section keys above. Omit any section that has no content.
- Each value is a list of strings. Each string is one bullet OR one
  short paragraph. Do NOT prefix bullets with "-" or "•" — the renderer
  adds those.
- Preserve company names, employer names, school names, and dates from
  the original VERBATIM. Do not translate or rephrase them.

Rules for cover_letter:
- Never invent achievements, employers, or qualifications. Use only
  what is in the resume above.
- If the JD requires something the candidate lacks, do NOT fake it —
  pivot to an adjacent strength.
- The candidate's actual name is in the CANDIDATE CONTACT block. Use
  that EXACT name in the signature. NEVER emit "[Your Name]", "Your
  Name", "[Name]", "[Candidate Name]", or similar placeholder text —
  those look like unfinished drafts.
""".strip()


def build_rewrite_prompt(
    parsed_sections: dict,
    contact_summary: dict,
    job_description: str,
    level: Level,
    company_context: str = "",
    output_language: str = "en",
    persona: str = GENERIC_PERSONA,
) -> str:
    """Build the full prompt for a single rewrite call.

    parsed_sections: the `sections` dict from parse_resume.
    contact_summary: candidate's name + location, for context only — the
        LLM does not return contact info, we merge it back ourselves.
    job_description: raw JD text.
    level: which ruleset to apply.
    company_context: optional pre-researched company briefing. The LLM
        is told this is *background only* — it must not invent facts to
        match anything in here.
    output_language: which language the tailored resume + cover letter
        come back in ('en' | 'es'). User-controlled via Profile — a
        Colombian user with a Spanish resume applying to a multinational
        Bogotá office wants English output; the reverse also happens.
    persona: domain-neutral candidate descriptor (ADR-007 + ADR-013),
        e.g. "a mid BI analyst candidate with experience in fintech".
        Caller resolves this via `core.resume.ai_summary.persona_line`;
        defaults to a generic line when the caller has no resume_id.
    """
    if level not in LEVEL_RULES:
        raise ValueError(f"Unknown level: {level!r}")

    sections_json = json.dumps(parsed_sections, indent=2, ensure_ascii=False)
    contact_json = json.dumps(contact_summary, indent=2, ensure_ascii=False)
    jd_clean = job_description.strip()

    company_block = ""
    if company_context.strip():
        company_block = (
            "\nCOMPANY CONTEXT (researched from the web — use for tone and "
            "framing only; do NOT invent candidate qualifications to match it):\n"
            f"\"\"\"\n{company_context.strip()}\n\"\"\"\n"
        )

    from core.settings import language_instruction

    return f"""{_system_preamble(persona)}

{language_instruction(output_language)}

{LEVEL_RULES[level]}

CANDIDATE CONTACT (for context — do NOT return this):
{contact_json}

ORIGINAL RESUME SECTIONS (authoritative source of facts):
{sections_json}
{company_block}
JOB DESCRIPTION:
\"\"\"
{jd_clean}
\"\"\"

{_OUTPUT_SCHEMA}
"""
