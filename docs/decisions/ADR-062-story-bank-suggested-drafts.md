# ADR-062: Empty Story Bank lazy-loads AI-suggested STAR drafts

Date: 2026-09-27 (backfilled 2026-10-01)
Status: Accepted
Relates to: REQ-045, ADR-050

## Context
The empty state was a dead end (REQ-045).

## Decision
- The empty state lazy-loads `GET /stories/suggested`, which runs P5 drafts from the résumé.
- It renders the same draft cards as `/stories/draft`, shared through `partials/story_drafts.html`.
- Drafts are suggestions until the user saves them, and they're grounded in the résumé only (GOV-005).

## Alternatives considered
- Static examples: generic, and nothing to do with the user's résumé.
- Generating on upload: costs an LLM call for users who never open Stories.

## Consequences
One lazy LLM call on the first empty visit. The card partial now has two callers.
