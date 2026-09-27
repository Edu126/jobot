"""Raw-audio interview scoring (ADR-052, GOV-008).

The Live streaming transcript is unreliable (wrong language / truncated), so the
debrief built from it is weak. Instead, the client records the candidate's spoken
answers and uploads a WAV once at the end; here we send that audio to an
audio-capable Gemini model for a debrief grounded in the ACTUAL audio — content
bands + delivery read from the voice itself (pace, fillers, confidence) — plus an
accurate transcript. The audio is uploaded transiently to the Gemini File API and
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
from core.settings import get_output_language, language_instruction

from . import prompts as P
from .practice import _parse_debrief


def score_from_audio(
    wav_bytes: bytes,
    questions: list[dict],
    competencies: list[dict],
    *,
    lang: Optional[str] = None,
) -> Optional[dict]:
    """Score the candidate's recorded answers from `wav_bytes`. Returns a debrief
    dict (Debrief shape + `delivery` from the audio + optional `clean_transcript`)
    ready for `db.save_practice_debrief`, or None on failure."""
    if not wav_bytes or not competencies:
        return None
    lang = lang if lang is not None else get_output_language()

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
            contents=[uploaded, t.Part(text=_build_prompt(questions, competencies, lang=lang))],
            config=t.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
        )
        raw = json.loads(resp.text or "{}")
    except Exception:  # noqa: BLE001 — any failure → caller falls back to transcript debrief
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

    valid = {str(c.get("id", "")).strip() for c in competencies if isinstance(c, dict)}
    debrief = _parse_debrief(raw, valid_comps=valid)
    if debrief is None:
        return None
    out = debrief.to_dict()
    out["delivery"] = _clean_delivery(raw.get("delivery"))
    ct = raw.get("clean_transcript")
    if isinstance(ct, str) and ct.strip():
        out["clean_transcript_text"] = ct.strip()
    return out


def _clean_delivery(d) -> dict:
    """Delivery read from the audio — numeric where the model can, qualitative
    labels otherwise. Safe defaults on a malformed blob."""
    d = d if isinstance(d, dict) else {}
    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0
    return {
        "wpm": _int(d.get("wpm")),
        "filler_count": _int(d.get("filler_count")),
        "pace": str(d.get("pace", "")).strip().lower() or "unknown",          # slow|on_target|fast
        "confidence": str(d.get("confidence", "")).strip().lower() or "unknown",  # low|medium|high
    }


def _build_prompt(questions: list[dict], competencies: list[dict], *, lang: str) -> str:
    q_lines = "\n".join(f"- {str(q.get('text','')).strip()}"
                        for q in questions if str(q.get("text", "")).strip())
    return f"""You are an expert interview coach. The attached audio is a candidate's spoken answers in a practice interview (their voice only). Judge the CANDIDATE from the AUDIO — both what they said and HOW they said it (pace, filler words, confidence).

{P.RULE_BLOCK}

{language_instruction(lang)}

Do this:
1. Write one takeaway sentence: the biggest strength and the biggest thing to improve.
2. Give one band per competency (strong/solid/needs_work), based on how the answers demonstrated it.
3. List the top 3 actions for next time — specific and doable in one practice session.
4. Read delivery FROM THE AUDIO: approximate words-per-minute (wpm), filler-word count, pace (slow|on_target|fast), and confidence (low|medium|high).
5. Provide a clean, accurate transcript of what the candidate said (their turns joined).
6. Suggest the next drill: one competency or null.

Questions the interview covered:
{q_lines}

Competencies:
{P.format_competencies(competencies)}

Return JSON with this exact schema — no prose before or after:
{{
  "takeaway": "string",
  "competency_bands": [{{ "competency_id": "c1", "band": "strong|solid|needs_work" }}],
  "top_actions": ["string", "string", "string"],
  "stories_to_revisit": [],
  "next_drill": {{ "competency_id": "c1 | null", "question_id": null, "reason": "string" }},
  "delivery": {{ "wpm": 0, "filler_count": 0, "pace": "slow|on_target|fast", "confidence": "low|medium|high" }},
  "clean_transcript": "string"
}}"""
