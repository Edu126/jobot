# REQ-002: Settings accessible from every page (floating panel)

Date: 2026-08-19 (first ask); 2026-08-20 (re-asked, marked as
accumulated debt with "I told you")
Source: User
Status: Shipped (PR C, 2026-08-20)

## What they asked for

> "Language y notificación i'll move to the floating bubble que
> aparece cuando le damos click en el gear que está arriba en la
> parte superior derecha. (aun no tenemos muchas cosas para tener un
> single settings page)"

Later, on 2026-08-20: _"modal floating on the right, something
coming out of the gear"_.

## What they actually need

Two coupled needs, only one of which is on the surface:

1. **Zero navigation cost to change Language / Notifications.** The
   gear icon used to navigate to `/profile` → Language tab. Two
   clicks + a page load to change one preference is friction that
   compounds — especially during ES/EN QA where the user flips
   language often.

2. **Profile page becomes only Profile.** The Settings hub was
   sharing a two-column grid with the resume card. Removing Settings
   lets Profile be a full-width single-column page dedicated to
   resume + contact + ATS + destructive actions. This half of the
   ask was implicit — user surfaced it explicitly in the next batch
   ("let's make it a single row and column").

## How we'll know it worked

- Changing UI language works from any page without leaving the
  current view.
- Profile page has no Language/Notifications section — it's only
  about the resume.
- User stops re-asking (the "I told you" was the signal that we'd
  lost this ask twice already).

## Related

- `ui_web/templates/partials/settings_panel.html` (new component)
- `ui_web/deps.py:settings_ctx()` Jinja global (data plumbing so
  the panel renders on every page without route-level threading)
- Alpine store `settings` in `base.html` (state)
- Vision "Post-POC direction" bullet: real auth (magic-link +
  Google) will likely surface as more Settings tabs — the floating
  panel is the container that grows with them.
