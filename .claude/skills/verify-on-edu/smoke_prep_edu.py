"""Seed / restore a PREP (REQ-023) fixture on jobbotv2-edu so the Prep tab can
be smoked against a real deploy WITHOUT an API key and without clobbering the
user's -edu data.

Runs ON THE MACHINE (transferred at smoke time). Uses the deployed app's own
core.db + core.prep so versions/keys match. The trick for no-API-key rendering:
we pre-seed `company_outlook` and `prep_kits` rows under the CURRENT
PROMPT_VERSIONs, so the detail view's lazy fragments hit cache and never call
Gemini. A tailored+scored job is seeded so the entry-form matching path proposes
it (the confirm chips), and a BOUND prep_session is seeded so /prep/<id> renders
the full outlook + kit.

    fly ssh console -a jobbotv2-edu -C "python3 /tmp/smoke_prep_edu.py seed"
    fly ssh console -a jobbotv2-edu -C "python3 /tmp/smoke_prep_edu.py status"
    fly ssh console -a jobbotv2-edu -C "python3 /tmp/smoke_prep_edu.py restore"
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from core import db  # noqa: E402
from core.matching import semantic_score as ss  # noqa: E402
from core.prep import company_outlook as co  # noqa: E402
from core.prep import kit as prep_kit  # noqa: E402
from core.prep import matching  # noqa: E402

SMOKE_FILENAME = "__SMOKE_prep__.docx"
SMOKE_JOB_ID = "__smoke_prep_j1__"
COMPANY = "CMHC"
ROLE = "Senior Business Analyst"
# 2nd session: a company we have NO outlook for → exercises the honest
# "couldn't find it, here's general prep" fallback (empty cached outlook, so
# no LLM call on -edu).
COMPANY2 = "Zorptech Dynamics"
ROLE2 = "Widget Analyst"
# 3rd session: a REAL, well-known company with NO cached outlook → forces the
# live Tavily→Gemini path (the whole point of this verify). Kit is pre-cached so
# only the outlook fragment exercises the network. A fallback here = real
# failure, since Tavily will certainly have info on this company.
COMPANY3 = "Shopify"
ROLE3 = "Senior Business Analyst"
LANG = "en"
MARKER = db.DB_PATH.parent / ".smoke_prep_marker"

PARSED = {
    "raw_text": (
        "Carlos Mendez — Senior Business Analyst. 6 years in regulated fintech "
        "and public-sector data. Built a Python/SQL pipeline that cut an ATIP "
        "reporting backlog and saved 200+ hours. Governance-first; scrum-of-"
        "scrums across two teams. Conversational French."
    ),
    "source_format": "docx",
    "contact": {"name": "Carlos Mendez", "email": "carlos@example.com",
                "phone": "613-555-0100", "location": "Ottawa, ON", "linkedin": ""},
    "stats": {"word_count": 300, "page_estimate": 1, "bullet_count": 10},
    "sections": {"summary": "Senior BA, public-sector data.",
                 "experience": "Built Python/SQL ATIP pipeline; saved 200+ hrs.",
                 "skills": "Python, SQL, governance, French (conversational)",
                 "education": "BSc"},
}

JD_TEXT = ("Analyze housing affordability data pipelines. Python, SQL, data "
           "governance. Public agency, compliance-heavy environment.")

OUTLOOK = {
    "culture_tone": "**Public agency**, risk-averse, **compliance- and data-heavy**.",
    "strategic_focus": "**Housing affordability** technology and **cloud data pipelines**.",
    "recent_news": [
        {"headline": "Launched AI Housing Assist", "date": "Jul 2026",
         "url": "https://example.com/cmhc/ai-housing-assist"},
    ],
}
OUTLOOK_SOURCES = ["https://example.com/cmhc/ai-housing-assist"]

KIT = {
    "star_qa": [
        {"kind": "behavioral",
         "question": "Tell me about a complex data process you automated.",
         "star": {"situation": "An ATIP reporting backlog was blowing turnaround SLAs.",
                  "task": "Cut turnaround while keeping 100% compliance.",
                  "action": "Built a Python/SQL pipeline replacing manual steps.",
                  "result": "Saved 200+ hours and held full compliance."}},
        {"kind": "why_you",
         "question": "Why are you a fit for this role?",
         "talking_points": ["6 years in regulated, public-sector data",
                            "Governance-first mindset the agency rewards",
                            "Proven automation impact (200+ hrs saved)"]},
        {"kind": "defensive_gap",
         "question": "How do you handle enterprise architecture gaps?",
         "talking_points": ["Lead with hands-on data-platform and pipeline work",
                            "Name the gap plainly; show fast ramp on adjacent tooling"]},
    ],
    "reverse_qs": [
        {"category": "Culture & Team", "question": "How does the team balance delivery speed with governance?"},
        {"category": "Role Success (90-Day Goals)", "question": "What does success look like in the first 90 days?"},
        {"category": "Tech & Data", "question": "What is the current maturity of your data stack?"},
    ],
}


def _resume_id_by_filename(name: str):
    for r in db.list_resumes():
        if r["filename"] == name:
            return int(r["id"])
    return None


def _purge() -> None:
    """Remove any prior prep smoke fixture: résumé (cascades job_scores),
    hash-keyed nothing here, the smoke job + its tailor runs, the smoke prep
    sessions (cascades prep_kits) + the seeded company_outlook row."""
    norms = (matching.normalize_company(COMPANY), matching.normalize_company(COMPANY2),
             matching.normalize_company(COMPANY3))
    rid = _resume_id_by_filename(SMOKE_FILENAME)
    with db.tx() as conn:
        if rid is not None:
            row = conn.execute("SELECT text_hash FROM resumes WHERE id=?", (rid,)).fetchone()
            h = row["text_hash"] if row else ""
            if h:
                conn.execute("DELETE FROM prep_sessions WHERE resume_hash=?", (h,))  # cascades prep_kits
            conn.execute("DELETE FROM resumes WHERE id=?", (rid,))  # cascades job_scores
        conn.execute("DELETE FROM tailor_runs WHERE job_id=?", (SMOKE_JOB_ID,))
        conn.execute("DELETE FROM jobs WHERE id=?", (SMOKE_JOB_ID,))
        conn.executemany("DELETE FROM company_outlook WHERE company_norm=?", [(n,) for n in norms])


def seed() -> None:
    current = db.get_current_resume()
    MARKER.write_text(str(current["id"]) if current else "")
    _purge()

    rid = db.save_resume(SMOKE_FILENAME, PARSED, b"smoke", set_current=True)
    resume_hash = db.get_current_resume()["text_hash"]

    # a tailored + scored job so matching proposes it and match% shows
    db.upsert_job({"id": SMOKE_JOB_ID, "title": ROLE, "company": COMPANY,
                   "description": JD_TEXT})
    db.save_tailor_run(SMOKE_JOB_ID, "balanced", LANG, {"note": "smoke"})
    db.save_scores(rid, [{"job_id": SMOKE_JOB_ID, "score": 88, "verdict": "strong",
                          "reasoning": "Strong public-sector data + governance match; lighter on cloud architecture.",
                          "matched": ["ATIP reporting automation", "Governance-first mindset", "Python/SQL pipelines"],
                          "gaps": ["Cloud architecture depth", "Team scale leadership"],
                          "model": "seed"}],
                   LANG, ss.PROMPT_VERSION, ss.SCORING_VERSION)

    # a BOUND session + pre-cached outlook & kit (current prompt versions ⇒
    # the lazy fragments hit cache, no LLM)
    sid = db.create_prep_session(resume_hash, COMPANY, ROLE, JD_TEXT, LANG,
                                 "from_job", job_id=SMOKE_JOB_ID)
    db.save_company_outlook(matching.normalize_company(COMPANY), ROLE, LANG,
                            co.PROMPT_VERSION, OUTLOOK, OUTLOOK_SOURCES, "seed")
    db.save_prep_kit(sid, LANG, prep_kit.PROMPT_VERSION, KIT, "seed")

    # 2nd session: unbound, EMPTY cached outlook → the general-prep fallback.
    sid2 = db.create_prep_session(resume_hash, COMPANY2, ROLE2, "", LANG, "pasted_text")
    db.save_company_outlook(matching.normalize_company(COMPANY2), ROLE2, LANG,
                            co.PROMPT_VERSION,
                            {"culture_tone": "", "strategic_focus": "", "recent_news": []},
                            [], "seed")
    db.save_prep_kit(sid2, LANG, prep_kit.PROMPT_VERSION, KIT, "seed")

    # 3rd session: bound-less, kit cached, outlook NOT cached → live Tavily.
    sid3 = db.create_prep_session(resume_hash, COMPANY3, ROLE3, "", LANG, "pasted_text")
    db.save_prep_kit(sid3, LANG, prep_kit.PROMPT_VERSION, KIT, "seed")

    print(f"SEEDED résumé_id={rid} PREP_SESSION_ID={sid} FALLBACK_SESSION_ID={sid2} "
          f"LIVE_SESSION_ID={sid3} prev_current={MARKER.read_text() or 'none'}")
    _print_state(resume_hash)


def restore() -> None:
    prev = MARKER.read_text().strip() if MARKER.exists() else ""
    _purge()
    if prev:
        try:
            db.set_current_resume(int(prev))
            print(f"RESTORED current résumé → {prev}")
        except Exception as e:  # noqa: BLE001
            print(f"WARN could not restore current={prev}: {e}")
    else:
        print("RESTORED (no prior current résumé)")
    if MARKER.exists():
        MARKER.unlink()


def status() -> None:
    current = db.get_current_resume()
    print(f"current résumé: {current['filename'] if current else 'none'} "
          f"(id={current['id'] if current else '-'})")
    if current:
        _print_state(current.get("text_hash", ""))


def _print_state(resume_hash: str) -> None:
    if not resume_hash:
        return
    for s in db.list_prep_sessions(resume_hash):
        print(f"  session id={s['id']} {s['company']} / {s['role_title']} "
              f"match={s.get('match_score')} status={s['status']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"seed": seed, "restore": restore, "status": status}.get(cmd, status)()
