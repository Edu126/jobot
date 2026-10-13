# REQ-060: See real jobs before uploading a résumé

Date: 2026-10-12
Source: Eduardo (guide decision page): "like LinkedIn, where you see jobs just by saying what you're looking for as a career, on the onboarding, so we're loading results in the background in case he doesn't upload a résumé; he will live the experience, but with no score."
Status: Open

## Need
The first minute decides whether a stranger stays. Today nothing happens until a résumé is in, and the first live search is slow. If onboarding asks "What role are you looking for, and where?" and starts that search in the background, the first screen is real jobs.

## Shape
- The onboarding wizard asks for the role and location, then starts the search.
- The results show without fit scores. One nudge says "Add your résumé to see how well you fit each one."
- When the résumé arrives, the same results get scored.

## Risk
Jobs without scores look like any other job board, so the résumé nudge carries the value.

## How we'll know it worked
Most users see their first job list within 60 seconds of sign-up. Activation is 60% on day 0 (REQ-054).

## Related
REQ-058, REQ-010
