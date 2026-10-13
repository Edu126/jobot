# ADR-085: Roll Prep out to everyone as a labelled beta

Date: 2026-10-12
Status: Accepted (Eduardo, launch decision page: "Now, labelled beta")

## Context
Prep runs only on hermana. The merge blockers in next-work.md are still open: answer quality (REQ-052), session-score calibration, and the provider review. Eduardo: "this score is not useful, we need to bring everyone to the latest version."

## Decision
- Merge the prep branch into main, which ships it to every user.
- The Prep nav carries a "Beta" tag.
- The session score is hidden (`JOBOT_SHOW_SESSION_SCORE`, on only on -edu). Users see the evidence and the takeaway.
- Before the merge:
  - snapshot every user volume
  - set `GEMINI_LIVE_MODEL` on every user app
  - add hermana back to the deploy matrix
- The voice budget (REQ-059) limits cost.

## Consequences
Answer quality and calibration keep going on -edu. The provider review is no longer a gate on the rollout. It stays open for the shared app.
