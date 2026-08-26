"""Shared, one-shot LLM read of a resume: role label, domain, seniority,
first impression, and section suggestions — one Gemini call, grounded
against the resume text, cached per (resume_id, output_language).

Two consumers (ADR-013):
- `ui_web/routes/profile.py` renders `get_or_generate()`'s output as the
  Profile page's AI-summary fragment.
- `core/matching/semantic_score.py` and `core/llm/prompts.py` use
  `persona_line()` to fill the domain-neutral persona template slot
  (ADR-007) instead of a hardcoded recruiter persona.

A prompt change here affects both surfaces — check Profile rendering
AND scoring/rewrite quality before shipping a prompt edit.

Quality lives in the contract layer, not in a retry button (ADR-005):
one Gemini call, Pydantic-validated, grounding-checked against the
resume, one silent retry, then `None` — nothing renders, nothing feeds
a prompt, and nothing gets cached on repeated failure. Rewritten
2026-08-20 after a hallucination burn: the model wrote "sudden pivot to
art gallery work" for a resume with no art or gallery content. Users
can't fix that by clicking a button; the only real defense is a
structured contract that forces the model to CITE the resume, then we
verify the citations.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

import pydantic

from core import db
from core.llm.gemini import GeminiClient, GeminiError, resolve_api_key
from core.resume.anomalies import missing_sections, present_sections

SECTION_SUGGESTIONS_MAX = 3
_EVIDENCE_MIN_CHARS = 6         # snippets shorter than this are too weak to check
_EVIDENCE_MAX_CHARS = 200       # snippets longer than this are the model regurgitating

# Used when generation is unavailable or fails (no API key, ungrounded twice,
# no resume) and a caller needs a persona line that can't block on retries —
# scoring must never hang or fail because this side-call failed (ADR-013).
GENERIC_PERSONA = "an experienced professional candidate"

# Module-level compiled patterns for the grounding hot path (used up to
# 2 attempts × up to 3 evidence snippets per AI-summary call). Python's
# `re` module caches patterns internally, but a hand-hoisted constant
# skips the cache dict lookup on every call.
_WS_RE = re.compile(r"\s+")
_DIGIT_RE = re.compile(r"\d")
_TOKEN_RE = re.compile(r"\b[A-Za-z][\w-]{2,}\b")


# ── Response schema — Pydantic v2 ─────────────────────────────
# The model wrote "sudden pivot to art gallery work" for a resume with no
# art or gallery content. Users can't fix that by clicking a button; the
# only real defense is a structured contract that forces the model to
# CITE the resume, then we verify the citations. See `_grounded_or_none`.

class _SectionSuggestion(pydantic.BaseModel):
    section: str
    reason: str


class _ResumeSummaryLLM(pydantic.BaseModel):
    """Shape of the raw JSON we ask Gemini for. We NEVER trust these
    fields on face value — `_validate_grounded` cross-checks the
    evidence snippets against the actual resume text before we
    persist or render anything."""
    role_label: str
    # domain/seniority (added for ADR-013): short, code-facing descriptors
    # consumed as scoring/rewrite persona input, not user-facing prose —
    # they don't need their own grounding check the way first_impression
    # does, since they're not specific factual claims about the candidate.
    domain: str = ""
    seniority: str = ""
    first_impression: str
    # Verbatim snippets from the resume that back specific claims in
    # first_impression. Empty list is allowed only if first_impression
    # itself is generic (no specific claim to defend); a specific-claim
    # impression with empty evidence fails validation.
    first_impression_evidence: list[str] = pydantic.Field(default_factory=list)
    section_suggestions: list[_SectionSuggestion] = pydantic.Field(default_factory=list)


def _normalize_for_grounding(s: str) -> str:
    """Collapse whitespace + lowercase. Substring match against this
    normalized form is our grounding test — tolerant enough that
    PDF line-breaks and extra spaces don't cause false negatives,
    strict enough that fabricated content ("art gallery") won't
    accidentally match."""
    return _WS_RE.sub(" ", s.lower().strip())


def _looks_specific(impression: str) -> bool:
    """Heuristic: does the impression make a specific claim that needs
    evidence? Capitalised words that aren't sentence starts (proper
    nouns), numbers, or industry/domain terms are red flags for
    "needs citation". Generic phrasings like 'solid mid-career resume'
    pass without evidence."""
    if not impression:
        return False
    # Any digit → almost certainly a specific claim (years, counts).
    if _DIGIT_RE.search(impression):
        return True
    tokens = _TOKEN_RE.findall(impression)
    # Capitalised words not at position 0 → proper noun candidates.
    # Skip the common start-of-clause stop-words in case a prompt tweak
    # ever produces "I have..." / "The candidate..." style openers.
    for i, t in enumerate(tokens):
        if i == 0:
            continue
        if t[0].isupper() and t.lower() not in {"i", "the", "a", "an"}:
            return True
    return False


def _validate_grounded(
    summary: _ResumeSummaryLLM, resume_norm: str
) -> bool:
    """Every evidence snippet MUST appear in the (already-normalized)
    resume text. If the impression looks specific but has no evidence,
    that also fails — a specific claim without a citation is exactly
    the art-gallery pattern.

    Takes the ALREADY-normalized resume so callers can reuse one
    normalization across retries (see `_grounded_or_none`)."""
    for snippet in summary.first_impression_evidence:
        snip = (snippet or "").strip()
        if not snip:
            continue   # empty snippets are ignored, not counted against
        if len(snip) < _EVIDENCE_MIN_CHARS or len(snip) > _EVIDENCE_MAX_CHARS:
            return False
        if _normalize_for_grounding(snip) not in resume_norm:
            return False
    # Specific claim + no evidence at all → un-grounded.
    if not summary.first_impression_evidence and _looks_specific(summary.first_impression):
        return False
    return True


def _grounded_or_none(
    prompt: str,
    api_key: str,
    resume_text: str,
) -> Optional[_ResumeSummaryLLM]:
    """One Gemini call → Pydantic validation → grounding check.
    Retries ONCE silently on invalid/un-grounded response. Returns
    None if still bad — the caller renders no summary rather than a
    lying one. No user-visible retry button; the server owns quality."""
    client = GeminiClient(api_key=api_key)
    # Normalize once — the resume text doesn't change between attempts.
    resume_norm = _normalize_for_grounding(resume_text)
    for _attempt in range(2):
        try:
            raw = client.generate_json(prompt)
            summary = _ResumeSummaryLLM.model_validate(raw)
            if _validate_grounded(summary, resume_norm):
                return summary
        except (pydantic.ValidationError, GeminiError):
            pass
        # Loop retries once. On the second failure, fall through.
    return None


def _build_prompt(resume_text: str, present: list[str], missing_block: str, location: str, lang_line: str) -> str:
    return f"""{lang_line}

You are a experienced colleague — not a career coach, not an HR
department — glancing at someone's resume and telling them straight what
you think. You'll get their resume text and two facts: which standard
resume sections they already have, and which they don't. Do SIX things:

1. role_label: In 2-5 words, name the FIELD their experience is in (e.g.
   "civil construction coordination", "B2B sales", "BI / data analytics").
   Base this only on their work history — resumes get reused across
   different job applications, so don't assume this is a "target title,"
   just what their actual experience says they've been doing. Lowercase,
   no fluff, no corporate label-speak.

2. domain: In 1-3 words, name the INDUSTRY or sector their experience
   sits in (e.g. "construction", "SaaS sales", "financial services").
   This is consumed by other prompts as plain descriptive input, not
   shown to the user verbatim — pick the most accurate label, don't hedge.

3. seniority: ONE word — "junior", "mid", "senior", or "lead" — your best
   read of their overall seniority from years of experience and scope of
   responsibility shown in the resume.

4. first_impression: ONE sentence (max 22 words), your real reaction
   reading this cold. Say whatever is actually true — could be all
   praise, all criticism, or noting something specific and unusual. Do
   NOT force a "here's what's good, but here's what's weak" sandwich
   every time — that pattern reads as a template, not an opinion.
   Write like you're texting a friend a quick honest take, not writing
   ad copy.

   ANTI-HALLUCINATION RULE (HARD, enforced by the server): every
   specific claim in first_impression MUST be backed by a verbatim
   snippet from the resume in `first_impression_evidence`. If you
   cannot quote the resume verbatim to support a claim, do not make
   it. If nothing specific stands out, say something generic-but-true
   ("solid mid-career resume, no red flags") and leave
   first_impression_evidence empty. Real user burn: model wrote
   "sudden pivot to art gallery work" for a resume with zero art or
   gallery content (2026-08-20). The server now REJECTS impressions
   whose evidence snippets do not appear in the resume — no summary
   renders in that case. Get it right or say something generic.

   Banned English words/phrases (instant AI-slop tell, never use
   them): leverage, robust, seamless, dynamic, passionate, results-driven,
   metric-driven, spearhead, utilize, synergy, cutting-edge, elevate,
   unlock, game-changer, "stands out", "speaks volumes", em-dash chains.
   Banned Spanish equivalents (same rule): apasionado, dinámico, robusto,
   orientado a resultados, sinergia, impulsar, potenciar, "destaca por",
   "cabe destacar", "no se puede negar". Use plain, specific words.
   Contractions / natural conversational phrasing are fine. If something
   is genuinely impressive, say so plainly ("this is solid" / "está
   sólido") — don't dress it up.

5. first_impression_evidence: 0-3 short verbatim snippets from the
   resume text below that back the specific claims in your impression.
   Copy them EXACTLY — including capitalisation and punctuation — so
   the server can verify with substring match. Each snippet: 6-200
   chars. If your impression is generic (no specific claim), return
   an empty list.

6. section_suggestions: Of the MISSING sections listed below, which (if
   any) are actually worth this specific candidate adding? Be selective —
   most resumes don't need most of these. Consider their apparent field
   and, if the location suggests it, the Ottawa/Montreal bilingual job
   market (Languages section matters a LOT there). Almost never suggest
   "References" — modern resumes drop it; only suggest it if something in
   the resume suggests it's expected. Return at most {SECTION_SUGGESTIONS_MAX}
   suggestions, each with a reason under 15 words, same plain-language
   rule as above (no "leverage your robust skillset" nonsense). Empty
   list is a valid, often-correct answer.

TODAY'S DATE: {date.today().strftime("%B %Y")} — use this as "now" when
judging any dates in the resume (e.g. a role starting a few months ago is
current employment, not a typo or something impossible).
CANDIDATE LOCATION: {location or "unknown"}
SECTIONS ALREADY PRESENT: {", ".join(present) or "(none detected)"}
SECTIONS MISSING (only suggest from this list): {missing_block}

RESUME:
---
{resume_text}
---

Return JSON:
{{
  "role_label": "...",
  "domain": "...",
  "seniority": "...",
  "first_impression": "...",
  "first_impression_evidence": ["verbatim snippet 1", "verbatim snippet 2"],
  "section_suggestions": [{{"section": "languages", "reason": "..."}}]
}}
"""


def get_or_generate(resume_id: Optional[int]) -> Optional[dict]:
    """Role label + domain + seniority + first-impression sentence +
    "worth adding?" judgment on missing standard sections, from a single
    Gemini call. Cached by (resume_id, output_language) — a new upload
    gets a new id and thus a fresh generation.

    On failure to produce a grounded summary (after one silent retry),
    returns None — callers render/use nothing rather than a hallucinated
    or ungrounded value. There is DELIBERATELY no user-facing regenerate
    button — regenerate patterns train users to distrust output + invite
    quota-burning spam. Quality lives in the prompt contract + Pydantic
    validation, not in a "try again" affordance.

    The whole body is one try/except — including the cache lookup, not
    just generation — so this function truly never raises; `persona_line`
    relies on that contract instead of wrapping its own call in a second,
    redundant try/except.
    """
    if not resume_id:
        return None
    try:
        from core import settings as app_settings
        # output_language is the correct resolver for LLM-generated text
        # that's shown to the user verbatim (role_label, first_impression).
        # Scoring/rewrite callers reuse this same cache for domain/seniority
        # even though those feed a different-language prompt (ADR-013) — the
        # descriptor is plain input to the model, not rendered prose, so it
        # doesn't need to match reasoning_language.
        lang = app_settings.get_output_language()

        cached = db.get_resume_ai_summary(resume_id, lang)
        # A row from before ADR-013 (or the v15 migration's default-backfill
        # of an old row) has role_label but domain='' and seniority=''. Real
        # generations under the current prompt always populate at least one
        # of those (both are mandatory asks) — treat "both empty" as a stale
        # cache miss so existing resumes get backfilled once, rather than
        # keeping a degraded persona forever.
        if cached and (cached.get("domain") or cached.get("seniority")):
            return cached

        api_key = resolve_api_key()
        if not api_key:
            return None

        resume = db.get_resume(resume_id)
        if not resume:
            return None
        parsed = resume["parsed"]
        resume_text = (parsed.get("raw_text") or "")[:8000].strip()
        if not resume_text:
            return None

        present = [t for _, t in present_sections(parsed)]
        missing = missing_sections(parsed)
        if not missing:
            missing_block = "(none — candidate already has every standard section)"
        else:
            missing_block = ", ".join(t for _, t in missing)
        location = (parsed.get("contact") or {}).get("location", "")

        lang_line = app_settings.language_instruction(lang)
        prompt = _build_prompt(resume_text, present, missing_block, location, lang_line)

        summary = _grounded_or_none(prompt, api_key, resume_text)
        if summary is None:
            # Two attempts came back un-grounded. Don't cache anything;
            # don't render anything. Better silence than a lie.
            return None

        role_label = summary.role_label.strip()[:60]
        domain = summary.domain.strip()[:40]
        seniority = summary.seniority.strip().lower()[:20]
        first_impression = summary.first_impression.strip()[:280]

        missing_keys = {k for k, _ in missing}
        suggestions: list[dict] = []
        for item in summary.section_suggestions:
            key = item.section.strip().lower()
            reason = item.reason.strip()[:160]
            if key in missing_keys and reason:
                suggestions.append({"section": key, "reason": reason})
            if len(suggestions) >= SECTION_SUGGESTIONS_MAX:
                break

        db.save_resume_ai_summary(
            resume_id,
            lang=lang,
            role_label=role_label,
            domain=domain,
            seniority=seniority,
            first_impression=first_impression,
            suggestions=suggestions,
        )
        return {
            "role_label": role_label,
            "domain": domain,
            "seniority": seniority,
            "first_impression": first_impression,
            "suggestions": suggestions,
        }
    except Exception:  # noqa: BLE001 — must never break a caller's render/prompt
        return None


def persona_line(resume_id: Optional[int]) -> str:
    """Best-effort one-sentence persona descriptor for scoring/rewrite
    prompts (ADR-007 + ADR-013): "a {seniority} {role_label} candidate
    with experience in {domain}". Never blocks its caller on a failed
    generation — falls back to `GENERIC_PERSONA` when the profile can't
    be produced (no resume_id, no API key, ungrounded twice, no resume,
    or a bare role_label with no domain/seniority yet cached).
    `get_or_generate` never raises, so no try/except is needed here."""
    summary = get_or_generate(resume_id)
    role_label = (summary or {}).get("role_label") or ""
    if not role_label:
        return GENERIC_PERSONA

    domain = (summary or {}).get("domain") or ""
    seniority = (summary or {}).get("seniority") or ""

    bits = f"a {seniority} {role_label} candidate" if seniority else f"a {role_label} candidate"
    if domain and domain.lower() not in role_label.lower():
        bits += f" with experience in {domain}"
    return bits
