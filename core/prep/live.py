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

# VOICE and PERSONALITY are DECOUPLED (Eduardo 2026-09-25): the old bundled
# "persona" hard-coded a voice+personality together, which was wrong. Now the UI
# offers two separate dropdowns — pick a voice (timbre only) AND a personality.

# The coach voices — picked BY EAR in the voice lab on the real Live model
# (Eduardo, 2026-10-02, ADR-069). {value: (gender, description, name)}. Names are
# short, friendly, and never one of our real users' names.
VOICES = {
    "Erinome": ("female", "Calm", "Anna"),
    "Sulafat": ("female", "Warm", "Maya"),
    "Iapetus": ("male", "Calm", "Tom"),
}
DEFAULT_VOICE = "Erinome"

# Each voice's winning delivery from the lab (speed / tone / energy → a
# delivery line via voice_lab.delivery_line). Sulafat won at higher energy.
VOICE_DELIVERY = {
    "Erinome": {"speed": "slower", "tone": "calm", "energy": "medium"},
    "Sulafat": {"speed": "slower", "tone": "calm", "energy": "high"},
    "Iapetus": {"speed": "slower", "tone": "calm", "energy": "medium"},
}

# Eduardo's winning voice direction (lab, 2026-10-02) — appended to every
# coach's delivery. Measured: Live answers fine with long prompts (ADR-053 update).
NATURAL_SPEECH = (
    "You are a natural, low-pitched, professional interviewer speaking out loud. "
    "Sound like a real person, not a script. Natural speech rules: "
    "- When the candidate finishes a point, use short acknowledgments: \"mhm\", \"right\", \"got it\". "
    "- Use light fillers only before thinking moments, like moving to a new question or reacting to "
    "something unexpected: \"hmm\", \"um\", \"let me see\", \"okay so\". "
    "- Occasionally self-correct mid-sentence: \"Can you tell me about... actually, let me ask it differently.\" "
    "- Max one filler per turn. Never start every sentence with one. Simple statements need none. "
    "- Keep turns short. Ask one question at a time, then wait."
)


def coach_delivery(voice: str) -> str:
    """The coach's delivery instruction for `voice`: its lab preset + the
    natural-speech rules. Used in P7 for every real session."""
    from . import voice_lab
    preset = VOICE_DELIVERY.get(voice, VOICE_DELIVERY[DEFAULT_VOICE])
    return voice_lab.delivery_line(voice_lab.clean_config({**preset, "extra": NATURAL_SPEECH}))

# Interviewer PERSONALITIES (the second dropdown). Personality only — no voice,
# no name. Each `style` is folded into the P7 core prompt (interviewer_system_prompt).
# Neutral is the default. Kept to four; all hard-coded here.
PERSONALITIES = {
    "neutral": {"label": "Neutral",
                "blurb": "Even and professional",
                "style": "even, professional and impartial — you neither warm up nor push hard; you ask, listen, and move on matter-of-factly"},
    "friendly": {"label": "Friendly",
                 "blurb": "Warm, puts you at ease",
                 "style": "warm and encouraging — you put the candidate at ease with a relaxed, supportive manner, while still keeping the interview on track"},
    "sharp": {"label": "Sharp",
              "blurb": "Probing, wants specifics",
              "style": "sharp and probing — you press for specifics, numbers and outcomes and follow up on anything vague; concise and businesslike, never hostile"},
    "harsh": {"label": "Harsh",
              "blurb": "Tough, high bar",
              "style": "tough and skeptical — you set a high bar and challenge weak answers directly without handing out reassurance; demanding but always professional and fair, never rude or personal"},
}
DEFAULT_PERSONALITY = "neutral"


def coach_name(voice: str) -> str:
    """The first name the coach uses for this voice. A lab-only voice (not in
    VOICES, REQ-046) introduces itself by its Gemini name."""
    if voice in VOICES:
        return VOICES[voice][2]
    return voice or VOICES[DEFAULT_VOICE][2]


def personality_meta(personality_id: str) -> dict:
    return PERSONALITIES.get(personality_id, PERSONALITIES[DEFAULT_PERSONALITY])


# The picker preview. Spoken AS the coach (never sent as a user turn — the
# Live model used to reply "Hi Theo!" to it, thinking the user was the coach).
_SAMPLE_LINE = ("Hello, I'm {name}. I'll be your interviewer today. "
                "Take a moment to get settled, and we'll begin when you're ready.")
# Pre-generated previews shipped with the app (scripts/gen_voice_samples.py) —
# a local file, no API call when the candidate clicks a voice.
STATIC_SAMPLES_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "ui_web" / "static" / "voice_samples"


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
    """The picker preview for `voice` as WAV. Order: the shipped static file →
    the on-disk cache → generate once with the TTS model (reads the line
    verbatim in the coach's own voice) and cache it. None if unavailable."""
    if voice not in VOICES:
        return None
    static = STATIC_SAMPLES_DIR / f"{voice}.wav"
    if static.exists():
        return static.read_bytes()
    cache = _samples_dir() / f"{voice}-live.wav"
    if cache.exists():
        return cache.read_bytes()
    if not resolve_api_key():
        return None
    import asyncio
    wav = await asyncio.to_thread(synthesize_sample, voice)
    if wav:
        try:
            cache.write_bytes(wav)
        except Exception:  # noqa: BLE001 — cache is best-effort
            pass
    return wav


def synthesize_sample(voice: str) -> Optional[bytes]:
    """One REAL Live generation of the sample line in `voice` (script mode),
    with Jobot's pause stretch applied — so the preview sounds like the coach
    in a session, not like a different TTS model (REQ-046). Used by the route on
    a cache miss and by scripts/gen_voice_samples.py to ship static previews."""
    from . import voice_lab
    cfg = voice_lab.clean_config({"voice": voice, "mode": "script",
                                  **VOICE_DELIVERY.get(voice, VOICE_DELIVERY[DEFAULT_VOICE]),
                                  "extra": NATURAL_SPEECH})
    got = voice_lab.live_pcm(cfg, _SAMPLE_LINE.format(name=coach_name(voice)))
    if not got:
        return None
    return _pcm_to_wav(voice_lab.stretch_pauses(got[0]))


def live_model() -> str:
    return (os.getenv("GEMINI_LIVE_MODEL") or "").strip()


def save_audio_enabled() -> bool:
    """-edu-only debug toggle (default off): persist practice audio to the volume so
    Eduardo can A/B the raw coach audio vs Google's playground and I can measure pacing.
    Breaks GOV-008's "audio is never stored" — SCOPED to -edu via `JOBOT_SAVE_AUDIO=1`,
    opt-in per session, deletable, never in prod (ADR-055)."""
    return (os.getenv("JOBOT_SAVE_AUDIO") or "").strip().lower() in ("1", "true", "yes", "on")


def saved_audio_dir():
    """Where persisted practice audio lives (the Fly volume on -edu)."""
    from core.db import DB_PATH
    return DB_PATH.parent / "practice_audio"


def affective_dialog_enabled() -> bool:
    """A/B toggle (default off): when on, the native-audio model adapts tone/rhythm to
    the candidate's voice. Set `GEMINI_AFFECTIVE_DIALOG=1` on -edu to test whether the
    coach sounds more natural — Gemini Live has no explicit pause control, so this is the
    only server-side naturalness lever. Off by default; flip via `fly secrets set`."""
    return (os.getenv("GEMINI_AFFECTIVE_DIALOG") or "").strip().lower() in ("1", "true", "yes", "on")


def is_enabled() -> bool:
    """Voice is available only when a Live model is configured AND we have a key."""
    return bool(live_model()) and bool(resolve_api_key())


# The coach conducts in English (the target for now) — enforced via the prompt
# (language_codes on transcription isn't supported on the Developer API).
LIVE_LANG = "en"


def candidate_first_name(interview: dict) -> str:
    """The candidate's first name from their résumé contact block, for the
    coach's greeting ("Hello Eduardo, I'm Maya…"). Empty when unknown — the
    greeting then falls back to a plain "Hello"."""
    try:
        r = db.get_resume(int(interview.get("resume_id") or 0)) if interview.get("resume_id") else None
        name = (((r or {}).get("parsed") or {}).get("contact") or {}).get("name", "")
    except Exception:  # noqa: BLE001 — a greeting must never block the session
        return ""
    first = str(name or "").strip().split()
    return first[0].strip(",.").capitalize() if first and first[0].isalpha() else ""


def _config(interview: dict, lang: str, personality_id: str = DEFAULT_PERSONALITY,
            voice: str = DEFAULT_VOICE):
    """Build the LiveConnectConfig pinned into the ephemeral token: the SHORT P7
    core prompt (personality behaviour + tone — context/questions injected
    separately to avoid the >~4000-char silent hang), the CHOSEN voice (decoupled
    from personality), both-side transcription, VAD tuned so echo/background noise
    doesn't flicker the turn, and session resumption so a ~10-min GoAway resumes."""
    from google.genai import types as t

    from . import voice_lab
    pers = personality_meta(personality_id)
    voice_name = voice if voice in VOICES else DEFAULT_VOICE
    delivery = coach_delivery(voice_name)   # the lab-picked delivery for this voice (ADR-069)
    # Voice playground override (REQ-046/ADR-068) — -edu only, flag-gated.
    lab = voice_lab.live_override()
    affective, silence_ms, extra = affective_dialog_enabled(), 700, {}
    if lab:
        voice_name = lab["voice"]
        delivery = voice_lab.delivery_line(lab)
        affective = lab["affective"] or affective
        silence_ms = lab["silence_ms"]
        if lab["proactive"]:
            extra["proactivity"] = t.ProactivityConfig(proactive_audio=True)
        _log(f"voice_lab override voice={voice_name} affective={affective} "
             f"proactive={lab['proactive']} silence_ms={silence_ms}")
    return t.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=t.Content(parts=[t.Part(
            text=interviewer_system_prompt(interview, lang=LIVE_LANG,
                                           coach_name=coach_name(voice_name),
                                           style=pers["style"],
                                           candidate_name=candidate_first_name(interview),
                                           delivery=delivery))]),
        input_audio_transcription=t.AudioTranscriptionConfig(),
        output_audio_transcription=t.AudioTranscriptionConfig(),
        speech_config=t.SpeechConfig(
            voice_config=t.VoiceConfig(
                prebuilt_voice_config=t.PrebuiltVoiceConfig(voice_name=voice_name))),
        temperature=0.7,
        enable_affective_dialog=affective,
        realtime_input_config=t.RealtimeInputConfig(
            automatic_activity_detection=t.AutomaticActivityDetection(
                start_of_speech_sensitivity=t.StartSensitivity.START_SENSITIVITY_LOW,
                end_of_speech_sensitivity=t.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=200,
                silence_duration_ms=silence_ms,
            )),
        session_resumption=t.SessionResumptionConfig(),
        **extra,
    )


def _load_context(interview: dict, lang: str):
    """(brief_dict, persona) for the live session — what the coach knows.
    Best-effort; empties on miss."""
    from . import brief as prep_brief
    b = prep_brief.read_cached_brief(interview["id"], lang=lang)
    brief_dict = b.to_dict_for_cache() if b else None
    persona = ""
    if interview.get("resume_id"):
        try:
            from core.resume import ai_summary
            persona = ai_summary.persona_line(int(interview["resume_id"])) or ""
        except Exception:  # noqa: BLE001 — persona is a nice-to-have
            persona = ""
    return brief_dict, persona


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

    personality_id = session_row.get("persona") or DEFAULT_PERSONALITY  # `persona` col now holds the personality id
    voice = session_row.get("voice") or DEFAULT_VOICE
    brief_dict, candidate_persona = _load_context(interview, lang)
    cfg = _config(interview, lang, personality_id, voice)
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
    _log(f"token minted model={live_model()} personality={personality_id} voice={voice} "
         f"ctx(brief={bool(brief_dict)},persona={bool(candidate_persona)})")
    return token.name, context
