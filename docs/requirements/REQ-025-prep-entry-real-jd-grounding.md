# REQ-025: Prep entry — always ground on a REAL JD, and make the kit's layers legible

Date: 2026-09-05
Source: Eduardo (self-testing Prep on -edu: March Networks, Kanak)
Status: Open

## What they asked for
Verbatim, batched from the -edu test:

1. **Link = a first-class, self-sufficient path.** "cuando le doy el link, este
   debería ser única opción también… le paso el link, él revisa mi resume, hace
   el score etc, no need to tailor porque ya estamos en prep, pero sí hace el
   scraping del job si se puede?"
2. **Paste-the-JD fallback when we don't hold the vacancy** — and the paste box
   should NOT show the full text back. "solo se ve el 'paste here job
   description, we will do the magic'… ellos no tienen preview del texto, solo
   algo tipo 'xxx lines pasted'. Siento que este paso está como mocho."
3. **The kit's questions must read as grounded in real layers.** "no sé si lo
   linkea con la empresa o con el rol… deben haber capas reales."
4. **Kit build failed once** (March Networks → "Couldn't build the kit right
   now — reopen in a moment"), and he expected gaps we'd *already saved* to feed
   it.

(Also shipped this pass, no decision needed: skeleton loaders replacing the
plain "Working…" state; Prev/counter/Next clustered inline-center — CRAP.)

## What they actually need
When Prep is entered by **typing a role name only**, the kit is built off a thin
signal (role string + résumé) and the questions feel generic — "mocho." The real
need: **every entry path should try to obtain the actual JD text**, because the
JD is the layer that makes STAR/reverse questions specific. Three intake routes,
one grounded outcome:

- **Link** → scrape+extract the JD (reuse `core/jobs/from_url.job_from_url`),
  score it against the current résumé (no tailoring — Prep is post-apply), create
  a bound session carrying the real JD.
- **Paste** → `extract_job_from_text`; the textarea collapses to a
  "N lines pasted" chip (capture-not-preview, like Claude's paste affordance).
- **Type company+role** → stays the light path, but is explicitly the *weakest*
  grounding; nudge toward link/paste.

Then the kit must **show its layers** — surface what it grounded on (company
intel · role/JD · your résumé · known gaps) so the user trusts the questions
aren't generic. And a transient generation failure must be **distinct** from an
honestly-empty kit (issue #4): different copy, and a real retry rather than a
dead "reopen in a moment."

## How we'll know it worked
Pasting a LinkedIn JD (no preview, just "42 lines pasted") or a link yields a kit
whose STAR/reverse questions cite the specific role's responsibilities — and the
user can see, at a glance, which real inputs the kit stands on. The generic-role
path is visibly the fallback, not the default.

## Addendum (2026-09-05, second -edu pass + design review)
Shipped this pass: skeleton loaders, clustered Prev/Next, smart input + paste
chip, import→confirm + self-contained score, kit "grounded on" layers, kit
retry, directionally-correct import error copy + LinkedIn Share-link tip,
**"Refresh news" gated to fallback** (ADR-031, cost).

Still open, from Eduardo's review + the UX/adversarial/persona analysis:

1. **Fit narrative up top (highest value).** The context bar shows title +
   score only. Reuse the scorer's `reasoning` (one-line why-fit) + top
   `matched` strengths + top `gaps` to defend — the same "fit summary" the
   Tailor already produces. At the PREP stage the candidate already has the
   interview, so the score's *meaning* shifts from "should I apply" to "where do
   I lean in / what do I shore up" — reframe/soften the raw % accordingly.
   (Needs storing reasoning/matched/gaps on the session, or deriving for bound.)
2. **STAR honesty framing.** Label STAR answers as drafts grounded in specific
   résumé lines ("make it yours") — an AI-authored STAR risks sounding scripted
   or nudging embellishment (GOV-005). Consider surfacing the source bullet.
3. **LinkedIn link how-to as a graphic hint** (tooltip / short gif) — text tip
   shipped; the visual explainer is deferred (it's a complex action to teach).
4. **Empty news facet** — collapse/merge instead of a lonely "—".
5. **Launchpad positioning + a "was this enough?" BI signal** — persona read:
   Prep is "enough" for less-technical/less-savvy candidates, a strong "intro"
   for senior/technical ones (they'll still Google for org/interviewer/tech
   depth). Capture that fork with a micro-signal instead of chasing full depth.

## Related
- Reuses `core/jobs/from_url` (scrape + LLM extract) — likely a new ADR for
  using it inside Prep entry (no tailoring, score-only).
- Refines ADR-026 (entry ladder), ADR-028 (kit grounding + failure vs empty).
- ADR-027 / ADR-029 (company intel) already provide the company layer.
