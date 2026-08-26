"""TF-IDF based matching between resume text and a job description.

Two outputs:
- similarity_score (0-100): cosine similarity, rescaled
- missing_keywords: top terms in the job description, ranked by TF-IDF
  weight, that don't appear in the resume

This is intentionally cheap and deterministic. The LLM-based rewrite step
sits on top of this; here we only do retrieval-style matching.
"""
from __future__ import annotations

import math
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.matching.lexical import normalize as _normalize, stems as _stems


# Domain-aware extras across several fields, not tied to any one
# candidate's industry (REQ-006). Adds nothing for unrelated jobs; helps
# the matcher recognize and weight domain tooling/vocabulary that generic
# English stopword lists ignore. AEC terms sit here as one peer domain
# among several — add more as new domains show up, not as the default.
DOMAIN_HINTS = {
    # AEC / construction
    "bim", "revit", "navisworks", "autocad", "civil 3d", "sketchup",
    "tekla", "ifc", "cobie", "lod", "clash detection", "rfi",
    "takeoff", "quantity takeoff", "ms project", "primavera", "p6",
    "pmp", "capm", "gantt", "wbs",
    "estimating", "cost control", "blueprint", "construction documents",
    # Sales / B2B
    "crm", "salesforce", "hubspot", "pipeline", "quota", "prospecting",
    "cold outreach", "account management", "b2b", "b2c", "arr", "mrr",
    # BI / data analytics
    "sql", "tableau", "power bi", "looker", "etl", "data warehouse",
    "dashboards", "kpi reporting",
    # Tech / software
    "python", "javascript", "react", "aws", "ci/cd", "microservices",
    "bilingual",
}

# Words to ignore as "missing keywords" even if they're TF-IDF heavy in the
# JD. Mostly boilerplate from job postings.
EXTRA_NOISE = {
    "team", "teams", "work", "works", "ability", "experience", "experiences",
    "years", "year", "role", "roles", "company", "companies",
    "candidate", "candidates", "opportunity", "opportunities", "position", "positions",
    "responsibilities", "duties", "qualifications", "requirements",
    "applicant", "applicants", "join", "joining", "growing", "looking",
    "seeking", "seeks", "hiring", "hire", "hires",
    "preferred", "required", "mandatory", "essential", "must", "client", "clients",
    "based", "including", "across", "various", "strong", "excellent", "ideal",
    "successful", "willing", "etc", "able", "knowledge", "asset", "assets",
    "advanced", "intermediate", "basic",
    "use", "using", "used", "uses",
    "mixed", "lead", "leads", "leading",  # title/verb noise — pair-words handle real signal
    "new", "well", "good", "great", "high", "low",
    "field", "fields", "related", "relevant",
    "responsible", "ensure", "ensuring", "provide", "providing", "support",
    "supporting", "collaborate", "collaborating",
}


def _rescale_similarity(sim: float) -> int:
    """Map cosine similarity → 0–100 score.

    Real resume↔JD cosine similarities rarely exceed 0.40, even for
    strong matches. A linear * 160 rescale (the old approach) made
    strong matches look mediocre. A sqrt-based curve gives more
    headroom in the mid range:

        sim 0.05 → 33    (weak — barely related)
        sim 0.10 → 47    (some overlap)
        sim 0.20 → 67    (decent — workable with tailoring)
        sim 0.30 → 82    (strong)
        sim 0.40 → 95    (very strong)
        sim 0.50+ → 100  (effectively perfect)
    """
    if sim <= 0:
        return 0
    return min(100, int(round(math.sqrt(sim) * 150)))


def match(resume_text: str, job_description: str, top_n_missing: int = 15) -> dict[str, Any]:
    """Compare a resume against a single job description."""
    if not resume_text.strip() or not job_description.strip():
        return {
            "similarity_score": 0,
            "matched_keywords": [],
            "missing_keywords": [],
            "top_jd_terms": [],
        }

    resume_norm = _normalize(resume_text)
    jd_norm = _normalize(job_description)

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        max_features=2000,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9+#]{1,}\b",
    )
    matrix = vectorizer.fit_transform([resume_norm, jd_norm])
    sim = float(cosine_similarity(matrix[0:1], matrix[1:2])[0, 0])
    score = _rescale_similarity(sim)

    vocab = vectorizer.get_feature_names_out()
    jd_vector = matrix[1].toarray()[0]

    # Sort JD terms by weight, descending.
    ranked = sorted(
        ((vocab[i], jd_vector[i]) for i in range(len(vocab)) if jd_vector[i] > 0),
        key=lambda x: x[1],
        reverse=True,
    )

    resume_tokens = resume_norm.split()
    resume_token_set = set(resume_tokens)
    resume_stem_set: set[str] = set()
    for t in resume_tokens:
        resume_stem_set.update(_stems(t))

    def in_resume(term: str) -> bool:
        """Treat a term as present if:
          - unigram: exact, OR any stem variant of it is in the resume's
            stem set
          - bigram: substring in resume, OR every word's stem variants
            have a hit in the resume
        """
        if " " in term:
            if term in resume_norm:
                return True
            parts = term.split()
            return all(_stems(p) & resume_stem_set for p in parts)
        if term in resume_token_set:
            return True
        return bool(_stems(term) & resume_stem_set)

    def is_noise(term: str) -> bool:
        """Drop a term if it's pure noise or — for bigrams — contains ANY
        noise word. Reason for the aggressive bigram rule: a phrase like
        'asset leed' or 'leed preferred' looks misleading in the missing
        list. The meaningful word ('leed') still appears as a unigram
        elsewhere, so we lose no signal.
        """
        if term in EXTRA_NOISE:
            return True
        if " " in term:
            parts = term.split()
            if any(p in EXTRA_NOISE for p in parts):
                return True
        return False

    matched, missing, top_terms = [], [], []
    for term, weight in ranked:
        if is_noise(term):
            continue
        top_terms.append({"term": term, "weight": round(float(weight), 4)})
        if in_resume(term):
            matched.append(term)
        else:
            missing.append(term)

    # Boost domain hints to the front of the missing list if present in JD.
    domain_in_jd = [t for t in DOMAIN_HINTS if t in jd_norm and not in_resume(t)]
    # Use dict to dedupe while preserving order.
    missing_ordered = list(dict.fromkeys(domain_in_jd + missing))

    return {
        "similarity_score": score,
        "matched_keywords": matched[:25],
        "missing_keywords": missing_ordered[:top_n_missing],
        "top_jd_terms": top_terms[:25],
    }
