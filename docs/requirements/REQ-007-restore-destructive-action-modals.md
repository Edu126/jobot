# REQ-007: Restore confirm modals on destructive account actions

Date: 2026-08-25
Source: Mehran (2026-08-25 PM feedback dump)
Status: Open

## What they asked for

> "Borrar todos mis datos" no muestra modal.
> "Reiniciar todas mis estadísticas" tampoco.

Both buttons on the Profile / Settings surface used to open a confirm
modal before firing. After the PR `79d3e6a` ("ATS 4 tiers + tiered
data-destruction") one or both wire-ups broke and the buttons are
either no-op, fire silently, or the modal partial is not rendered.

## What they actually need

A destructive-action button that fires without a confirm dialog is
worse than useless — it either erodes trust (user is scared to
touch it) or wipes real data by accident. The tiered
data-destruction PR added new copy and new tiers; somewhere in that
change the modal binding fell off. Root cause is likely one of:
Alpine `@click` referencing a modal state that no longer exists, an
HTMX `hx-confirm` removed in favour of a modal that never got
wired, or the modal partial being included conditionally on state
that no longer flips.

This is a regression fix, not a design change. The tiers themselves
(what each button does) stay. Only the confirm gate is missing.

## How we'll know it worked

- Clicking each destructive button on Profile opens a confirm modal
  before any request fires.
- Cancelling the modal fires no request (verified in the Network
  panel or via a smoke test).
- Confirming the modal executes the destruction and the button's
  post-condition holds (data actually cleared / stats actually reset).
- Regression note added to the tiered-destruction ADR (or a small
  new ADR) so the next refactor doesn't drop the gate again.

## Related

- Prior work: commit `79d3e6a` (tiered data destruction, likely
  regression source).
- [[feedback_htmx_busy_state_on_form]] — same class of
  Alpine ↔ HTMX interaction bug on iOS.
