"""The gap map — a candidate's REAL gaps as a tactical 3-pillar panel
(REQ-019 base + REQ-020 / ADR-022 / ADR-023 / ADR-024).

Where gap_enhance.py answers a gap inside one job's detail (JD-specific, lazy),
this collects gaps across ALL the résumé's scored jobs and turns them into a
diagnostic panel — the candidate-level "distance between who you are and the job
you want" (product vision: gap monetized 3×).

Mechanism:
1. `db.gap_counts_for_resume` aggregates every gap across `job_scores` with a
   frequency count — pure SQL, no LLM (ADR-022).
2. Each DISTINCT gap is classified JD-FREE in ONE batched call (ADR-023): résumé
   × gap → {kind: wording|real, suggestion, category, canonical}. Cached per-gap
   in `gap_classification`, so repeat renders are ~free and only newly-seen gaps
   cost a call. Already-known canonicals are fed back as anchors so clusters stay
   stable across incremental calls.
3. REAL gaps are grouped by `canonical` (variants like "Fluent French" +
   "Bilingual French (CBC)" collapse into one concept), bucketed into 3 pillars
   (technical / certifications / domain), ranked by summed count, top 5 each.
4. Clusters the user dismissed as false positives (ADR-024) are filtered out.

Honesty is the product (GOV-005): when unsure a gap is classified REAL, and a
real gap's suggestion is an honest defense hook (lead with transferable
strength), never an invented skill or a course pitch.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.llm.sanitize import strip_md_escapes
from core.matching import semantic_score as ss
from core.matching.gap_enhance import _fuzzy_match
from core.resume import ai_summary
from core.settings import language_instruction

# Own prompt version (JD-free classification). Bump to invalidate the
# gap_classification cache without deleting it (ADR-006 convention).
# 2026-09-02: +category +canonical (ADR-023).
PROMPT_VERSION = "2026-09-02-jdfree-pillars-clusters"

MAX_RESUME_CHARS = 12000
MAX_GAPS_PER_CALL = 40   # distinct gaps; short phrases, one call comfortably fits
MAX_ANCHORS = 40         # existing canonical labels fed back to stabilise clusters
VALID_KINDS = ("wording", "real")
PILLARS = ("technical", "certifications", "domain")
DEFAULT_PILLAR = "domain"   # where an unknown/ambiguous category lands (ADR-023)
TOP_PER_PILLAR = 5


@dataclass
class GapCluster:
    canonical: str          # the concept label shown on the pill
    count: int              # summed roles blocked across the cluster's variants
    category: str           # "technical" | "certifications" | "domain"
    suggestion: str         # defense hook for the concept
    members: list[str] = field(default_factory=list)   # the raw variant surface-forms

    def to_dict(self) -> dict:
        return asdict(self)


def build_gap_map(
    resume_id: int,
    resume_text: str,
    client: GeminiClient | None,
    *,
    lang: str | None = None,
) -> dict[str, list[GapCluster]]:
    """Return the candidate's REAL gaps bucketed into the 3 pillars, each pillar
    ranked by cluster frequency and capped at TOP_PER_PILLAR. Empty pillars when
    nothing's scored or the résumé is text-less. `client` may be None (no API
    key) — then we render from cached classifications only and never classify new
    gaps. Gaps we can't classify (no client / quota out) still appear, honestly,
    as real with no suggestion (own cluster, domain pillar) — never dropped or
    faked. Dismissed clusters (ADR-024) are filtered out."""
    empty: dict[str, list[GapCluster]] = {p: [] for p in PILLARS}
    if not resume_text.strip():
        return empty
    lang = ss._resolve_lang(lang)

    counts = db.gap_counts_for_resume(
        resume_id, lang, ss.PROMPT_VERSION, ss.SCORING_VERSION,
    )
    if not counts:
        return empty

    cached = db.get_gap_classifications(resume_id, list(counts), lang, PROMPT_VERSION)
    missing = [g for g in counts if g not in cached]

    if missing and client is not None and not client.all_models_exhausted():
        persona = ai_summary.persona_line(resume_id)
        anchors = _known_canonicals(cached)
        fresh = _classify(
            resume_text, missing[:MAX_GAPS_PER_CALL], client,
            lang=lang, persona=persona, anchors=anchors,
        )
        if fresh:
            db.save_gap_classifications(
                resume_id, lang, PROMPT_VERSION,
                [{"gap": g, **v} for g, v in fresh.items()],
            )
            cached.update(fresh)

    dismissed = db.get_gap_dismissals(resume_id, lang)

    # Group REAL gaps by canonical label into clusters. `peaks` holds the count of
    # the member whose defense hook each cluster currently shows (-1 = none yet),
    # so the most-frequent variant that HAS a hook wins.
    clusters: dict[str, GapCluster] = {}
    peaks: dict[str, int] = {}
    for gap, count in counts.items():
        c = cached.get(gap) or {}
        kind = c.get("kind", "real")
        if kind not in VALID_KINDS:
            kind = "real"
        if kind != "real":
            continue   # wording gaps live per-job (ADR-021), not in the map

        category = c.get("category", DEFAULT_PILLAR)
        if category not in PILLARS:
            category = DEFAULT_PILLAR
        # Unclassified / label-less → the gap is its own cluster. Cluster key +
        # dismissal lookup are both lower-cased so a re-cased canonical still
        # matches a prior dismissal (ADR-024).
        canonical = (c.get("canonical") or "").strip() or gap
        key = canonical.lower()
        if key in dismissed:
            continue   # user dismissed this cluster as a false positive

        sug = c.get("suggestion", "")
        cl = clusters.get(key)
        if cl is None:
            clusters[key] = GapCluster(
                canonical=canonical, count=count, category=category,
                suggestion=sug, members=[gap],
            )
            peaks[key] = count if sug else -1
        else:
            cl.count += count
            cl.members.append(gap)
            # Highest-count member that has a hook wins the representative hook.
            if sug and count > peaks[key]:
                cl.suggestion, peaks[key] = sug, count

    # Bucket into pillars, rank by cluster count (then alpha for stable ties),
    # cap each at TOP_PER_PILLAR.
    out: dict[str, list[GapCluster]] = {p: [] for p in PILLARS}
    for cl in clusters.values():
        cl.members.sort(key=str.lower)
        out[cl.category].append(cl)
    for p in PILLARS:
        out[p].sort(key=lambda e: (-e.count, e.canonical.lower()))
        out[p] = out[p][:TOP_PER_PILLAR]
    return out


def _known_canonicals(cached: dict[str, dict]) -> list[str]:
    """Distinct canonical labels already assigned to REAL gaps — fed back to the
    next classify call so new variants attach to existing clusters (ADR-023)."""
    seen: list[str] = []
    lowered: set[str] = set()
    for c in cached.values():
        if c.get("kind") != "real":
            continue
        canon = (c.get("canonical") or "").strip()
        if canon and canon.lower() not in lowered:
            lowered.add(canon.lower())
            seen.append(canon)
    return seen[:MAX_ANCHORS]


def _classify(
    resume_text: str,
    gaps: list[str],
    client: GeminiClient,
    *,
    lang: str,
    persona: str,
    anchors: list[str],
) -> dict[str, dict]:
    """One JD-free call → {gap: {kind, suggestion, category, canonical}} for the
    given gaps. {} on any failure (caller degrades to honest 'real, no
    suggestion')."""
    resume_snippet = resume_text.strip()[:MAX_RESUME_CHARS]
    prompt = _build_prompt(resume_snippet, gaps, persona=persona, lang=lang, anchors=anchors)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return {}
    return _parse_response(raw, gaps)


def _build_prompt(
    resume: str, gaps: list[str], *, persona: str, lang: str, anchors: list[str],
) -> str:
    gaps_block = "\n".join(f"- {g}" for g in gaps)
    anchor_block = ""
    if anchors:
        existing = "\n".join(f"- {a}" for a in anchors)
        anchor_block = f"""
EXISTING CLUSTER LABELS (reuse one VERBATIM as the "canonical" when a gap below
means the same concept — this keeps the same idea from splitting into two):
{existing}
"""
    return f"""You are helping {persona} understand the gaps between their résumé and the jobs they are targeting — HONESTLY. Below is the résumé and a list of GAPS collected across many job postings (requirements a scoring pass did not clearly find in the résumé).

{language_instruction(lang)}

For EACH gap, decide, judging ONLY by what the résumé below contains:
- "wording": the candidate genuinely HAS this (it appears in the résumé — possibly under a synonym, abbreviation, another language, or a tail section), just not phrased the way jobs name it. suggestion = the concrete, honest rewording, mapping to real résumé content.
- "real": the résumé does NOT evidence this in any form. suggestion = a DEFENSE HOOK: an honest way the candidate can address it if a recruiter or interviewer raises it — lead with the closest transferable strength actually in the résumé, then frame the gap plainly, without apologizing or overclaiming.

Also for EACH gap return:
- "category": exactly one of "technical" (hard skills, software, programming languages, analytical/technical tools), "certifications" (certifications, licenses, security clearances, spoken languages and proficiency levels), or "domain" (years of industry-specific experience, methodologies, sector/domain knowledge, and anything that fits neither of the other two).
- "canonical": a SHORT concept label (2-4 words) for the underlying requirement. Give the SAME canonical to gaps that are the same concept phrased differently or in another language (e.g. "Fluent French" and "Bilingual French (CBC)" → the same canonical). Different concepts get different canonicals.
{anchor_block}
RULES (non-negotiable):
1. NEVER invent, assume, or suggest claiming something the résumé does not support. If unsure the candidate truly has it, classify "real". When in doubt, "real".
2. Do NOT recommend courses, certifications, or training (out of scope).
3. Echo each gap's text back EXACTLY as given so it can be matched.

RÉSUMÉ:
---
{resume}
---

GAPS:
{gaps_block}

Return JSON with this exact schema — no prose before or after:
{{
  "classifications": [
    {{ "gap": "<exact gap text>", "kind": "wording" | "real", "suggestion": "<one honest, concrete sentence>", "category": "technical" | "certifications" | "domain", "canonical": "<short concept label>" }}
  ]
}}

One entry per gap above."""


def _parse_response(raw: dict, gaps: list[str]) -> dict[str, dict]:
    """{gap: {kind, suggestion, category, canonical}} for gaps the model
    returned. Missing/garbled gaps are simply omitted (caller keeps them as
    honest 'real')."""
    items = raw.get("classifications")
    by_gap: dict[str, dict] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                g = str(item.get("gap", "")).strip()
                if g:
                    by_gap.setdefault(g, item)

    out: dict[str, dict] = {}
    for gap in gaps:
        item = by_gap.get(gap) or _fuzzy_match(gap, by_gap)
        if not item:
            continue
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in VALID_KINDS:
            kind = "real"
        category = str(item.get("category", "")).strip().lower()
        if category not in PILLARS:
            category = DEFAULT_PILLAR
        suggestion = strip_md_escapes(str(item.get("suggestion", "")).strip())
        canonical = strip_md_escapes(str(item.get("canonical", "")).strip())
        out[gap] = {
            "kind": kind, "suggestion": suggestion,
            "category": category, "canonical": canonical,
        }
    return out
