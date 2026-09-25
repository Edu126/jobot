"""Practice live-voice — direct browser ↔ Gemini Live (ADR-052, GOV-008).

The browser connects DIRECTLY to the Gemini Live API with the official
`@google/genai` SDK, using a short-lived **ephemeral token** minted here that
PINS our config (P7 system instruction + candidate/company context + the chosen
voice + input/output transcription + AUDIO out) via `live_connect_constraints`,
so the client can't change the model, prompt, or voice. The model conducts the
whole interview itself using automatic VAD — no server relay, no app-orchestrated
turns. Mic audio streams browser→Google directly and is NEVER stored (GOV-008);
only the text transcript is posted back for the holistic debrief.

This module now provides: `is_enabled()`, `create_ephemeral_token()`, the shared
`_config()` / `_load_context()` (also used to build the token constraints), the
voice list, and the voice-preview sample. Env-gated: `GEMINI_LIVE_MODEL` unset →
`is_enabled()` is False and Practice stays text-only.
"""
from __future__ import annotations

import datetime
import os
from typing import Optional

from core import db
from core.llm.gemini import resolve_api_key

from .practice import interviewer_context_turn, interviewer_system_prompt

# Standard Gemini Live audio rates (the browser handles the audio now).
INPUT_RATE = 16000
OUTPUT_RATE = 24000

# Ephemeral token lifetimes.
_TOKEN_EXPIRE_MIN = 30
_TOKEN_SESSION_START_MIN = 2

# Curated prebuilt voices offered in the UI (Gemini TTS/Live voice names). The
# docs don't label gender; these are the widely-perceived male/female picks.
# {value: (label_gender, characteristic)} — the route/template read VOICES.
VOICES = {
    "Kore": ("female", "Firm"),
    "Aoede": ("female", "Breezy"),
    "Puck": ("male", "Upbeat"),
    "Charon": ("male", "Informative"),
}
DEFAULT_VOICE = "Kore"

# Interviewer personas (shown as a dropdown in setup). Each bundles a name, a
# voice, and an interviewing style folded into the P7 core prompt. `voice` must
# be one of VOICES (drives the token's speech config + the preview).
PERSONAS = {
    "maya": {"name": "Maya", "voice": "Aoede",
             "blurb": "Friendly HR screener",
             "style": "warm, friendly and encouraging — an HR screener who puts the candidate at ease"},
    "david": {"name": "David", "voice": "Charon",
              "blurb": "Direct hiring manager",
              "style": "direct, concise and probing — a hiring manager who pushes for specifics and results"},
    "sam": {"name": "Sam", "voice": "Puck",
            "blurb": "Supportive mentor",
            "style": "patient and supportive — a mentor who gives the candidate space to think"},
}
DEFAULT_PERSONA = "maya"


def persona_meta(persona_id: str) -> dict:
    return PERSONAS.get(persona_id, PERSONAS[DEFAULT_PERSONA])


_SAMPLE_LINE = "Hi, I'm your interview coach. Let's get you ready — take a breath, and we'll begin."


def _log(*a) -> None:
    """Stdout trace for live-session debugging — visible in `fly logs`."""
    print("[prep.live]", *a, flush=True)


def _samples_dir():
    from core.db import DB_PATH
    d = DB_PATH.parent / "voice_samples"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pcm_to_wav(pcm: bytes, rate: int = OUTPUT_RATE) -> bytes:
    """Wrap raw little-endian 16-bit mono PCM in a minimal WAV header so the
    browser can play it with a plain <audio>/Audio()."""
    import struct
    n = len(pcm)
    header = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", n)
    return header + pcm


async def voice_sample_wav(voice: str) -> Optional[bytes]:
    """A short spoken sample of `voice` as WAV, generated once via the Live model
    and cached on disk (so the picker can play it). None if voice unavailable."""
    if voice not in VOICES or not is_enabled():
        return None
    cache = _samples_dir() / f"{voice}.wav"
    if cache.exists():
        return cache.read_bytes()

    from google.genai import types as t
    import google.genai as genai
    client = genai.Client(api_key=resolve_api_key())
    config = t.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=t.SpeechConfig(voice_config=t.VoiceConfig(
            prebuilt_voice_config=t.PrebuiltVoiceConfig(voice_name=voice))),
    )
    pcm = bytearray()
    try:
        async with client.aio.live.connect(model=live_model(), config=config) as sess:
            await sess.send_client_content(
                turns=t.Content(role="user", parts=[t.Part(text=_SAMPLE_LINE)]),
                turn_complete=True)
            async for resp in sess.receive():
                sc = getattr(resp, "server_content", None)
                if sc and getattr(sc, "model_turn", None) and sc.model_turn.parts:
                    for p in sc.model_turn.parts:
                        blob = getattr(p, "inline_data", None)
                        if blob and blob.data:
                            pcm += blob.data
                if sc and getattr(sc, "turn_complete", False):
                    break
    except Exception as exc:  # noqa: BLE001
        _log("voice_sample failed:", type(exc).__name__, str(exc)[:150])
        return None
    if not pcm:
        return None
    wav = _pcm_to_wav(bytes(pcm))
    try:
        cache.write_bytes(wav)
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass
    return wav


def live_model() -> str:
    return (os.getenv("GEMINI_LIVE_MODEL") or "").strip()


def is_enabled() -> bool:
    """Voice is available only when a Live model is configured AND we have a key."""
    return bool(live_model()) and bool(resolve_api_key())


# The coach conducts in English (the target for now) — enforced via the prompt
# (language_codes on transcription isn't supported on the Developer API).
LIVE_LANG = "en"


def _config(interview: dict, lang: str, persona_id: str = DEFAULT_PERSONA):
    """Build the LiveConnectConfig pinned into the ephemeral token: the SHORT P7
    core prompt (persona identity + behaviour + tone — context/questions injected
    separately to avoid the >~4000-char silent hang), the persona's voice,
    both-side transcription, VAD tuned so echo/background noise doesn't flicker
    the turn, and session resumption so a ~10-min GoAway can be resumed."""
    from google.genai import types as t
    p = persona_meta(persona_id)
    voice_name = p["voice"] if p["voice"] in VOICES else DEFAULT_VOICE
    return t.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=t.Content(parts=[t.Part(
            text=interviewer_system_prompt(interview, lang=LIVE_LANG,
                                           coach_name=p["name"], style=p["style"]))]),
        input_audio_transcription=t.AudioTranscriptionConfig(),
        output_audio_transcription=t.AudioTranscriptionConfig(),
        speech_config=t.SpeechConfig(
            voice_config=t.VoiceConfig(
                prebuilt_voice_config=t.PrebuiltVoiceConfig(voice_name=voice_name))),
        temperature=0.7,
        realtime_input_config=t.RealtimeInputConfig(
            automatic_activity_detection=t.AutomaticActivityDetection(
                start_of_speech_sensitivity=t.StartSensitivity.START_SENSITIVITY_LOW,
                end_of_speech_sensitivity=t.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=200,
                silence_duration_ms=700,
            )),
        session_resumption=t.SessionResumptionConfig(),
    )


def _load_context(interview: dict, lang: str):
    """(brief_dict, persona, cues_by_question_index) for the live session — what
    the coach knows + the Study-mode STAR cues. Best-effort; empties on miss."""
    from . import brief as prep_brief
    from . import mapping as prep_mapping
    b = prep_brief.read_cached_brief(interview["id"], lang=lang)
    brief_dict = b.to_dict_for_cache() if b else None
    persona = ""
    if interview.get("resume_id"):
        try:
            from core.resume import ai_summary
            persona = ai_summary.persona_line(int(interview["resume_id"])) or ""
        except Exception:  # noqa: BLE001 — persona is a nice-to-have
            persona = ""
    # Study cues: competency what_good + mapped story title, keyed by competency.
    cue_by_comp: dict = {}
    if b:
        comp_by_id = {c.id: c for c in b.competencies}
        stories = db.list_stories(interview["resume_hash"], status="saved")
        mapping = prep_mapping.read_cached_mapping(interview["id"], stories, lang=lang) or []
        story_by_id = {str(s["id"]): s for s in stories}
        for m in mapping:
            comp = comp_by_id.get(m.competency_id)
            if not comp:
                continue
            story = story_by_id.get(m.story_id) if m.story_id else None
            cue_by_comp[m.competency_id] = {
                "competency": comp.name, "what_good": comp.what_good_looks_like,
                "story_title": story["title"] if story else None}
        # also cover competencies with no mapping row
        for c in b.competencies:
            cue_by_comp.setdefault(c.id, {
                "competency": c.name, "what_good": c.what_good_looks_like, "story_title": None})
    return brief_dict, persona, cue_by_comp


def create_ephemeral_token(interview: dict, session_row: dict, *, lang: str):
    """Mint a single-use ephemeral token + build the context turn for a direct
    browser↔Gemini Live session (ADR-052). The token pins the SHORT persona core
    prompt + voice + VAD + transcription (client can't change them); the
    candidate/company context + questions ride in the returned `context` string,
    which the client injects via sendClientContent (kept out of the pinned prompt
    to avoid the >~4000-char silent hang). Returns (token_name, context) or None
    (voice disabled / no questions / mint failed → client falls back to text)."""
    if not is_enabled():
        return None
    questions = session_row.get("questions") or []
    if not questions:
        return None
    import google.genai as genai
    from google.genai import types as t

    persona_id = session_row.get("persona") or DEFAULT_PERSONA
    brief_dict, candidate_persona, _cues = _load_context(interview, lang)
    cfg = _config(interview, lang, persona_id)
    context = interviewer_context_turn(interview, questions, brief=brief_dict,
                                       persona=candidate_persona)
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    client = genai.Client(api_key=resolve_api_key())
    try:
        token = client.auth_tokens.create(config=t.CreateAuthTokenConfig(
            uses=1,
            expire_time=now + datetime.timedelta(minutes=_TOKEN_EXPIRE_MIN),
            new_session_expire_time=now + datetime.timedelta(minutes=_TOKEN_SESSION_START_MIN),
            live_connect_constraints=t.LiveConnectConstraints(model=live_model(), config=cfg),
        ))
    except Exception as exc:  # noqa: BLE001 — mint failure → client falls back to text
        _log("token_mint_failed:", type(exc).__name__, str(exc)[:200])
        return None
    _log(f"token minted model={live_model()} persona={persona_id} "
         f"ctx(brief={bool(brief_dict)},persona={bool(candidate_persona)})")
    return token.name, context
