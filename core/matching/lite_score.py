"""Lite scoring engine (REQ-016 / ADR-016).

Rank-aware, honest, *local* fit. No LLM in the hot path.

Two signals, both deterministic:

  1. **skills-coverage** — of the skill-like terms the JD emphasises, how
     many appear in the resume (matched / total). This ratio, plus an
     exact-title check, drives the displayed **bucket** (Strong / Good /
     Weak). We never surface a raw comparable-looking %: scores aren't
     calibrated across jobs (ADR-016).

  2. **TF-IDF cosine** — a fast local text-similarity. Its only job here is
     the before/after **delta** — honest movement when the user tailors the
     resume, not a chased number.

Reuses the vectoriser + noise/domain vocab from `tfidf_match` and the
stdlib-only normalise/stems from `lexical`, so this adds no new dependency
beyond scikit-learn (already required).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.matching.lexical import normalize as _normalize, stems as _stems
from core.matching.tfidf_match import DOMAIN_HINTS, EXTRA_NOISE

# How many top-weighted JD terms we treat as the JD's "skills" for the
# coverage ratio. Coverage is over these, NOT over every prose token —
# skills-coverage + title are the dominant ranker features (REQ-016).
_SKILL_TERMS_TOP_N = 25

# Fixed thresholds on our own coverage signal (ADR-016: buckets, not raw %).
_STRONG_MIN = 0.60
_GOOD_MIN = 0.35

# A vectoriser identical to tfidf_match's, kept here so coverage and cosine
# share one tokenisation.
def _vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        max_features=2000,
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9+#]{1,}\b",
    )


def _is_noise(term: str) -> bool:
    if term in EXTRA_NOISE:
        return True
    if " " in term:
        return any(p in EXTRA_NOISE for p in term.split())
    return False


def _resume_membership(resume_norm: str):
    """Return an `in_resume(term)` predicate tolerant of stem variants —
    same rule as tfidf_match, so 'coordinated' matches 'coordinate'."""
    tokens = resume_norm.split()
    token_set = set(tokens)
    stem_set: set[str] = set()
    for t in tokens:
        stem_set.update(_stems(t))

    def in_resume(term: str) -> bool:
        if " " in term:
            if term in resume_norm:
                return True
            return all(_stems(p) & stem_set for p in term.split())
        if term in token_set:
            return True
        return bool(_stems(term) & stem_set)

    return in_resume


@dataclass
class LiteScore:
    bucket: str                      # "Strong" | "Good" | "Weak"
    coverage: float                  # matched / total, 0..1
    similarity: float                # raw cosine, 0..1 (internal, not shown raw)
    title_match: bool
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "coverage": round(self.coverage, 3),
            "similarity": round(self.similarity, 4),
            "title_match": self.title_match,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
        }


def _bucket(coverage: float, title_match: bool) -> str:
    label = "Strong" if coverage >= _STRONG_MIN else "Good" if coverage >= _GOOD_MIN else "Weak"
    # Exact-title match is a strong ranker feature: nudge a borderline
    # Good up to Strong. It can never rescue a Weak (too little overlap).
    if title_match and label == "Good" and coverage >= (_GOOD_MIN + _STRONG_MIN) / 2:
        label = "Strong"
    return label


def _cosine(resume_norm: str, jd_norm: str) -> tuple[float, TfidfVectorizer, Any]:
    vec = _vectorizer()
    matrix = vec.fit_transform([resume_norm, jd_norm])
    sim = float(cosine_similarity(matrix[0:1], matrix[1:2])[0, 0])
    return sim, vec, matrix


def score(resume_text: str, jd_text: str, jd_title: str | None = None) -> LiteScore:
    """Score one resume against one JD. Deterministic, local, no API."""
    if not resume_text.strip() or not jd_text.strip():
        return LiteScore(bucket="Weak", coverage=0.0, similarity=0.0, title_match=False)

    resume_norm = _normalize(resume_text)
    jd_norm = _normalize(jd_text)

    sim, vec, matrix = _cosine(resume_norm, jd_norm)

    # Rank JD terms by TF-IDF weight; the top non-noise ones are our "skills".
    vocab = vec.get_feature_names_out()
    jd_vector = matrix[1].toarray()[0]
    ranked = sorted(
        ((vocab[i], jd_vector[i]) for i in range(len(vocab)) if jd_vector[i] > 0),
        key=lambda x: x[1],
        reverse=True,
    )
    in_resume = _resume_membership(resume_norm)

    skills: list[str] = []
    for term, _w in ranked:
        if _is_noise(term):
            continue
        skills.append(term)
        if len(skills) >= _SKILL_TERMS_TOP_N:
            break
    # Domain tooling present in the JD counts as a skill term even if it
    # ranked below the cut — these are the ones users care about most.
    for hint in DOMAIN_HINTS:
        if hint in jd_norm and hint not in skills:
            skills.append(hint)

    matched = [s for s in skills if in_resume(s)]
    missing = [s for s in skills if not in_resume(s)]
    coverage = len(matched) / len(skills) if skills else 0.0

    title_match = False
    if jd_title:
        title_norm = _normalize(jd_title)
        # Any content word of the title present in the resume counts.
        title_match = any(
            in_resume(w) for w in title_norm.split() if w not in EXTRA_NOISE and len(w) > 2
        )

    return LiteScore(
        bucket=_bucket(coverage, title_match),
        coverage=coverage,
        similarity=sim,
        title_match=title_match,
        matched_skills=matched[:25],
        missing_skills=missing[:15],
    )


def delta(before_text: str, after_text: str, jd_text: str) -> dict[str, float]:
    """Before/after cosine similarity to the JD — honest movement (ADR-016).

    Returns raw cosines (internal) plus their difference. The UI turns this
    into "you moved up", never a chased number.
    """
    jd_norm = _normalize(jd_text)
    before, _, _ = _cosine(_normalize(before_text), jd_norm)
    after, _, _ = _cosine(_normalize(after_text), jd_norm)
    return {
        "before": round(before, 4),
        "after": round(after, 4),
        "delta": round(after - before, 4),
    }
