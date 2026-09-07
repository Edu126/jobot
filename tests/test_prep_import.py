"""Prep import + self-contained score (REQ-025 / ADR-030). Locks down:
  1. `create_prep_session(match_score=..)` stores it and `list_prep_sessions`
     returns it via COALESCE (imported/pasted session carries its own fit);
  2. a bound session with NO stored score still derives one from job_scores
     (the COALESCE fallback is intact);
  3. `_import_and_score` scrapes a URL (job_from_url) + scores it;
  4. it extracts pasted text (extract_job_from_text) when there's no URL;
  5. a scrape failure degrades to an honest message, never a fabricated job.

No network: the importer + scorer are monkeypatched. Runs without pytest:
    .venv/bin/python tests/test_prep_import.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json  # noqa: E402

from core import db  # noqa: E402
from core.jobs.from_url import UrlExtractError  # noqa: E402
from core.matching.semantic_score import ScoreResult  # noqa: E402
from core.prep import fit  # noqa: E402
from ui_web.routes import prep  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "imp.sqlite"
    db.init_db(p)
    return p


def test_stored_match_score_roundtrips():
    p = _fresh()
    sid = db.create_prep_session("h1", "Kanak", "GTM", "jd text", "en",
                                 "pasted_link", match_score=73, path=p)
    rows = db.list_prep_sessions("h1", path=p)
    row = next(r for r in rows if r["id"] == sid)
    _assert(row["match_score"] == 73, f"stored score should surface, got {row['match_score']}")
    print("PASS test_stored_match_score_roundtrips")


def test_bound_score_still_derives_from_job_scores():
    p = _fresh()
    db.upsert_job({"id": "j1", "title": "BA", "company": "CMHC",
                   "description": "d"}, path=p)
    rid = db.save_resume("r.docx", {"raw_text": "x"}, b"x", set_current=True, path=p)
    rh = db.get_current_resume(path=p)["text_hash"]
    db.save_scores(rid, [{"job_id": "j1", "score": 61, "verdict": "fair",
                          "reasoning": "r", "matched": [], "gaps": [], "model": "m"}],
                   "en", "pv", "sv", path=p)
    sid = db.create_prep_session(rh, "CMHC", "BA", "", "en", "from_job", job_id="j1", path=p)
    row = next(r for r in db.list_prep_sessions(rh, path=p) if r["id"] == sid)
    _assert(row["match_score"] == 61, f"bound session derives score, got {row['match_score']}")
    print("PASS test_bound_score_still_derives_from_job_scores")


class _Client:
    def all_models_exhausted(self):
        return False


def _patch(monkey: dict):
    saved = {k: getattr(prep, k) for k in monkey}
    for k, v in monkey.items():
        setattr(prep, k, v)
    return saved


def _restore(saved: dict):
    for k, v in saved.items():
        setattr(prep, k, v)


def test_import_url_scrapes_and_scores():
    job = {"id": "x", "title": "VP Services", "company": "March Networks",
           "description": "Lead the services org."}
    saved = _patch({
        "job_from_url": lambda url, client: job,
        "score_single_no_cache": lambda *a, **k: ScoreResult(
            job_id="x", score=42, verdict="fair", reasoning="r",
            matched=[], gaps=[], model="m"),
    })
    try:
        out, err = prep._import_and_score(
            "https://x.example/job", "", "my resume", 1, _Client(), "en")
    finally:
        _restore(saved)
    _assert(err is None, f"URL import should succeed, err={err}")
    _assert(out["company"] == "March Networks", "company passed through")
    _assert(out["_score"] == 42, f"score attached, got {out.get('_score')}")
    print("PASS test_import_url_scrapes_and_scores")


def test_import_paste_uses_extractor():
    calls = {"url": 0, "text": 0}

    def fake_from_url(url, client):
        calls["url"] += 1
        return {}

    def fake_from_text(text, source_url, client):
        calls["text"] += 1
        return {"title": "Analyst", "company": "Kanak", "description": text}

    saved = _patch({
        "job_from_url": fake_from_url,
        "extract_job_from_text": fake_from_text,
        "score_single_no_cache": lambda *a, **k: None,
    })
    try:
        out, err = prep._import_and_score(
            "", "Pasted JD body", "resume", 1, _Client(), "en")
    finally:
        _restore(saved)
    _assert(err is None and out["company"] == "Kanak", "paste path extracts a job")
    _assert(calls["text"] == 1 and calls["url"] == 0, "paste must use the text extractor, not URL")
    _assert(out["_score"] is None, "score None when the model declines — still honest")
    print("PASS test_import_paste_uses_extractor")


def test_import_failure_is_honest():
    def boom(text, source_url, client):
        raise UrlExtractError("not a job posting")

    saved = _patch({"extract_job_from_text": boom})
    try:
        out, err = prep._import_and_score("", "garbage", "resume", 1, _Client(), "en")
    finally:
        _restore(saved)
    _assert(out is None, "no job on failure — never fabricate")
    # directionally-correct copy: the paste box is ABOVE the error (not "below")
    _assert(err and "box above" in err, f"honest message surfaced, got {err!r}")
    print("PASS test_import_failure_is_honest")


def test_linkedin_url_gets_share_link_tip():
    def boom(url, client):
        raise UrlExtractError("nope")

    saved = _patch({"job_from_url": boom})
    try:
        _out, err = prep._import_and_score(
            "https://www.linkedin.com/jobs/search?keywords=analyst",
            "", "resume", 1, _Client(), "en")
    finally:
        _restore(saved)
    _assert("Share" in err and "Copy link" in err,
            f"LinkedIn failure should tip Share→Copy link, got {err!r}")
    print("PASS test_linkedin_url_gets_share_link_tip")


def test_parse_score_never_crashes():
    # /code-review LL-1: the old isdigit guard let "--5" through and crashed int()
    _assert(prep._parse_score("73") == 73, "plain int parses")
    _assert(prep._parse_score("--5") is None, "'--5' → None, not a crash")
    _assert(prep._parse_score("72.5") is None, "float string → None")
    _assert(prep._parse_score("") is None and prep._parse_score("  ") is None, "blank → None")
    _assert(prep._parse_score("-5") == -5, "signed int still parses")
    print("PASS test_parse_score_never_crashes")


def test_sanitize_brief_tolerates_non_dict():
    # /code-review LL-2: a stored "null" json.loads to None; must not AttributeError
    for bad in (None, [], "str", 5):
        out = fit.sanitize_brief(bad)
        _assert(out == {"reasoning": "", "matched": [], "gaps": []},
                f"non-dict {bad!r} → empty brief, got {out}")
    print("PASS test_sanitize_brief_tolerates_non_dict")


def test_safe_url_blocks_dangerous_schemes():
    # /code-review RB-3: javascript:/data: URLs must not survive into an href
    from ui_web.deps import safe_url
    _assert(safe_url("https://a.example/x") == "https://a.example/x", "https allowed")
    _assert(safe_url("http://a.example") == "http://a.example", "http allowed")
    _assert(safe_url("javascript:alert(1)") == "", "javascript: blocked")
    _assert(safe_url("data:text/html,<script>") == "", "data: blocked")
    _assert(safe_url("  JavaScript:alert(1)") == "", "case/space-obfuscated blocked")
    _assert(safe_url(None) == "" and safe_url("") == "", "empty → empty")
    print("PASS test_safe_url_blocks_dangerous_schemes")


def test_band_thresholds():
    _assert(fit.band_from_score(88) == "strong", "88 → strong")
    _assert(fit.band_from_score(60) == "solid", "60 → solid")
    _assert(fit.band_from_score(42) == "stretch", "42 → stretch")
    _assert(fit.band_from_score(None) is None, "None → no band")
    print("PASS test_band_thresholds")


def test_brief_imported_roundtrips():
    p = _fresh()
    brief = json.dumps({"reasoning": "Strong data match; light on cloud.",
                        "matched": ["ATIP automation", "Governance"],
                        "gaps": ["Cloud architecture"]})
    sid = db.create_prep_session("h9", "Kanak", "GTM", "jd", "en", "pasted_text",
                                 match_score=42, match_brief=brief, path=p)
    session = db.get_prep_session(sid, path=p)
    out = fit.brief_for_session(session, path=p)
    _assert(out is not None and out["band"] == "stretch", "stretch band from 42")
    _assert(out["reasoning"].startswith("Strong data match"), "narrative carried")
    _assert(out["matched"] == ["ATIP automation", "Governance"], "strengths carried")
    _assert(out["gaps"] == ["Cloud architecture"], "gaps carried")
    print("PASS test_brief_imported_roundtrips")


def test_brief_caps_prevent_bloat():
    p = _fresh()
    long_item = "x" * 300
    brief = json.dumps({"reasoning": "y" * 500,
                        "matched": [long_item, long_item, long_item, long_item, long_item],
                        "gaps": [long_item, long_item, long_item, long_item]})
    sid = db.create_prep_session("hb", "Co", "Role", "jd", "en", "pasted_text",
                                 match_score=60, match_brief=brief, path=p)
    out = fit.brief_for_session(db.get_prep_session(sid, path=p), path=p)
    _assert(len(out["matched"]) <= fit.MAX_ITEMS and len(out["gaps"]) <= fit.MAX_ITEMS,
            f"lists capped to {fit.MAX_ITEMS}, got {len(out['matched'])}/{len(out['gaps'])}")
    _assert(all(len(m) <= fit.MAX_ITEM_CHARS for m in out["matched"]),
            "each item capped in length")
    _assert(len(out["reasoning"]) <= fit.MAX_REASONING_CHARS, "narrative capped")
    print("PASS test_brief_caps_prevent_bloat")


def test_brief_bound_derives_from_job_scores():
    p = _fresh()
    db.upsert_job({"id": "jb", "title": "BA", "company": "CMHC", "description": "d"}, path=p)
    rid = db.save_resume("r.docx", {"raw_text": "x"}, b"x", set_current=True, path=p)
    rh = db.get_current_resume(path=p)["text_hash"]
    db.save_scores(rid, [{"job_id": "jb", "score": 80, "verdict": "strong",
                          "reasoning": "Great overlap.", "matched": ["SQL", "Python"],
                          "gaps": ["Leadership"], "model": "m"}],
                   "en", "pv", "sv", path=p)
    sid = db.create_prep_session(rh, "CMHC", "BA", "", "en", "from_job", job_id="jb", path=p)
    out = fit.brief_for_session(db.get_prep_session(sid, path=p), path=p)
    _assert(out and out["band"] == "strong", "bound derives strong band from job_scores")
    _assert(out["matched"] == ["SQL", "Python"] and out["gaps"] == ["Leadership"],
            "bound strengths/gaps come from the cached score")
    print("PASS test_brief_bound_derives_from_job_scores")


if __name__ == "__main__":
    test_stored_match_score_roundtrips()
    test_bound_score_still_derives_from_job_scores()
    test_import_url_scrapes_and_scores()
    test_import_paste_uses_extractor()
    test_import_failure_is_honest()
    test_linkedin_url_gets_share_link_tip()
    test_parse_score_never_crashes()
    test_sanitize_brief_tolerates_non_dict()
    test_safe_url_blocks_dangerous_schemes()
    test_band_thresholds()
    test_brief_imported_roundtrips()
    test_brief_caps_prevent_bloat()
    test_brief_bound_derives_from_job_scores()
    print("all prep-import tests passed")
