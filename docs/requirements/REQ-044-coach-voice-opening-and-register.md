# REQ-044: Coach voice — professional opening, calm HR register, local previews

Date: 2026-10-01
Source: Eduardo, live-voice Practice on -edu
Status: Building

## What they asked for
> "the session always gotta start Hey, Hi, hello, like a professional
> welcoming. then Salutation ("eduardo"), im xxx, and whatever will go after."

> "how to change the pitch of the AIs, they all sound very marketing, high vibe
> high pitch, not so calm, more human resource."

> "on the initial set up screen when i clicked the name of a AI interviewer, he
> says 'hi Theo', like he thinks im theo… is it a call? we gotta make it a .wav
> local file … not so robotic"

## What they actually need
The rehearsal should feel like a real screening call with a calm, experienced HR person. A hyped, salesy assistant makes the practice feel fake and raises nerves. The voice picker should play instantly and say the right thing.

## What we changed
- **Opening:** the P7 prompt fixes the order: "Hello {first name}, I'm {coach}. Thanks for making the time today — we'll talk about the {role} role at {company}." Then a calm transition to the first question. The first name comes from the résumé contact. With no name it falls back to a plain "Hello".
- **Register:** the prompt sets a calm, experienced HR interviewer: relaxed pace, low even tone, conversational. Never upbeat or salesy, no exclamations, no hype words.
- **Previews:** the "Hi Theo" bug happened because the sample line was sent to the Live model as a *user* turn, so it replied to "Theo". Previews are now made once with the TTS model, which reads the line verbatim ("Hello, I'm Theo. I'll be your interviewer today…"). They ship as `ui_web/static/voice_samples/<Voice>.wav`, so a click plays a local file with no API call. Regenerate with `scripts/gen_voice_samples.py --force`.

## On "pitch" — the levers we actually have
Gemini Live native audio has **no pitch, rate or SSML parameter**. The levers are:
1. **Voice choice.** The biggest lever. The current five (Sulafat, Callirrhoe, Achird, Enceladus, Charon) were chosen as "warm". Google's catalogue also describes calmer voices: *Vindemiatrix* (gentle), *Achernar* (soft), *Schedar* (even), *Gacrux* (mature), *Sadaltager* (knowledgeable). The candidate swap needs Eduardo's ear (A/B on -edu).
2. **Prompt register.** Shipped above. The native-audio model follows delivery instructions.
3. **Affective dialog** (`GEMINI_AFFECTIVE_DIALOG=1`). Adapts tone to the candidate. It's an A/B toggle and currently off.

## How we'll know it worked
- Every session opens with "Hello Eduardo, I'm Maya…".
- Eduardo describes the coach as calm or HR-like, not "marketing".
- Clicking a voice plays the right line instantly.

## Related
ADR-052 (direct Live), ADR-055 (-edu audio capture for A/B), REQ-041
