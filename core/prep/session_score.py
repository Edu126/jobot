"""Practice session score (ADR-059) — a 0–100 number built in CODE from
evidence-gated binary checks, never asked of the model.

Why: the old debrief asked the model for one gut-feel band per competency. With
no rubric, no evidence and no "not covered" option it rounded junk answers up
to "solid". Now the model only answers five yes/no checks per competency and
must quote the candidate's exact words; code verifies the quote against the
transcript, sums the points and derives the band. A failed quote zeroes the
competency — the model can't award credit it can't point to.

  answered     — the candidate actually answered what was asked
  example      — a specific, real situation (not a generic "I usually…")
  own_actions  — what THEY did, not "we" / the team
  result       — an outcome of those actions
  quantified   — a number in the evidence (also checked in code: needs a digit
                 or number word in the quote)
  own_actions is also checked in code: needs a first-person word in the quote.
Band: 5 strong · 4 solid · ≤3 needs_work.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Optional

CHECKS = ("answered", "example", "own_actions", "result", "quantified")
MAX_POINTS = len(CHECKS)

# Verdict thresholds on the 0–100 session score.
READY_AT = 75
CLOSE_AT = 50

# Speaking pace thresholds (words per minute) — code, not model.
SLOW_WPM = 110
FAST_WPM = 170

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)
_NUMBER_WORDS = {
    # en
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "dozen", "hundred", "hundreds", "thousand", "thousands", "million", "millions",
    "billion", "half", "double", "percent",
    # fr
    "deux", "trois", "quatre", "cinq", "sept", "huit", "neuf", "dix", "cent",
    "mille", "pourcent", "moitié",
    # es
    "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez",
    "cien", "mil", "millón", "millones", "mitad", "por", "ciento",
}
_NUMBER_WORDS -= {"por"}  # too common on its own

# own_actions needs the candidate speaking for THEMSELVES in the quote.
# (Spanish can drop the pronoun — "lideré" — a known false negative, REQ-042.)
_FIRST_PERSON = {
    "i", "i'm", "i've", "i'd", "i'll", "my", "me", "myself",   # en
    "je", "j'ai", "moi", "mon", "ma", "mes",                     # fr
    "yo", "mi", "mis", "me", "conmigo",                          # es
}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = t.replace("’", "'")
    return " ".join(_TOKEN_RE.findall(t))


def verify_quote(quote: str, transcript: str) -> bool:
    """True when `quote` is really the candidate's words: a normalized substring
    of the transcript, or (speech-to-text drift) ≥60% of its tokens present.
    Quotes under 3 words never verify — too short to be evidence."""
    q, tr = _norm(quote), _norm(transcript)
    if not q or not tr:
        return False
    q_tokens = q.split()
    if len(q_tokens) < 3:
        return False
    if q in tr:
        return True
    tr_tokens = set(tr.split())
    hits = sum(1 for tok in q_tokens if tok in tr_tokens)
    return hits / len(q_tokens) >= 0.6


def _has_number(text: str) -> bool:
    if re.search(r"\d", text or ""):
        return True
    return any(tok in _NUMBER_WORDS for tok in _norm(text).split())


def _has_first_person(text: str) -> bool:
    return any(tok in _FIRST_PERSON for tok in _norm(text).split())


def band_for(points: int) -> str:
    """5 = strong (complete STAR + a number) · 4 = solid (complete STAR, no
    number) · ≤3 = needs_work (a piece of the story is missing)."""
    if points >= MAX_POINTS:
        return "strong"
    if points >= 4:
        return "solid"
    return "needs_work"


def verdict_for(score: int) -> str:
    if score >= READY_AT:
        return "ready"
    if score >= CLOSE_AT:
        return "close"
    return "not_ready"


def pace_for(wpm: int) -> str:
    if not wpm:
        return "unknown"
    if wpm < SLOW_WPM:
        return "slow"
    if wpm > FAST_WPM:
        return "fast"
    return "on_target"


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "yes", "1")


def grade_item(item: Any, transcript: str) -> Optional[dict]:
    """Normalize ONE model evidence item → {competency_id, asked, quote,
    verified, checks, points, missing}. The gates live here:
      - quote must verify against the transcript, else every check is false;
      - `answered` false → 0 points whatever else was ticked;
      - `quantified` also needs a number in the quote itself."""
    if not isinstance(item, dict):
        return None
    cid = str(item.get("competency_id", "")).strip()
    if not cid:
        return None
    quote = str(item.get("quote") or "").strip()
    checks_in = item.get("checks") if isinstance(item.get("checks"), dict) else {}
    checks = {k: _truthy(checks_in.get(k)) for k in CHECKS}
    verified = verify_quote(quote, transcript)
    if not verified:
        checks = {k: False for k in CHECKS}
    if checks["quantified"] and not _has_number(quote):
        checks["quantified"] = False
    if checks["own_actions"] and not _has_first_person(quote):
        checks["own_actions"] = False
    if not checks["answered"]:
        checks = {k: False for k in CHECKS}
    points = sum(1 for k in CHECKS if checks[k])
    return {
        "competency_id": cid,
        "asked": _truthy(item.get("asked", True)),
        "quote": quote if verified else "",
        "verified": verified,
        "checks": checks,
        "points": points,
        "missing": str(item.get("missing") or "").strip(),
    }


def aggregate(
    graded: Iterable[Optional[dict]],
    *,
    competency_ids: list[str],
    asked_ids: Optional[set[str]] = None,
) -> Optional[dict]:
    """Roll graded items up to the session: best item per competency (a typed
    session can ask the same competency twice), `not_asked` competencies kept
    for display but out of the denominator. Returns {score, verdict_key,
    competency_evidence, competency_bands} or None when nothing was asked."""
    best: dict[str, dict] = {}
    for g in graded:
        if not g or (competency_ids and g["competency_id"] not in competency_ids):
            continue
        cur = best.get(g["competency_id"])
        if cur is None or g["points"] > cur["points"]:
            best[g["competency_id"]] = g

    asked_ids = {a for a in (asked_ids or set()) if a}
    evidence: list[dict] = []
    for cid in competency_ids or list(best):
        g = best.get(cid)
        # Asked = the session planned a question for it, or the model saw one
        # asked (the live coach can drift) AND the candidate's words back it up.
        asked = (cid in asked_ids) or bool(g and g["asked"] and g["verified"])
        if g is None:
            g = {"competency_id": cid, "asked": asked, "quote": "", "verified": False,
                 "checks": {k: False for k in CHECKS}, "points": 0, "missing": ""}
        g = {**g, "asked": asked, "band": band_for(g["points"]) if asked else "not_asked"}
        evidence.append(g)

    asked = [e for e in evidence if e["asked"]]
    if not asked:
        return None
    points = sum(e["points"] for e in asked)
    score = round(100 * points / (MAX_POINTS * len(asked)))
    verdict = verdict_for(score)
    # One weak competency is enough to fail a real interview: never call the
    # session "ready" while any asked competency is still needs_work.
    if verdict == "ready" and any(e["band"] == "needs_work" for e in asked):
        verdict = "close"
    return {
        "score": score,
        "verdict_key": verdict,
        "competency_evidence": evidence,
        # Same shape readiness reads (readiness._latest_competency_bands).
        "competency_bands": [{"competency_id": e["competency_id"], "band": e["band"]}
                             for e in asked],
    }


def delta_vs_previous(sessions: list[dict], session_id: int) -> Optional[int]:
    """Score change vs the most recent EARLIER done session that has a score.
    `sessions` is newest-first (db.list_practice_sessions)."""
    seen = False
    current = None
    for s in sessions:
        if s.get("id") == session_id:
            seen = True
            current = (s.get("debrief") or {}).get("score")
            continue
        if not seen or s.get("status") != "done":
            continue
        prev = (s.get("debrief") or {}).get("score")
        if isinstance(prev, int) and isinstance(current, int):
            return current - prev
    return None


# Shared prompt text (P8 / P9 / audio) — the rubric the model fills in.
RUBRIC_BLOCK = """Score each competency with five YES/NO checks. Be strict: when unsure, answer false.
- answered: the candidate actually answered the question that tests this competency. Rambling, "I don't know", off-topic talk, or repeating the question = false.
- example: they described ONE specific real situation (when, where, what project). Generic habits ("I usually…", "I would…") = false.
- own_actions: they said what THEY personally did ("I built…"), not only "we" or the team.
- result: they said what happened because of their actions.
- quantified: the result or situation includes a real number (money, %, time, people, volume).
For every competency also give:
- quote: the candidate's EXACT words (8–30 words) that best support your checks. Copy them, do not paraphrase. Empty string if they said nothing relevant.
- asked: true if a question in the interview tested this competency.
- missing: one short line — the single most important thing the answer lacked.
Example of a weak answer: "Um, yeah, I mean budgets are important, you just have to manage them, you know." → answered=false, example=false, own_actions=false, result=false, quantified=false."""

EVIDENCE_SCHEMA = """"competency_evidence": [{ "competency_id": "c1", "asked": true, "quote": "string", "checks": { "answered": false, "example": false, "own_actions": false, "result": false, "quantified": false }, "missing": "string" }]"""


# ---------- delivery gauges (REQ-043) ----------
# Every number is shown against a research baseline, never alone ("4 fillers"
# means nothing without the length). Zones: good | ok | warn.
#   Pace: ~150 wpm is typical US conversation (NCVS); 130–160 is easy to
#     note-take in an interview; <110 reads hesitant, >170 rushed.
#   Fillers: ~2.6 uh/um per 100 words in everyday conversation (Bortfeld et
#     al. 2001, Language & Speech, range ≈1.5–3.5); fewer reads more fluent.
#   Answer length: 1–2 min per behavioural answer (practitioner guidance,
#     not a study — labelled as such in the UI copy).

def _zone(value: float, zones: list[tuple[float, float, str]]) -> str:
    for lo, hi, kind in zones:
        if lo <= value < hi:
            return kind
    return zones[-1][2]


def _gauge(key: str, value: float, display: str, lo: float, hi: float,
           zones: list[tuple[float, float, str]], verdict: str) -> dict:
    span = (hi - lo) or 1
    pct = lambda v: round(100 * (min(max(v, lo), hi) - lo) / span, 1)  # noqa: E731
    return {
        "key": key, "value": value, "display": display, "verdict": verdict,
        "kind": _zone(value, zones), "marker_pct": pct(value),
        "zones": [{"kind": k, "left": pct(a), "width": round(pct(min(b, hi)) - pct(a), 1)}
                  for a, b, k in zones],
    }


PACE_ZONES = [(0, SLOW_WPM, "warn"), (SLOW_WPM, 130, "ok"), (130, 161, "good"),
              (161, FAST_WPM + 1, "ok"), (FAST_WPM + 1, 10_000, "warn")]
FILLER_ZONES = [(0, 2.0, "good"), (2.0, 4.0, "ok"), (4.0, 10_000, "warn")]
LENGTH_ZONES = [(0, 45, "warn"), (45, 60, "ok"), (60, 121, "good"),
                (121, 150, "ok"), (150, 10_000, "warn")]


def delivery_gauges(*, words: int, seconds: int, fillers: int,
                    answers: int = 0) -> list[dict]:
    """The Delivery panel as gauges — computed in code from measured words,
    speaking seconds and filler count. Empty list when there's no speech."""
    out: list[dict] = []
    if words and seconds:
        wpm = round(words / (seconds / 60))
        out.append(_gauge("pace", wpm, f"{wpm}", 80, 220, PACE_ZONES, pace_for(wpm)))
    if words:
        per100 = round(100 * fillers / words, 1)
        fv = "low" if per100 < 2 else ("typical" if per100 < 4 else "high")
        out.append(_gauge("fillers", per100, f"{per100:g}", 0, 8, FILLER_ZONES, fv))
    if answers and seconds:
        avg = round(seconds / answers)
        lv = "short" if avg < 60 else ("long" if avg > 120 else "on_target")
        out.append(_gauge("length", avg, f"{avg // 60}:{avg % 60:02d}", 0, 180, LENGTH_ZONES, lv))
    return out
