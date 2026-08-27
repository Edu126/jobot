# REQ-013: User Onboarding

Date: 2026-08-26
Source: Eduard (product owner)
Status: Building

## What they asked for
> "siento que la gente entra a la app y 1) no está claro que es nuevo, y 2) si es un nuevo usuario, no sabe qué hacer, no hemos pensado en como sería el onboarding. vamos con driver.js"

## What they actually need
Two distinct problems bundled together:
1. **New users** don't know where to start — the app has no empty-state guidance or first-time flow.
2. **Returning users** don't know when something changed — no "what's new" signal after a deploy.

Driver.js is the chosen implementation tool.

## How we'll know it worked
A brand-new user can complete their first job search without asking "what do I do now?"
A returning user notices when a new feature lands without being told out-of-band.

## Related
ADR-014-driver-js-onboarding-wizard-and-tour.md
REQ-010 (language pick on first visit — absorbed into the wizard step 1)
