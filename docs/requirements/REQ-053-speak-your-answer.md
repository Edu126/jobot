# REQ-053: Speak your answer instead of typing it

Date: 2026-10-12
Source: Eduardo, Get Ready check-in on -edu
Status: Building

## What they asked for
"When preparing an answer or something particularly related to the job, it
should have the option for voice recording as well, so they can use their
voice." Also: the hint "⌘/Ctrl + Enter for next" mixes Mac and Windows.

## What they actually need
Getting real detail out of people is easier spoken than typed; every field
where they give their own words should accept voice. And small copy should
fit the device they're on.

## How we'll know it worked
Every Get Ready answer field (check-in questions, answer-card gap fills) has
"Speak your answer"; speech lands as editable text; the shortcut hint shows
⌘ on a Mac and Ctrl elsewhere.

## Related
`ui.dictate` macro + `static/dictate.js` (browser speech-to-text; hidden where
unsupported). Reuse it in the Answer Bank (ADR-080). Note: Chrome's speech
recognition sends audio to Google to transcribe; nothing is stored by us.
