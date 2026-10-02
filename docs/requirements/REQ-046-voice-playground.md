# REQ-046: A voice playground to tune the coach by ear

Date: 2026-10-01
Source: Eduardo
Status: Building. **Engine switched to the real Live model** (Eduardo: "here we are testing text to speech, not the real live API"). v1 on -edu (ADR-068): line test, live override. v1.1, same day: A/B replaced by a recorded takes list with ★ rating + ♥, per Eduardo's "only one is fine, record each one tested, list on the side, rate or like".

## What they asked for
> "me gustaría tener un playground de voces, donde podamos jugar a subir y
> bajar las opciones disponibles, speed, speech, tones etc."

> On adaptive voice: "es experimental, son esas donde descubrimos a veces
> cosas nuevas."

## What they actually need
We pick voices and delivery by guessing, then find out in a full live session, which is slow and expensive. Eduardo needs a quick loop: change one knob, hear the result, compare, keep the winner. Settings that win in the lab get promoted to the real coach.

## What the knobs really are (Gemini, 2026-10)
There's no pitch, rate or SSML parameter on native-audio Live. The real levers:

| Knob | Where | Notes |
|---|---|---|
| Voice (30 prebuilt) | Live + TTS `voice_name` | Biggest lever. Calm candidates: Vindemiatrix, Achernar, Schedar, Gacrux, Sadaltager |
| Delivery instruction (speed, tone, energy) | Prompt text: Live system prompt, or a TTS style line ("Say calmly, slowly…") | Natural-language control. This is how "speed" and "tone" really move |
| Personality style | P7 `style` | neutral / friendly / sharp / harsh |
| Temperature | Live config | Affects wording variety, not the voice |
| **Affective dialog** (experimental) | `enable_affective_dialog` (`GEMINI_AFFECTIVE_DIALOG`) | Adapts tone to the candidate's emotion. Exploratory |
| Proactive audio (experimental) | Live config | The model may choose not to answer irrelevant input |
| VAD sensitivity / silence ms | `realtime_input_config` | How fast it jumps in. Affects whether it feels rushed |
| Client pauses | ADR-054 | Pacing between sentences |

## Recommendation (how to work)
1. **-edu only**, behind a flag (`JOBOT_VOICE_LAB=1`), at `/lab/voice`. It never reaches users.
2. **Two modes:**
   - **Line test:** TTS, cheap and instant. Pick a voice, a style line and a sample sentence, and hear it.
   - **Live test:** a 60-second mini-interview using the same pinned config the real coach uses, including the experimental toggles.
3. **Side-by-side A/B.** Two configs, same line, blind order. Eduardo rates them (calm, human, clear) and each trial is logged with its full config.
4. **Promote, don't fork.** A winning config becomes a code change to `VOICES` / P7 with an ADR. The lab never writes settings that users get.
5. **Experiments are labelled.** Affective dialog and proactive audio carry an "experimental" tag and their findings get written down. That's where we discover new things.

## How we'll know it worked
Eduardo can change a voice or delivery setting and hear the difference in under 10 seconds. The default coach ends up chosen from logged A/B ratings, not guesswork.

## Related
REQ-044, ADR-063, ADR-054, ADR-055 (-edu audio capture)

## Measured on the real Live model (2026-10-01)
Same line, `gemini-3.8-live`:

| Config | Raw | With Jobot stretch |
|---|---|---|
| Vindemiatrix · slower · calm · low | 9.0 s | 10.1 s |
| Puck · faster · upbeat · high | 8.1 s | 9.6 s |

Speed, tone and energy instructions barely move Live's pace (TTS showed 11.5 s vs 7.6 s, a false signal). The voice and our pause stretch are the levers that matter.
