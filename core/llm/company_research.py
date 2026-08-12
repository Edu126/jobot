"""Look up live company context using Gemini's Google Search grounding.

When the user opts in on the Tailor tab, we make a quick separate Gemini
call with the GoogleSearch tool enabled. The model summarizes what it
finds about the company. We pass that summary into the rewrite prompt as
additional context.

Free under Gemini Flash. One extra API call per tailoring run when opted in.

Design note: we do NOT reuse the rewrite GeminiClient here because that
client is configured with response_mime_type='application/json', which
is incompatible with tools. We instantiate a parallel client for
research only.
"""
from __future__ import annotations

from dataclasses import dataclass

from google import genai
from google.genai import types

from .gemini import DEFAULT_MODEL, GeminiError


@dataclass
class CompanyResearch:
    summary: str            # plain-text briefing
    sources: list[str]      # URLs Gemini cited (may be empty)


_PROMPT_TEMPLATE = """\
You are researching a company for a job applicant who is about to write a
tailored resume and cover letter.

Provide a concise briefing (2–4 short paragraphs) on the company below.
Cover, as best you can find:
- What the company does and the industry
- Size, location, and footprint
- Any recent news, growth focus, or hiring focus
- Culture and tone clues a cover letter writer should match
  (formal vs. casual, mission-driven vs. commercial, etc.)

If the role title is provided, focus the briefing on what someone
applying for that role should know.

Be factual. If you can't find solid information, say so plainly — DO NOT
invent details. Keep the briefing under 250 words.

Company name: {company}
{role_line}
"""


def fetch_company_context(
    api_key: str,
    company: str,
    role_title: str = "",
    model_name: str = DEFAULT_MODEL,
) -> CompanyResearch:
    """Run a grounded Gemini search and return a plain-text briefing."""
    if not api_key:
        raise GeminiError("No Gemini API key for company research.")
    if not company.strip():
        return CompanyResearch(summary="", sources=[])

    role_line = f"Role title: {role_title.strip()}" if role_title.strip() else ""
    prompt = _PROMPT_TEMPLATE.format(company=company.strip(), role_line=role_line)

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        temperature=0.2,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )
    except Exception as exc:
        raise GeminiError(f"Company research call failed: {exc}") from exc

    text = (response.text or "").strip()

    # Pull citation URLs out of the grounding metadata if present.
    sources: list[str] = []
    try:
        candidates = getattr(response, "candidates", None) or []
        for c in candidates:
            gm = getattr(c, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", None) or []
            for ch in chunks:
                web = getattr(ch, "web", None)
                if web and getattr(web, "uri", None):
                    sources.append(web.uri)
    except Exception:
        pass

    # de-dupe while preserving order
    seen: set[str] = set()
    sources = [s for s in sources if not (s in seen or seen.add(s))]

    return CompanyResearch(summary=text, sources=sources)
