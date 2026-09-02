"""Seed / restore fixture data on the jobbotv2-edu Fly machine so a feature can
be smoke-tested against a REAL deploy without an API key and without clobbering
the user's own -edu data.

Runs ON THE MACHINE (transferred there at smoke time — NOT baked into the image,
per .dockerignore's smoke_*.py exclusion). Uses the deployed app's own core.db +
gap_map so versions always match. Invoke over SSH:

    fly ssh console -a jobbotv2-edu -C "python3 /tmp/smoke_edu.py seed"
    fly ssh console -a jobbotv2-edu -C "python3 /tmp/smoke_edu.py status"
    fly ssh console -a jobbotv2-edu -C "python3 /tmp/smoke_edu.py restore"

Contract:
- seed:    remembers the current résumé id in a marker on the volume, inserts a
           fixture résumé (marked by SMOKE_FILENAME) + jobs + scores + gap
           classifications, sets the fixture current. Idempotent (cleans a prior
           smoke fixture first).
- restore: sets the remembered résumé current again, deletes every smoke row
           (résumé, its scores, its gap caches keyed on resume_hash, smoke jobs),
           removes the marker. Leaves -edu exactly as found.
- status:  prints the current résumé + the gap-map pillars (no writes).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/app")   # the deployed app root on the Fly machine

from core import db  # noqa: E402
from core.matching import gap_map as gm  # noqa: E402
from core.matching import semantic_score as ss  # noqa: E402

SMOKE_FILENAME = "__SMOKE_gapmap__.docx"
SMOKE_JOB_IDS = [f"__smoke_j{i}__" for i in range(1, 6)]
MARKER = db.DB_PATH.parent / ".smoke_marker"
LANG = "en"

# A minimal-but-valid parsed dict — run_checks / anomalies.analyze read every key
# with .get(), so this won't crash /profile; sections populate tab 2.
PARSED = {
    "raw_text": (
        "Carlos Mendez — Senior Project Manager. 6 years delivering regulated "
        "fintech programs. Docker + CI/CD, CloudFormation IaC, scrum-of-scrums "
        "across two teams. Conversational French."
    ),
    "source_format": "docx",
    "contact": {"name": "Carlos Mendez", "email": "carlos@example.com",
                "phone": "613-555-0100", "location": "Ottawa, ON", "linkedin": ""},
    "stats": {"word_count": 320, "page_estimate": 1, "bullet_count": 12},
    "sections": {
        "summary": "Senior PM, regulated fintech, delivery ownership.",
        "experience": "Program Lead — 6 yrs. Docker/CI-CD. Scrum-of-scrums.",
        "skills": "Docker, CloudFormation, Agile, French (conversational)",
        "education": "BSc",
    },
}

# gaps per fixture job → drives the counts (case-insensitive distinct strings).
JOB_GAPS = {
    SMOKE_JOB_IDS[0]: ["Kubernetes", "Fluent French", "PMP certification", "10 years healthcare experience"],
    SMOKE_JOB_IDS[1]: ["Kubernetes", "Bilingual French (CBC)", "Terraform", "Agile at scale"],
    SMOKE_JOB_IDS[2]: ["Kubernetes", "Fluent French", "PMP certification", "10 years healthcare experience"],
    SMOKE_JOB_IDS[3]: ["Terraform"],
    SMOKE_JOB_IDS[4]: [],
}

# JD-free classifications (real + category + canonical) — two French variants
# share a canonical so the map shows a 2-member cluster.
CLASSIFICATIONS = [
    {"gap": "Kubernetes", "kind": "real", "category": "technical", "canonical": "Kubernetes",
     "suggestion": "Lead with your Docker and CI/CD containerization work."},
    {"gap": "Terraform", "kind": "real", "category": "technical", "canonical": "Terraform",
     "suggestion": "Point to your CloudFormation infra-as-code exposure."},
    {"gap": "Fluent French", "kind": "real", "category": "certifications", "canonical": "French proficiency",
     "suggestion": "Frame your conversational French and willingness to certify."},
    {"gap": "Bilingual French (CBC)", "kind": "real", "category": "certifications", "canonical": "French proficiency",
     "suggestion": "Frame your conversational French and willingness to certify."},
    {"gap": "PMP certification", "kind": "real", "category": "certifications", "canonical": "PMP",
     "suggestion": "Lead with 6 years of delivery ownership; PMP in progress."},
    {"gap": "10 years healthcare experience", "kind": "real", "category": "domain", "canonical": "Healthcare domain",
     "suggestion": "Bridge from 4 years in regulated fintech — same compliance rigor."},
    {"gap": "Agile at scale", "kind": "real", "category": "domain", "canonical": "Agile at scale",
     "suggestion": "Cite your two-team scrum-of-scrums coordination."},
]


def _resume_id_by_filename(name: str) -> int | None:
    for r in db.list_resumes():
        if r["filename"] == name:
            return int(r["id"])
    return None


def _purge_smoke_rows() -> None:
    """Remove any existing smoke fixture (résumé + hash-keyed caches + jobs)."""
    rid = _resume_id_by_filename(SMOKE_FILENAME)
    with db.tx() as conn:
        if rid is not None:
            row = conn.execute("SELECT text_hash FROM resumes WHERE id = ?", (rid,)).fetchone()
            h = row["text_hash"] if row else ""
            conn.execute("DELETE FROM resumes WHERE id = ?", (rid,))  # cascades job_scores
            if h:
                conn.execute("DELETE FROM gap_classification WHERE resume_hash = ?", (h,))
                conn.execute("DELETE FROM gap_dismissals WHERE resume_hash = ?", (h,))
        conn.executemany("DELETE FROM jobs WHERE id = ?", [(j,) for j in SMOKE_JOB_IDS])


def seed() -> None:
    current = db.get_current_resume()
    MARKER.write_text(str(current["id"]) if current else "")
    _purge_smoke_rows()

    rid = db.save_resume(SMOKE_FILENAME, PARSED, b"smoke", set_current=True)
    for jid in SMOKE_JOB_IDS:
        db.upsert_job({"id": jid, "title": "Senior PM", "company": "SmokeCo", "description": "d"})
    db.save_scores(rid, [
        {"job_id": jid, "score": 55, "verdict": "stretch", "reasoning": "r",
         "matched": [], "gaps": g, "model": "seed"}
        for jid, g in JOB_GAPS.items()
    ], LANG, ss.PROMPT_VERSION, ss.SCORING_VERSION)
    db.save_gap_classifications(rid, LANG, gm.PROMPT_VERSION, CLASSIFICATIONS)

    print(f"SEEDED résumé_id={rid}, prev_current={MARKER.read_text() or 'none'}")
    _print_pillars(rid)


def restore() -> None:
    prev = MARKER.read_text().strip() if MARKER.exists() else ""
    _purge_smoke_rows()
    if prev:
        try:
            db.set_current_resume(int(prev))
            print(f"RESTORED current résumé → {prev}")
        except Exception as e:  # noqa: BLE001
            print(f"WARN could not restore current={prev}: {e}")
    else:
        print("RESTORED (no prior current résumé to reset)")
    if MARKER.exists():
        MARKER.unlink()


def status() -> None:
    current = db.get_current_resume()
    print(f"current résumé: {current['filename'] if current else 'none'} (id={current['id'] if current else '-'})")
    if current:
        _print_pillars(int(current["id"]))


def _print_pillars(rid: int) -> None:
    pillars = gm.build_gap_map(rid, PARSED["raw_text"], None, lang=LANG)
    for p in gm.PILLARS:
        cells = ", ".join(f"{c.canonical}(x{c.count},{len(c.members)}m)" for c in pillars[p])
        print(f"  {p}: {cells or '—'}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"seed": seed, "restore": restore, "status": status}.get(cmd, status)()
