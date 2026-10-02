"""Generate the voice-picker previews as static WAVs shipped with the app.

    .venv/bin/python scripts/gen_voice_samples.py            # missing only
    .venv/bin/python scripts/gen_voice_samples.py --force    # regenerate all

Writes ui_web/static/voice_samples/<Voice>.wav — one TTS call per voice, then
the setup screen plays a local file (no API call, no "Hi Theo" reply). Re-run
with --force whenever VOICES, the sample line or the voice model changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.prep import live  # noqa: E402


def main() -> int:
    force = "--force" in sys.argv
    live.STATIC_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    failed = 0
    for voice in live.VOICES:
        out = live.STATIC_SAMPLES_DIR / f"{voice}.wav"
        if out.exists() and not force:
            print(f"skip {voice} (exists)")
            continue
        wav = live.synthesize_sample(voice)
        if not wav:
            print(f"FAIL {voice}")
            failed += 1
            continue
        out.write_bytes(wav)
        print(f"ok   {voice} ({live.coach_name(voice)}) {len(wav)//1024} KB")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
