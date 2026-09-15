"""fit_story: the match-story derivation (domain × seniority → human label).
Locks the behaviour validated against Eduardo's real scored jobs (2026-09-15)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.matching import fit_story


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# Candidate: mid-level Business Intelligence / data analytics.
CAND = dict(role_label="data analytics and transformation",
            domain="business intelligence", seniority="mid")


def _label(title, score=90, verdict="strong_fit"):
    return fit_story.build(job_title=title, score=score, verdict=verdict, **CAND).fit_label


def test_in_lane_same_field_same_level():
    _assert(_label("Data Analyst") == "In your lane", "Data Analyst should be in-lane")
    # abbreviation: 'BI' must expand to match 'business intelligence'
    _assert(_label("BI & AI Analyst") == "In your lane", "BI Analyst should be in-lane (abbrev)")
    _assert(_label("Analyst, Business Intelligence") == "In your lane", "BI analyst in-lane")


def test_seniority_reach_up():
    _assert(_label("Senior Data Analyst") == "Reach — level up", "senior same field = reach")
    _assert(_label("Senior Business Intelligence Developer") == "Reach — level up", "senior BI = reach")


def test_generic_word_not_a_domain_match():
    # 'business' alone (shared with 'business intelligence') must NOT make
    # 'Business Operations' read as in-lane — it's a different field.
    st = fit_story.build(job_title="Business Operations Associate", score=90,
                         verdict="strong_fit", **CAND)
    _assert(st.domain_relation == "adjacent", "business ops is a pivot, not in-lane")
    _assert(st.fit_label == "Pivot — new field", f"got {st.fit_label}")


def test_long_shot_new_field_and_level():
    _assert(_label("Senior Manager, Advanced Analytics").startswith("Long shot"),
            "senior-manager off-field = long shot")


def test_weak_score_overrides_geometry():
    _assert(_label("Data Analyst", score=30, verdict="poor_fit") == "Weak match",
            "a poor score is a weak match regardless of domain/level")


def test_seniority_relation_primitive():
    _assert(fit_story.seniority_relation("mid", "Senior Data Analyst") == "up", "mid→senior is up")
    _assert(fit_story.seniority_relation("mid", "Data Analyst") == "at", "no marker = at level")
    _assert(fit_story.seniority_relation("senior", "Junior Analyst") == "down", "senior→junior is down")
    _assert(fit_story.seniority_relation("", "Data Analyst") == "unknown", "no candidate seniority")


def test_job_level_label_is_about_the_vacancy():
    # A fact about the JOB's title level — no candidate needed.
    _assert(fit_story.job_level_label("Senior Data Analyst") == "Senior-level role", "senior title")
    _assert(fit_story.job_level_label("Director, Analytics") == "Leadership role", "director title")
    _assert(fit_story.job_level_label("Junior Analyst") == "Junior-level role", "junior title")
    _assert(fit_story.job_level_label("Data Analyst") == "", "unmarked/mid title = no tag")


def test_seniority_note_populated_on_reach():
    st = fit_story.build(job_title="Senior Data Analyst", score=90, verdict="strong_fit", **CAND)
    _assert("step up" in st.seniority_note.lower(), f"reach note missing: {st.seniority_note}")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all fit_story tests passed")
