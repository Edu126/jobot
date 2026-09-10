"""Gap map (REQ-019 base + REQ-020 / ADR-022 / ADR-023 / ADR-024): cross-job
aggregation, JD-free classification, semantic clustering into a 3-pillar panel,
and the ✕-dismiss override. Locks down that the map (1) counts a gap across the
résumé's scored jobs case-insensitively, (2) shows only REAL gaps bucketed into
pillars and ranked by count (wording stays per-job), (3) merges variant phrasings
that share a canonical label into one cluster, (4) still surfaces gaps it
couldn't classify honestly rather than dropping them, and (5) drops a cluster the
user dismissed. No network — build_gap_map runs with client=None (cache only).

Runs without pytest:
    .venv/bin/python tests/test_gap_map.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.matching import gap_map as gm  # noqa: E402
from core.matching import semantic_score as ss  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _flat(pillars: dict) -> list:
    return [c for p in gm.PILLARS for c in pillars[p]]


class _EnvDB:
    """Redirect db.tx/db.connect at a temp DB for the duration of a test."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self):
        self._tx, self._connect = db.tx, db.connect
        db.tx = lambda *a, **k: self._tx(self.path)
        db.connect = lambda *a, **k: self._connect(self.path)
        return self

    def __exit__(self, *exc) -> None:
        db.tx, db.connect = self._tx, self._connect


def test_parse_jdfree() -> None:
    raw = {"classifications": [
        {"gap": "AutoCAD", "kind": "wording", "suggestion": "You list Autodesk suite.",
         "category": "technical", "canonical": "AutoCAD"},
        {"gap": "PMP", "kind": "bogus", "suggestion": "x", "category": "nonsense", "canonical": "PMP cert"},
    ]}
    out = gm._parse_response(raw, ["AutoCAD", "PMP", "Dropped"])
    _assert(out["AutoCAD"]["kind"] == "wording" and out["AutoCAD"]["category"] == "technical", "wording parsed")
    _assert(out["PMP"]["kind"] == "real", "bad kind → real")
    _assert(out["PMP"]["category"] == gm.DEFAULT_PILLAR, "bad category → default pillar")
    _assert(out["PMP"]["canonical"] == "PMP cert", "canonical parsed")
    _assert("Dropped" not in out, "a gap the model omitted is left out (caller keeps it real)")


def test_build_map_ranks_real_only_bucketed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        with _EnvDB(db_path):
            rid = db.save_resume("cv.pdf", {"raw_text": "Autodesk suite; team delivery lead"}, b"x")
            for jid in ("j1", "j2"):
                db.upsert_job({"id": jid, "title": "T", "company": "C", "description": "d"})
            lang = "en"
            db.save_scores(rid, [
                {"job_id": "j1", "score": 80, "verdict": "stretch", "reasoning": "r",
                 "matched": [], "gaps": ["PMP certification", "AutoCAD"], "model": "m"},
                {"job_id": "j2", "score": 80, "verdict": "stretch", "reasoning": "r",
                 "matched": [], "gaps": ["PMP certification", "Six Sigma"], "model": "m"},
            ], lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)

            counts = db.gap_counts_for_resume(rid, lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)
            _assert(counts.get("PMP certification") == 2, f"PMP count 2, got {counts}")

            db.save_gap_classifications(rid, lang, gm.PROMPT_VERSION, [
                {"gap": "PMP certification", "kind": "real", "suggestion": "Lead with delivery ownership.",
                 "category": "certifications", "canonical": "PMP"},
                {"gap": "AutoCAD", "kind": "wording", "suggestion": "Name it explicitly.",
                 "category": "technical", "canonical": "AutoCAD"},
                {"gap": "Six Sigma", "kind": "real", "suggestion": "Frame your process-improvement work.",
                 "category": "domain", "canonical": "Six Sigma"},
            ])

            pillars = gm.build_gap_map(rid, "Autodesk suite; team delivery lead", None, lang=lang)
            canon = [c.canonical for c in _flat(pillars)]
            _assert("AutoCAD" not in canon, "wording gap must NOT appear in the map (stays per-job)")
            _assert([c.canonical for c in pillars["certifications"]] == ["PMP"], "PMP in certifications pillar")
            _assert([c.canonical for c in pillars["domain"]] == ["Six Sigma"], "Six Sigma in domain pillar")
            _assert(pillars["technical"] == [], "technical pillar empty")
            top = pillars["certifications"][0]
            _assert(top.count == 2 and top.suggestion.startswith("Lead"), "cluster carries count + defense hook")


def test_clustering_merges_variants() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        with _EnvDB(db_path):
            rid = db.save_resume("cv.pdf", {"raw_text": "spanish only"}, b"x")
            for jid in ("j1", "j2", "j3"):
                db.upsert_job({"id": jid, "title": "T", "company": "C", "description": "d"})
            lang = "en"
            db.save_scores(rid, [
                {"job_id": "j1", "score": 80, "verdict": "s", "reasoning": "r",
                 "matched": [], "gaps": ["Fluent French"], "model": "m"},
                {"job_id": "j2", "score": 80, "verdict": "s", "reasoning": "r",
                 "matched": [], "gaps": ["Bilingual French (CBC)"], "model": "m"},
                {"job_id": "j3", "score": 80, "verdict": "s", "reasoning": "r",
                 "matched": [], "gaps": ["Fluent French"], "model": "m"},
            ], lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)

            db.save_gap_classifications(rid, lang, gm.PROMPT_VERSION, [
                {"gap": "Fluent French", "kind": "real", "suggestion": "Frame your language exposure.",
                 "category": "certifications", "canonical": "French proficiency"},
                {"gap": "Bilingual French (CBC)", "kind": "real", "suggestion": "Frame your language exposure.",
                 "category": "certifications", "canonical": "French proficiency"},
            ])

            pillars = gm.build_gap_map(rid, "spanish only", None, lang=lang)
            certs = pillars["certifications"]
            _assert(len(certs) == 1, f"two variants collapse into one cluster, got {len(certs)}")
            cl = certs[0]
            _assert(cl.canonical == "French proficiency", "cluster shows the canonical label")
            _assert(cl.count == 3, f"cluster count sums variants (2+1), got {cl.count}")
            _assert(set(cl.members) == {"Fluent French", "Bilingual French (CBC)"}, "members list both variants")


def test_dismiss_filters_cluster() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        with _EnvDB(db_path):
            rid = db.save_resume("cv.pdf", {"raw_text": "spanish only"}, b"x")
            db.upsert_job({"id": "j1", "title": "T", "company": "C", "description": "d"})
            lang = "en"
            db.save_scores(rid, [
                {"job_id": "j1", "score": 80, "verdict": "s", "reasoning": "r",
                 "matched": [], "gaps": ["Fluent French"], "model": "m"},
            ], lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)
            db.save_gap_classifications(rid, lang, gm.PROMPT_VERSION, [
                {"gap": "Fluent French", "kind": "real", "suggestion": "s",
                 "category": "certifications", "canonical": "French proficiency"},
            ])

            _assert(len(_flat(gm.build_gap_map(rid, "spanish only", None, lang=lang))) == 1, "shown before dismiss")
            # Dismiss with different casing than the canonical → must still match (ADR-024).
            ok = db.dismiss_gap_cluster(rid, lang, "FRENCH proficiency")
            _assert(ok, "dismiss persisted")
            _assert(_flat(gm.build_gap_map(rid, "spanish only", None, lang=lang)) == [], "dismissed cluster is gone")
            # Stored lower-cased so a re-cased canonical still matches (ADR-024).
            _assert("french proficiency" in db.get_gap_dismissals(rid, lang), "dismissal readable (lower-cased)")

            # Restore (REQ-021 Undo) — reversible, casing-insensitive, cluster
            # comes back on the next build.
            _assert(db.undismiss_gap_cluster(rid, lang, "French Proficiency"), "undismiss persisted")
            _assert("french proficiency" not in db.get_gap_dismissals(rid, lang), "dismissal cleared")
            _assert(len(_flat(gm.build_gap_map(rid, "spanish only", None, lang=lang))) == 1, "cluster restored")


def test_build_map_keeps_unclassified_as_real() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        with _EnvDB(db_path):
            rid = db.save_resume("cv.pdf", {"raw_text": "some text"}, b"x")
            db.upsert_job({"id": "j1", "title": "T", "company": "C", "description": "d"})
            db.save_scores(rid, [
                {"job_id": "j1", "score": 80, "verdict": "stretch", "reasoning": "r",
                 "matched": [], "gaps": ["Kubernetes"], "model": "m"},
            ], "en", ss.PROMPT_VERSION, ss.SCORING_VERSION)
            # No classification seeded, client=None → can't classify. Must still
            # surface the gap honestly (real, own cluster, default pillar, no hook).
            pillars = gm.build_gap_map(rid, "some text", None, lang="en")
            flat = _flat(pillars)
            _assert(len(flat) == 1 and flat[0].canonical == "Kubernetes", "unclassified gap still shown")
            _assert(flat[0].category == gm.DEFAULT_PILLAR and flat[0].suggestion == "",
                    "unclassified → default pillar, no invented suggestion")


def test_recent_highfit_filter() -> None:
    """REQ-036 / ADR-040: only jobs scored within 60 days AND with score > 70
    feed the aggregation. A low-fit job and a stale high-fit job are both
    excluded — a hard filter, no fallback, so the gap signal stays in-lane and
    current."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        with _EnvDB(db_path):
            rid = db.save_resume("cv.pdf", {"raw_text": "text"}, b"x")
            lang = "en"
            for jid in ("jGood", "jLow", "jStale"):
                db.upsert_job({"id": jid, "title": f"Role {jid}", "company": "Co", "description": "d"})
            db.save_scores(rid, [
                {"job_id": "jGood", "score": 85, "verdict": "s", "reasoning": "r",
                 "matched": [], "gaps": ["Kubernetes"], "model": "m"},
                {"job_id": "jLow", "score": 55, "verdict": "s", "reasoning": "r",
                 "matched": [], "gaps": ["Data architecture"], "model": "m"},   # out-of-lane noise
                {"job_id": "jStale", "score": 90, "verdict": "s", "reasoning": "r",
                 "matched": [], "gaps": ["Terraform"], "model": "m"},
            ], lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)
            # Age jStale past the 60-day window (scored_at is ISO8601-UTC).
            with db.connect(db_path) as conn:
                conn.execute(
                    "UPDATE job_scores SET scored_at = '2000-01-01T00:00:00Z' WHERE job_id = 'jStale'"
                )
                conn.commit()

            counts = db.gap_counts_for_resume(
                rid, lang, ss.PROMPT_VERSION, ss.SCORING_VERSION,
                min_score=gm.GAP_MAP_MIN_SCORE, since=gm._recency_cutoff(),
            )
            _assert(set(counts) == {"Kubernetes"},
                    f"only the recent high-fit gap survives, got {counts}")
            ranked = [j["job_id"] for j in gm.scored_jobs(rid, lang)]
            _assert(ranked == ["jGood"], f"low-fit + stale jobs excluded from ranking, got {ranked}")


def test_build_map_excludes_subfloor_jobs() -> None:
    """REQ-036 / ADR-040: build_gap_map is a single recent/high-fit view — a
    sub-70 job's gaps never reach the map, and counts sum only over the >70 jobs."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        with _EnvDB(db_path):
            rid = db.save_resume("cv.pdf", {"raw_text": "text"}, b"x")
            lang = "en"
            spec = [("jA", 90, ["Kubernetes"]),
                    ("jB", 80, ["Kubernetes", "Terraform"]),
                    ("jC", 75, ["PMP"]),
                    ("jD", 60, ["Docker"])]   # sub-floor → excluded
            for jid, _s, _g in spec:
                db.upsert_job({"id": jid, "title": f"Role {jid}", "company": "Co", "description": "d"})
            db.save_scores(rid, [
                {"job_id": jid, "score": s, "verdict": "stretch", "reasoning": "r",
                 "matched": [], "gaps": g, "model": "m"}
                for jid, s, g in spec
            ], lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)
            db.save_gap_classifications(rid, lang, gm.PROMPT_VERSION, [
                {"gap": "Kubernetes", "kind": "real", "category": "technical", "canonical": "Kubernetes", "suggestion": "s"},
                {"gap": "Terraform", "kind": "real", "category": "technical", "canonical": "Terraform", "suggestion": "s"},
                {"gap": "PMP", "kind": "real", "category": "certifications", "canonical": "PMP", "suggestion": "s"},
                {"gap": "Docker", "kind": "real", "category": "technical", "canonical": "Docker", "suggestion": "s"},
            ])

            ranked = [j["job_id"] for j in gm.scored_jobs(rid, lang)]
            _assert(ranked == ["jA", "jB", "jC"], f"ranking excludes the sub-70 job, got {ranked}")

            pillars = gm.build_gap_map(rid, "text", None, lang=lang)
            canon = {c.canonical for p in gm.PILLARS for c in pillars[p]}
            _assert(canon == {"Kubernetes", "Terraform", "PMP"}, f"Docker (jD=60) filtered, got {canon}")
            k = [c for c in pillars["technical"] if c.canonical == "Kubernetes"][0]
            _assert(k.count == 2, f"Kubernetes counted in jA+jB only, got {k.count}")


def test_classify_drains_full_filtered_set() -> None:
    """REQ-036: build_gap_map classifies the WHOLE recency/fit-filtered gap set in
    up to MAX_CLASSIFY_CHUNKS batches — not just the first 40 — so no gap is left
    unclassified and dumped into the domain pillar (the Mehran -hermana bug)."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "t.db"
        db.init_db(db_path)
        with _EnvDB(db_path):
            rid = db.save_resume("cv.pdf", {"raw_text": "text"}, b"x")
            lang = "en"
            db.upsert_job({"id": "j1", "title": "T", "company": "C", "description": "d"})
            gaps = [f"gap {i}" for i in range(90)]   # > 2×MAX_GAPS_PER_CALL
            db.save_scores(rid, [
                {"job_id": "j1", "score": 85, "verdict": "s", "reasoning": "r",
                 "matched": [], "gaps": gaps, "model": "m"},
            ], lang, ss.PROMPT_VERSION, ss.SCORING_VERSION)

            calls: list[int] = []

            def fake_classify(resume_text, batch, client, *, lang, persona, anchors):
                calls.append(len(batch))
                return {g: {"kind": "real", "suggestion": "s",
                            "category": "technical", "canonical": g} for g in batch}

            class _Client:
                def all_models_exhausted(self):
                    return False

            orig_c, orig_p = gm._classify, gm.ai_summary.persona_line
            gm._classify = fake_classify
            gm.ai_summary.persona_line = lambda _rid: ""
            try:
                gm.build_gap_map(rid, "text", _Client(), lang=lang)
            finally:
                gm._classify, gm.ai_summary.persona_line = orig_c, orig_p

            cached = db.get_gap_classifications(rid, gaps, lang, gm.PROMPT_VERSION)
            _assert(len(cached) == 90, f"all 90 gaps classified, got {len(cached)}")
            _assert(calls == [40, 40, 10], f"drained in bounded batches, got {calls}")


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("OK — gap_map aggregation + clustering + pillars + dismiss verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
