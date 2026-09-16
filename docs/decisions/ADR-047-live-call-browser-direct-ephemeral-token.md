# ADR-047: The live prep call runs browser↔Gemini directly, over an ephemeral token; our server never carries audio

Date: 2026-09-16
Status: Accepted (design) — implementation gated on **G1** (free tier) and
**G3** (token-bound constraints). See REQ-041 "Open gates". **If G3 comes back
negative, this ADR does not hold** and the transport must change.
Relates to: REQ-041, ADR-001 (one small Fly app per user), ADR-003 (no build
step), ADR-004 (Gemini free tier + fallback chain), ADR-008 (prompt/call-site
conventions), GOV-008 (voice data)

## Context

Prep needs a real-time voice call. jobot runs **one small Fly machine per user**
with `auto_stop_machines` — a box sized for HTMX fragments and SQLite, not for
proxying a bidirectional 16 kHz PCM stream for five minutes. Relaying audio
through FastAPI would mean a long-lived WebSocket per call, audio buffering, and a
machine that can never sleep.

Research (Pillar 3) established: the Live API is **WebSocket-only** (no native
WebRTC), and Google's **ephemeral tokens exist precisely so a browser can
connect directly** without holding the real API key — `newSessionExpireTime`
~1 min to open, `expireTime` ~30 min once running. The JS SDK (`@google/genai`)
is importable as a **CDN ES module**, so no bundler is required.

## Decision

**The browser opens the Live session itself.** Our server's only role in the
audio path is to **mint a short-lived, single-use ephemeral token**, right
before the client connects, and then step out.

- `POST /prep/{id}/call/token` — server-side: checks the résumé + session exist,
  checks the caps (ADR-051), builds the **system instruction** (company outlook
  + JD + résumé + the selected deck of kit questions), mints the token, logs the
  BI event, returns `{token, config}`.
- The page imports `@google/genai` from a CDN as `<script type="module">` and
  connects with the token. **ADR-003 holds: still no build step.**
- The **real `GEMINI_API_KEY` never reaches the client.** Tokens are minted per
  call, never reused across calls or users.
- **The token is minted CONFIG-LOCKED, not config-suggested.**
  *(Added 2026-09-16 after an adversarial review; this clause is the difference
  between a design and a hole.)* The mint call binds the session shape into the
  token itself — `live_connect_constraints.bidi_generate_content_setup` —
  pinning **model**, **system instruction**, `response_modalities: ["AUDIO"]`,
  the session cap, and an **empty tools array**. The client then connects to
  the constrained endpoint (`BidiGenerateContentConstrained`).
  **Why this clause exists:** the client sends the setup frame. A token that
  merely *travels alongside* a config is a token whose holder picks their own
  model, duration, modality, tools and system instruction — on our key. Every
  cap in ADR-051 would be advisory, and "no live-call attach" (GOV-008) would be
  a sentence rather than a property. ⚠ The exact field/endpoint names come from
  secondary sources (`ai.google.dev` is egress-blocked from our research
  sandbox) — **gate G3 in REQ-041 blocks implementation on confirming the SDK
  in use supports token-bound constraints.** If it does not, this ADR does not
  hold and the transport must change (server-side relay, or no feature).
- **Untrusted content is fenced inside the system instruction.** `jd_text`
  arrives from a scraped URL or a paste — attacker-controllable by construction
  — and `company` / `role_title` are user-supplied strings. All of them are
  wrapped in the sentinel + "inert data" pattern `core/jobs/from_url.py` already
  uses. **ADR-008 rule 4's "the JD in scoring is trusted" exemption is NOT
  inherited here** — see ADR-052, which narrows it.
- **The transcript postback is bound to the minted session.** The browser posts
  what it claims was said; the endpoint accepts it only against the specific
  call it minted, once. A debrief quotes the user's words back to them as fact
  (ADR-049), so the input to it cannot be a free-form string anyone can POST.
- **VAD is tuned slower than a sales agent's.** `silenceDurationMs` raised and
  end-of-speech sensitivity lowered, because a candidate pausing mid-answer to
  think is not a finished turn (pre-mortem #1). Exact values are a contract-layer
  constant, tuned on -edu, never a user-facing setting (non-negotiable #2).
- **`sessionResumption` is configured defensively** even though a 5-minute call
  fits inside the ~10-minute socket lifetime — mobile backgrounding is real.
- The Live session needs an ADR on two counts: **ADR-008 rule 6** (it runs on a
  Live-API model, not `DEFAULT_MODEL_CHAIN` — an override), and
  `llm-surface.md`'s own "Adding a new site" step 4 (*a new pattern — a new
  model, streaming, a tool that changes the output mode — opens an ADR before
  shipping*). This is that ADR. It also gets its own row in the inventory, which
  is what rule 7 requires.

## Alternatives considered

- **Proxy the audio through FastAPI.** Rejected: puts a media stream on a box
  sized for HTML fragments, defeats `auto_stop_machines`, and adds an entire
  failure surface for zero benefit — Google's own design point is direct client
  connection.
- **WebRTC via a partner bridge** (LiveKit / Pipecat / Daily). Rejected for the
  POC: a third-party vendor, an account, and infra we don't need for a 1:1 call.
  It is the documented upgrade path if WebSocket audio quality disappoints on
  poor mobile networks.
- **Long-lived API key in the client.** Never. Each beta user supplies **their
  own** `GOOGLE_API_KEY` to their own Fly app (GOV-001) — so leaking it burns
  *their* quota and, if they ever enable billing, *their* money. A per-call
  token is the only shape that doesn't put that credential in a browser.
- **Cascaded STT → text LLM → TTS** (our own pipeline). Rejected: research put
  cascaded stacks at $0.007–0.029/conversation-minute against our modelled
  ~$0.012/min for native audio — *no cost win* — while adding three vendors,
  three failure modes and serialization latency past the ~500 ms turn-taking
  cliff.

## Consequences

- **Ops cost stays ~zero.** No media on our machine; the call survives the box
  sleeping between HTMX requests.
- The client holds real logic for the first time (audio capture, playback,
  socket lifecycle). That is a genuine strain on ADR-003's "server-rendered
  strings" ergonomics — the honest first crack in that decision. Accepted here
  because the alternative is worse; noted as evidence if ADR-003 is revisited.
- Token minting is a **security boundary**: it is where caps, ownership checks
  and BI logging must live, because nothing downstream of it is ours to enforce.
- We cannot inspect or moderate the stream server-side. Grounding therefore has
  to be front-loaded into the system instruction (ADR-048) rather than policed
  turn-by-turn. **This is precisely why the token must be config-locked**: the
  locked setup is the *only* thing we get to decide, so everything we care about
  has to be expressed there or not at all.
- **The system instruction is assembled server-side and never handed to the
  client as text.** Under config-locking it rides inside the token; the browser
  receives a credential, not the user's résumé in a JSON body it could leak to a
  browser extension or leave in a devtools log. (GOV-008 records this.)
- If Google changes ephemeral-token semantics, the whole transport changes. The
  blast radius is one route + one JS module.
