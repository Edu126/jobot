"""Prep vacancy matching (REQ-023 / ADR-026). Locks down the ladder:
  1. an exact URL auto-binds — across www / https / tracking-param variants,
     and against `job_url_direct` too;
  2. fuzzy company+title proposes the right job, with the TAILORED one winning
     a tie (the search space prioritises tailored);
  3. a pasted JD blob matches on stored description / verbatim company mention;
  4. a weak signal proposes nothing (→ fresh) — a wrong bind would ground the
     kit on the wrong JD (GOV-005);
  5. the search space is tailored ∪ this-résumé's-scored, deduped.

No network. Runs without pytest:
    .venv/bin/python tests/test_prep_matching.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.prep import matching as m  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _job(con, jid, title, company, url="", direct="", desc=""):
    con.execute(
        "INSERT INTO jobs(id,title,company,job_url,job_url_direct,description,first_seen,last_seen) "
        "VALUES (?,?,?,?,?,?,'now','now')",
        (jid, title, company, url, direct, desc),
    )


def _tailor(con, jid):
    con.execute(
        "INSERT INTO tailor_runs(job_id,level,language,tailored_json,created_at) "
        "VALUES (?,'balanced','en','{}','now')", (jid,))


def _seed() -> tuple[Path, str]:
    p = Path(tempfile.mkdtemp()) / "m.sqlite"
    db.init_db(p)
    con = sqlite3.connect(p)
    con.execute("PRAGMA foreign_keys = ON")
    # a résumé + its text_hash (the candidate key job_scores joins on)
    con.execute("INSERT INTO resumes(id,filename,uploaded_at,parsed_json,is_current,text_hash) "
                "VALUES (1,'cv.pdf','now','{}',1,'cand1')")
    # tailored job (rich reuse signal)
    _job(con, "j-cmhc", "Senior Business Analyst", "CMHC",
         url="https://www.linkedin.com/jobs/view/12345?trk=share&utm_source=x",
         desc="Analyze housing affordability data pipelines. Python, SQL, governance.")
    _tailor(con, "j-cmhc")
    # a decoy tailored job at a similar-sounding place
    _job(con, "j-cmch", "Business Analyst", "CMCH Holdings", desc="Generic BA role.")
    _tailor(con, "j-cmch")
    # a SCORED-only job for this résumé (in the search space, not tailored)
    _job(con, "j-scored", "Data Engineer", "Shopify", direct="https://shopify.com/careers/de-9",
         desc="Build data platforms.")
    con.execute(
        "INSERT INTO job_scores(resume_hash,resume_id,job_id,lang,score,verdict,reasoning,"
        "matched_json,gaps_json,model,scored_at) "
        "VALUES ('cand1',1,'j-scored','en',80,'strong','ok','[]','[]','m','now')")
    # a job that is neither tailored nor scored → must NOT be a candidate
    _job(con, "j-ghost", "Ghost Role", "Nowhere", desc="unrelated")
    con.commit()
    con.close()
    return p, "cand1"


def test_exact_url_autobinds_across_variants() -> None:
    p, rh = _seed()
    # different scheme, no www, extra tracking params, trailing slash
    r = m.find_matches(rh, url="http://linkedin.com/jobs/view/12345/?utm_medium=email&trk=foo", path=p)
    _assert(r.bound_job_id == "j-cmhc", f"exact URL should auto-bind j-cmhc, got {r.bound_job_id}")
    _assert(r.candidates == [], "auto-bind returns no confirm list")
    print("PASS test_exact_url_autobinds_across_variants")


def test_exact_url_matches_direct() -> None:
    p, rh = _seed()
    r = m.find_matches(rh, url="https://www.shopify.com/careers/de-9", path=p)
    _assert(r.bound_job_id == "j-scored", f"should bind via job_url_direct, got {r.bound_job_id}")
    print("PASS test_exact_url_matches_direct")


def test_fuzzy_company_title_proposes_and_tailored_wins() -> None:
    p, rh = _seed()
    r = m.find_matches(rh, company="CMHC", role_title="Senior Business Analyst", path=p)
    _assert(r.bound_job_id is None, "fuzzy never auto-binds (only exact URL does)")
    _assert(r.candidates, "should propose at least one candidate")
    _assert(r.candidates[0].job_id == "j-cmhc",
            f"top candidate should be the exact tailored match, got {r.candidates[0].job_id}")
    _assert(len(r.candidates) <= m.MAX_CANDIDATES, "never propose more than the cap")
    print("PASS test_fuzzy_company_title_proposes_and_tailored_wins")


def test_pasted_jd_blob_matches_on_description() -> None:
    p, rh = _seed()
    blob = ("We are CMHC. You will analyze housing affordability data pipelines "
            "using Python and SQL with a governance focus.")
    r = m.find_matches(rh, text=blob, path=p)
    _assert(r.bound_job_id is None, "text never auto-binds")
    _assert(r.candidates and r.candidates[0].job_id == "j-cmhc",
            f"JD blob should surface j-cmhc first, got {[c.job_id for c in r.candidates]}")
    print("PASS test_pasted_jd_blob_matches_on_description")


def test_weak_signal_goes_fresh() -> None:
    p, rh = _seed()
    r = m.find_matches(rh, company="Totally Different Corp", role_title="Underwater Welder", path=p)
    _assert(r.bound_job_id is None and r.candidates == [],
            f"weak signal must propose nothing, got {r.candidates}")
    # no signal at all → fresh
    r2 = m.find_matches(rh, path=p)
    _assert(r2.bound_job_id is None and r2.candidates == [], "no signal → fresh")
    print("PASS test_weak_signal_goes_fresh")


def test_search_space_excludes_untouched_jobs() -> None:
    p, rh = _seed()
    ids = {c["job_id"] for c in db.prep_match_candidates(rh, path=p)}
    _assert("j-ghost" not in ids, "a never-touched job must not be in the search space")
    _assert({"j-cmhc", "j-cmch", "j-scored"} <= ids, f"tailored+scored must be present, got {ids}")
    print("PASS test_search_space_excludes_untouched_jobs")


def test_url_and_company_normalizers() -> None:
    _assert(m.normalize_url("https://www.x.com/a/") == m.normalize_url("http://x.com/a?utm_source=z"),
            "normalizer should collapse scheme/www/tracking/slash")
    _assert(m.normalize_company("CMHC Inc.") == m.normalize_company("cmhc"),
            "company normalizer should drop legal suffix/case")
    _assert(m.normalize_url("") == "" and m.normalize_url("garbage") != "",
            "blank stays blank; bare host normalizes")
    print("PASS test_url_and_company_normalizers")


if __name__ == "__main__":
    test_exact_url_autobinds_across_variants()
    test_exact_url_matches_direct()
    test_fuzzy_company_title_proposes_and_tailored_wins()
    test_pasted_jd_blob_matches_on_description()
    test_weak_signal_goes_fresh()
    test_search_space_excludes_untouched_jobs()
    test_url_and_company_normalizers()
    print("all prep-matching tests passed")
