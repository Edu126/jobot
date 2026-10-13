# REQ-059: App-wide caps on voice practice and company search

Date: 2026-10-12
Source: Eduardo, 2026-10-12 ("make sure all the caps are managed", "voice maybe 50 a month", "Tavily is free, it will just stop")
Status: Built (ef8612a)

## Need
Before 20 strangers each get an app, every costly or shared call needs a ceiling. One file controls them all.

## What's built
- Gemini text: 600 calls a day per identity. This existed already.
- Voice: 3 sessions a day and 20 a month per app, charged once per session. Eduardo chose 20 on the launch page. Estimated worst case is about 12 USD per tester per month.
- Tavily: 10 a day and 100 a month per app, a slice of the free plan's shared 1,000. Over the cap, the brief is built from the JD alone.
- Overrides work without a deploy: `JOBOT_CAP_<KIND>_<DAY|MONTH>`. The `LLM_DISABLED` kill switch also stops both caps.
- Counts live in `gemini_usage` (identity `app`, model `budget:<kind>`) and show on /admin/pulse.

## Still open
Real voice cost isn't measured, because the browser talks to Gemini directly. Log session minutes on the client.
