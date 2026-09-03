"""Company outlook for Prep (REQ-023 / ADR-027) — the structured, cached,
Tailor-shared briefing behind the mockup's 3-facet + news panel.

Built **two-hop** because the GoogleSearch grounding tool can't emit JSON:
  hop 1 — `company_research.fetch_company_context`: a grounded plain-text
          briefing + citation URLs (spends Google Search grounding quota; the
          only call that does — llm-surface). `language_instruction` applied.
  hop 2 — one JSON-mode `GeminiClient` call that splits hop 1's text into
          {culture_tone, strategic_focus, recent_news:[{headline,date,url}]}.

Cached in `company_outlook` keyed company_norm × role × lang × prompt_version
(ADR-008 rule 3), read/written by both Tailor and Prep. `use_cache=False` is
the sanctioned "Refresh news intel" path (ADR-027 — live data ages, the one
regenerate that isn't an escape hatch).

Honesty (GOV-005): hop 1 is instructed not to invent; hop 2 only reshapes what
hop 1 returned — it must not add facts. Any failure returns None and the caller
renders nothing (grounded-or-none, ADR-005), never a fabricated card.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core import db
from core.llm import company_research
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.prep.matching import normalize_company
from core.settings import get_output_language, language_instruction

# Bump when either hop's prompt changes — a version mismatch on read is a miss
# (regenerate), never a delete (same convention as gap_enhance.PROMPT_VERSION).
PROMPT_VERSION = "2026-09-03-3facet-news"

MAX_BRIEFING_CHARS = 6000
MAX_NEWS = 4


@dataclass
class NewsItem:
    headline: str
    date: str = ""
    url: str = ""


@dataclass
class CompanyOutlook:
    culture_tone: str = ""
    strategic_focus: str = ""
    recent_news: list[NewsItem] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    verified_at: str = ""

    def is_empty(self) -> bool:
        return not (self.culture_tone or self.strategic_focus or self.recent_news)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_dict_for_cache(self) -> dict[str, Any]:
        """Only the facets go in `outlook_json`; `sources` is a separate column
        and `verified_at` is the row's write time."""
        return {
            "culture_tone": self.culture_tone,
            "strategic_focus": self.strategic_focus,
            "recent_news": [asdict(n) for n in self.recent_news],
        }


def _resolve_lang(lang: Optional[str]) -> str:
    return lang if lang is not None else get_output_language()


def _row_to_outlook(row: dict) -> CompanyOutlook:
    o = row.get("outlook") or {}
    news = [
        NewsItem(headline=str(n.get("headline", "")).strip(),
                 date=str(n.get("date", "")).strip(),
                 url=str(n.get("url", "")).strip())
        for n in (o.get("recent_news") or [])
        if isinstance(n, dict) and str(n.get("headline", "")).strip()
    ]
    return CompanyOutlook(
        culture_tone=str(o.get("culture_tone", "")).strip(),
        strategic_focus=str(o.get("strategic_focus", "")).strip(),
        recent_news=news[:MAX_NEWS],
        sources=list(row.get("sources") or []),
        verified_at=row.get("verified_at", ""),
    )


def get_or_generate(
    company: str,
    role_title: str,
    client: GeminiClient,
    api_key: str,
    *,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> Optional[CompanyOutlook]:
    """Cache-aware entry point. Returns the structured outlook, generating it
    two-hop on a miss (or always, when `use_cache=False` = manual refresh).
    None on any failure or an empty briefing — the caller renders nothing."""
    company = (company or "").strip()
    if not company:
        return None
    lang = _resolve_lang(lang)
    role_title = (role_title or "").strip()
    company_norm = normalize_company(company)

    if use_cache:
        cached = db.get_company_outlook(company_norm, role_title, lang, PROMPT_VERSION, path=path)
        if cached is not None:
            return _row_to_outlook(cached)

    if client.all_models_exhausted():
        return None

    # hop 1 — grounded briefing (spends grounding quota; may raise on quota/kill).
    try:
        research = company_research.fetch_company_context(
            api_key, company, role_title, lang=lang
        )
    except (QuotaExhaustedError, GeminiError):
        return None
    if not research.summary.strip():
        return None

    # hop 2 — structure into facets (normal JSON call on the fallback chain).
    facets = _structure(research.summary, client, lang=lang)
    if facets is None:
        return None

    outlook = CompanyOutlook(
        culture_tone=facets.get("culture_tone", ""),
        strategic_focus=facets.get("strategic_focus", ""),
        recent_news=[
            NewsItem(headline=n["headline"], date=n.get("date", ""), url=n.get("url", ""))
            for n in facets.get("recent_news", [])
        ],
        sources=research.sources,
    )
    if outlook.is_empty():
        return None

    model_used = client.last_model_used or client.model_name or ""
    db.save_company_outlook(
        company_norm, role_title, lang, PROMPT_VERSION,
        outlook.to_dict_for_cache(), research.sources, model_used, path=path,
    )
    # Re-read so verified_at reflects the stored write time.
    stored = db.get_company_outlook(company_norm, role_title, lang, PROMPT_VERSION, path=path)
    return _row_to_outlook(stored) if stored else outlook


def _structure(briefing: str, client: GeminiClient, *, lang: str) -> Optional[dict]:
    """Hop 2: reshape the grounded briefing into the 3 facets + news list. Does
    NOT add facts — it only organizes what hop 1 already found (GOV-005)."""
    prompt = _build_structuring_prompt(briefing[:MAX_BRIEFING_CHARS], lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    return _parse_facets(raw)


def _build_structuring_prompt(briefing: str, *, lang: str) -> str:
    return f"""You are reorganizing an existing company briefing into a fixed structure for a job candidate preparing for an interview. The briefing was produced by a grounded web search.

{language_instruction(lang)}

Use ONLY what the briefing below states. Do NOT add companies facts, news, or details that are not in the briefing. If a field isn't covered, return an empty string (or an empty list for news). Never invent.

Produce three things:
- "culture_tone": 1–2 sentences on the company's culture and communication tone (formal vs casual, risk-averse vs fast-moving, mission vs commercial), as evidenced in the briefing.
- "strategic_focus": 1–2 sentences on what the company is focused on / investing in (products, markets, growth, technology).
- "recent_news": up to {MAX_NEWS} concrete recent items the briefing mentions. Each item: a short "headline", an optional "date" (as written in the briefing, else ""), and an optional "url" ONLY if the briefing gives one (else ""). Empty list if the briefing cites no specific news.

BRIEFING:
---
{briefing}
---

Return JSON with this exact schema — no prose before or after:
{{
  "culture_tone": "<string>",
  "strategic_focus": "<string>",
  "recent_news": [
    {{ "headline": "<string>", "date": "<string>", "url": "<string>" }}
  ]
}}"""


def _parse_facets(raw: dict) -> dict:
    """Defensive extraction — a missing/renamed field degrades to empty, never
    raises, so a flaky structuring call yields a partial card, not a crash."""
    def _s(v: Any) -> str:
        return str(v).strip() if v is not None else ""

    news_out: list[dict] = []
    for n in (raw.get("recent_news") or []):
        if isinstance(n, dict):
            head = _s(n.get("headline"))
            if head:
                news_out.append({"headline": head, "date": _s(n.get("date")), "url": _s(n.get("url"))})
    return {
        "culture_tone": _s(raw.get("culture_tone")),
        "strategic_focus": _s(raw.get("strategic_focus")),
        "recent_news": news_out[:MAX_NEWS],
    }
