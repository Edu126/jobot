# REQ-043: Delivery numbers shown on gauges against real baselines

Date: 2026-10-01
Source: Eduardo, reviewing Practice Feedback
Status: Building (gauges shipped on the feature branch)

## What they asked for
> "WPM is good, but it means nothing, like, pace fast? what does it mean? i
> think we gotta show this more on a gauge plus some short explanations, like
> whats the baseline. do research. real ones."

## What they actually need
A number like "305 wpm" or "4 fillers" means nothing without a reference point.
The candidate needs three things: where they landed, what normal looks like,
and whether it helps or hurts in an interview. Each one needs a real source,
not a vibe.

## The baselines (researched 2026-10-01)

| Metric | Baseline | Source | How we use it |
|---|---|---|---|
| **Pace (wpm)** | ~150 wpm is the typical US conversational rate | National Center for Voice and Speech (NCVS), via [VirtualSpeech](https://virtualspeech.com/blog/average-speaking-rate-words-per-minute) and [Wikipedia: Speech tempo](https://en.wikipedia.org/wiki/Speech_tempo) | Zones: <110 slow (warn) · 110–129 ok · **130–160 good** · 161–170 ok · >170 rushed (warn) |
| Pace, relaxed chat | 196 wpm over a whole call, 236 wpm with silences removed (2,438 Switchboard phone calls between strangers) | Yuan, Liberman & Cieri 2006, *Towards an integrated understanding of speaking rate in conversation*, Interspeech ([PDF](http://itre.cis.upenn.edu/myl/llog/icslp06_final.pdf)) | Context only: casual chat runs fast. An interviewer taking notes needs slower. That's why we cap "good" at 160, below the casual rate |
| Pace → perception | Faster speech is rated more **competent**, but warmth ("benevolence") peaks at normal speed and drops above it | Smith, Brown, Strong & Rencher 1975, *Effects of Speech Rate on Personality Perception*, Language & Speech ([doi](https://doi.org/10.1177/002383097501800203)) | This is why both ends of the scale are amber: slow reads hesitant, fast reads less likeable |
| **Fillers** (uh/um) | **2.56 per 100 words** on average (≈1.5–3.5 by role and gender). Total disfluencies 5.97 per 100 words | Bortfeld et al. 2001, *Disfluency Rates in Conversation*, Language & Speech 44(2), Table 4A ([PDF](https://heatherbortfeld.com/wp-content/uploads/2016/09/bortfeld_etal_ls2001.pdf)) | Normalised **per 100 words** (a raw count depends on how long you talked). Zones: <2 fluent · 2–4 typical · >4 high |
| Fillers → interview ratings | Models of rated mock interviews recommend "speak more fluently, use less filler words" | Naim et al. 2015, *Automated Analysis and Prediction of Job Interview Performance* (MIT), [arXiv:1504.03425](https://arxiv.org/abs/1504.03425) | Lower fillers are good, but we don't claim a precise hiring effect |
| **Answer length** | 1–2 min per behavioural (STAR) answer | Practitioner guidance, not a study ([Indeed STAR guide](https://www.indeed.com/career-advice/interviewing/how-to-use-the-star-interview-response-technique), [CMU Tepper](https://www.cmu.edu/tepper/alumni/assets/docs/star-story.pdf)) | Zones: <45s warn · 45–59 ok · **60–120 good** · 121–150 ok · >150 warn. The UI copy says "recruiters usually advise", not "research shows" |

**Rejected sources:** blog claims like "fast speakers rated 30% more competent" (no traceable study), and AI-generated "2026 guides". Every number we show must trace to a table above.

## Design
- Each gauge has a zoned track (good / ok / warn tints), a marker where you landed, the value + unit, a verdict pill and a one-line note that names the baseline. Built with `ui.gauge`; the data comes from `session_score.delivery_gauges`.
- Inputs are **measured in code**: words, speaking seconds, filler count. With no measurement there's no gauge, and we never show a guess. Speaking seconds come from the candidate's recorded audio, measured on the server ([ADR-070](../decisions/ADR-070-speaking-time-measured-from-audio.md)). The browser's level-gated count gave 0 s, or too few seconds, on quiet mics.
- The length gauge only appears when the per-answer count is known (the typed path). The voice path can't split answers reliably yet.

## How we'll know it worked
Eduardo reads "139 wpm · Easy to follow — everyday conversation is about 150" and knows what to do without asking what the number means.

## Related
REQ-042 (score inventory, row 14), ADR-059, ADR-048 (delivery in code), ADR-070 (speaking time from audio)
