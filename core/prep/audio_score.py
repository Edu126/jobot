"""Raw-audio interview scoring (ADR-052, GOV-008).

The Live streaming transcript is unreliable (wrong language / truncated), so the
debrief built from it is weak. Instead, the client records the candidate's spoken
answers and uploads a WAV once at the end; here we send that audio to an
audio-capable Gemini model for evidence-gated rubric checks (ADR-059) plus an
accurate transcript. Delivery numbers are counted in code from that transcript. The audio is uploaded transiently to the Gemini File API and
**deleted right after**; it is never stored by us (GOV-008).

Falls back to None on any failure so the caller can use the transcript-based
`practice.session_debrief_from_transcript` instead.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

# Audio-capable model for scoring (accepts audio + JSON) — centralized in gemini.py
# beside DEFAULT_MODEL_CHAIN so every model name has one home. Distinct from the Live
# model; a normal generate_content call.
from core.llm.gemini import AUDIO_SCORE_MODEL, resolve_api_key
from core.settings import language_instruction, resolve_output_language

from . import prompts as P
from . import session_score as SS
from .practice import _comp_ids, _parse_debrief, asked_competency_ids, delivery_metrics


def score_from_audio(
    wav_bytes: bytes,
    questions: list[dict],
    competencies: list[dict],
    *,
    turns: Optional[list[dict]] = None,
    candidate_seconds: int = 0,
    lang: Optional[str] = None,
) -> Optional[dict]:
    """Score the candidate's recorded answers from `wav_bytes`. Returns a debrief
    dict (Debrief shape + code-computed `delivery` + optional
    `clean_transcript_text`) ready for `db.save_practice_debrief`, or None on
    failure. `turns` (the live transcript) tells the model what the coach asked;
    the score is built in code from evidence-gated checks (ADR-059)."""
    if not wav_bytes or not competencies:
        return None
    lang = resolve_output_language(lang)

    # Respect the daily cap / kill-switch, like GeminiClient does.
    from core.llm import usage as llm_usage
    try:
        llm_usage.check_and_charge(model="any")
    except Exception:  # noqa: BLE001 — capped / disabled
        return None

    import google.genai as genai
    from google.genai import types as t

    client = genai.Client(api_key=resolve_api_key())
    uploaded = None
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name
        uploaded = client.files.upload(file=tmp_path)
        resp = client.models.generate_content(
            model=AUDIO_SCORE_MODEL,
            contents=[uploaded, t.Part(text=_build_prompt(questions, competencies, turns or [], lang=lang))],
            config=t.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
        )
        raw = json.loads(resp.text or "{}")
    except Exception as exc:  # noqa: BLE001 — any failure → caller falls back to transcript debrief
        # Leave a trace in `fly logs`: the fallback debrief is weaker, and silently so.
        print("[prep.audio_score] audio scoring failed, falling back:", type(exc).__name__, str(exc)[:200], flush=True)
        return None
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)   # GOV-008: don't retain audio
            except Exception:  # noqa: BLE001
                pass
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    ct = raw.get("clean_transcript")
    clean = ct.strip() if isinstance(ct, str) else ""
    live_said = " ".join(str(x.get("text", "")) for x in (turns or [])
                         if isinstance(x, dict) and x.get("role") != "coach")
    comp_ids = _comp_ids(competencies)
    # Quotes verify against the LIVE transcript (Gemini Live's speech-to-text of
    # what was actually said). Not `clean`: the same call that writes the quotes
    # writes it, so a hallucinated quote would verify against itself (REQ-042
    # "no credit without verifiable proof"). Only when there's no live transcript
    # at all does `clean` stand in. verify_quote's token-overlap fallback absorbs
    # speech-to-text drift.
    debrief = _parse_debrief(raw, valid_comps=set(comp_ids), comp_ids=comp_ids,
                             transcript=live_said if live_said.strip() else clean,
                             asked_ids=asked_competency_ids(questions))
    if debrief is None:
        return None
    out = debrief.to_dict()
    out["delivery"] = code_delivery(clean or live_said, candidate_seconds)
    if clean:
        out["clean_transcript_text"] = clean
    return out


def code_delivery(text: str, seconds: int) -> dict:
    """Delivery numbers counted in CODE from the transcript + measured speaking
    time (ADR-048) — the model's own wpm guess was 305 for normal speech."""
    d = delivery_metrics(text, seconds, 0)
    return {"wpm": d["wpm"], "filler_count": d["filler_count"],
            "seconds": d["seconds"], "word_count": d["word_count"],
            "pace": SS.pace_for(d["wpm"])}


def _build_prompt(questions: list[dict], competencies: list[dict], turns: list[dict], *, lang: str) -> str:
    q_lines = "\n".join(f"- {str(q.get('text','')).strip()}"
                        for q in questions if str(q.get("text", "")).strip())
    asked_lines = "\n".join(f"- {str(x.get('text','')).strip()}" for x in turns
                             if isinstance(x, dict) and x.get("role") == "coach"
                             and str(x.get("text", "")).strip()) or "(not available)"
    return f"""You are an expert interview coach. The attached audio is a candidate's spoken answers in a practice interview (their voice only). Judge the CANDIDATE's answers from the AUDIO — what they actually said, strictly.

{P.RULE_BLOCK}

{language_instruction(lang)}

Do this:
1. Write one takeaway sentence addressed to the candidate as "you" (never "the candidate"): the biggest strength and the biggest thing to improve. If the answers were weak, say so plainly.
2. Score every competency with the checks below.
3. List the top 3 actions for next time, addressed to the candidate ("you") — specific and doable in one practice session.
4. Provide a clean, accurate transcript of what the candidate said (their turns joined), word for word.
5. Suggest the next drill: one competency or null.

Questions planned for this interview:
{q_lines}

What the interviewer actually asked (live transcript, may be imperfect):
{asked_lines}

Competencies:
{P.format_competencies(competencies)}

{SS.RUBRIC_BLOCK}

Return JSON with this exact schema — no prose before or after:
{{
  "takeaway": "string",
  {SS.EVIDENCE_SCHEMA},
  "top_actions": ["string", "string", "string"],
  "stories_to_revisit": [],
  "next_drill": {{ "competency_id": "c1 | null", "question_id": null, "reason": "string" }},
  "clean_transcript": "string"
}}"""
