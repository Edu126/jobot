"""Thin wrapper around the google-genai SDK — with model fallback and
daily-quota awareness.

Reasons this exists instead of calling genai directly from callers:
- Single place to set JSON-mode + timeout + retry policy.
- Caller passes an API key or we read from env, never both styles mixed.
- Errors get a consistent shape (`GeminiError`) so the UI can render them.
- **Fallback chain**: gemini-2.5-flash's free tier is 20 req/day. That
  dies fast. We now try `-lite` variants first (higher quotas) and only
  fall back to gemini-2.5-flash when everything else fails.
- **Quota tracking**: when a model returns 429, we remember it's exhausted
  for the rest of today (persisted in the `gemini_model_state` DB table so
  it survives Fly machine cycling — see `_mark_exhausted`). Subsequent calls
  short-circuit past it instead of wasting 8s hitting the API just to be
  told no, and the fallback chain stays on the SAME model across restarts.

Free-tier quotas as of 2026-08 (verified from Google AI Studio dashboard):
    - gemini-3.5-flash-lite:    500/day peak (primary — best perf/quota ratio)
    - gemini-3.1-flash-lite:    500/day peak (backup, same tier)
    - gemini-2.5-flash:         20/day       (last resort — small quota, wide compat)

If any of the -lite model IDs stops existing, the client detects it and
moves on to the next one. Chain survives naming drift.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

import json as _json


# Ordered by preference: try the two 500/day -lite models first, keep the
# 20/day gemini-2.5-flash as a small-cap safety net at the end.
# (Removed gemini-2.5-flash-lite from the chain — not confirmed available on
# Google's free tier as of 2026-08.)
DEFAULT_MODEL_CHAIN = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
]

DEFAULT_MODEL = DEFAULT_MODEL_CHAIN[0]   # backward-compat single-model callers


class GeminiError(RuntimeError):
    """Raised for any Gemini-call failure that the UI should display."""


class QuotaExhaustedError(GeminiError):
    """All models in the fallback chain hit their per-day quota."""


# Per-model daily state (quota exhaustion + successful request counts) is
# persisted in the `gemini_model_state` SQLite table (schema v18), keyed
# (model, day). It used to be module-level RAM, but that reset on every Fly
# `auto_stop_machines` wake — which (a) re-probed exhausted models (wasted
# 429s) and (b) let the fallback chain land on a DIFFERENT model across runs
# → inconsistent scores (next-work.md, Mehran's unstable re-score). DB-backed
# state fixes both. All helpers below swallow DB errors and degrade to the
# old "assume not exhausted, count 0" behaviour so bookkeeping can never
# break a real generate call (e.g. CLI use before init_db).


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _mark_exhausted(model: str) -> None:
    try:
        from core import db
        with db.tx() as conn:
            conn.execute(
                "INSERT INTO gemini_model_state (model, day, exhausted, count) "
                "VALUES (?, ?, 1, 0) "
                "ON CONFLICT(model, day) DO UPDATE SET exhausted = 1",
                (model, _today_str()),
            )
    except Exception:
        pass


def _exhausted_models_today() -> set[str]:
    """One query for all models down today — callers filter their own chain
    against this set rather than issuing a query per model."""
    try:
        from core import db
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT model FROM gemini_model_state WHERE day = ? AND exhausted = 1",
                (_today_str(),),
            ).fetchall()
        return {r["model"] for r in rows}
    except Exception:
        return set()


def _increment_count(model: str) -> None:
    try:
        from core import db
        with db.tx() as conn:
            conn.execute(
                "INSERT INTO gemini_model_state (model, day, exhausted, count) "
                "VALUES (?, ?, 0, 1) "
                "ON CONFLICT(model, day) DO UPDATE SET count = count + 1",
                (model, _today_str()),
            )
    except Exception:
        pass


def request_counts_today() -> dict[str, int]:
    """Return {model: count} for successful requests made today.
    Model order matches DEFAULT_MODEL_CHAIN for display purposes."""
    counts: dict[str, int] = {}
    try:
        from core import db
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT model, count FROM gemini_model_state WHERE day = ?",
                (_today_str(),),
            ).fetchall()
        counts = {r["model"]: int(r["count"]) for r in rows}
    except Exception:
        pass
    return {model: counts.get(model, 0) for model in DEFAULT_MODEL_CHAIN}


# Rough per-day free-tier caps for the UI (approximate — Google may change).
MODEL_QUOTAS = {
    "gemini-3.5-flash-lite": 500,
    "gemini-3.1-flash-lite": 500,
    "gemini-2.5-flash": 20,
}


def _is_quota_error(exc: Exception) -> bool:
    """Detect 429 RESOURCE_EXHAUSTED across the various shapes google-genai
    surfaces. It sometimes has `.code`, sometimes only in `str(exc)`."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    s = str(exc).lower()
    return "429" in s or "resource_exhausted" in s or "quota" in s


def exhausted_models() -> list[str]:
    """For UI display: which models are down until tomorrow."""
    return list(_exhausted_models_today())


@dataclass
class GeminiClient:
    api_key: str
    # `model_name` kept for backward compat; if provided AND `model_chain`
    # is None, we use a single-model chain of just that one.
    model_name: Optional[str] = None
    model_chain: Optional[list[str]] = None
    temperature: float = 0.4
    max_output_tokens: int = 8192

    _client: genai.Client = field(init=False, repr=False)
    # Which model actually served the most recent successful call — so
    # callers (semantic_score) can label ScoreResult.model accurately.
    last_model_used: Optional[str] = field(init=False, default=None)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise GeminiError("No Gemini API key provided.")
        # Resolve which chain to use
        if self.model_chain is None:
            self.model_chain = (
                [self.model_name] if self.model_name else list(DEFAULT_MODEL_CHAIN)
            )
        if not self.model_name:
            self.model_name = self.model_chain[0]
        self._client = genai.Client(api_key=self.api_key)

    # ── public: quota-aware short-circuit ─────────────────────
    def all_models_exhausted(self) -> bool:
        """True if every model in this chain hit quota today. Callers can
        skip expensive prep work when this is the case."""
        down = _exhausted_models_today()
        return all(m in down for m in self.model_chain)

    def available_models(self) -> list[str]:
        return [m for m in self.model_chain if m not in _exhausted_models_today()]

    # ── public: main entry point ──────────────────────────────
    def generate_json(
        self, prompt: str, *, max_retries: int = 2, temperature: Optional[float] = None
    ) -> dict:
        """Try each model in the chain until one succeeds. On 429 for a
        model, mark it exhausted and move on. Non-quota failures propagate
        so the UI can show the real error.

        `temperature` overrides the client default for THIS call only —
        scoring passes 0.0 for determinism (ADR-018) while resume/cover
        generation keeps the client's creative default. None = use
        `self.temperature`.

        Enforces the LLM_DISABLED kill switch and the per-identity daily
        cap before touching the wire — see `core.llm.usage`. Identity
        comes from a request-scoped ContextVar set by
        `ui_web.middleware.IdentityMiddleware`.
        """
        # Kill switch + per-identity daily cap. Uses "any" as model bucket
        # because the fallback chain means a single logical call may hit
        # different models; the cap is on total calls per identity per day.
        from core.llm import usage as llm_usage
        llm_usage.check_and_charge(model="any")

        available = self.available_models()
        if not available:
            raise QuotaExhaustedError(
                "All configured Gemini models hit their daily quota. "
                "Try again tomorrow, or add a model with higher quota."
            )

        last_exc: Optional[Exception] = None
        for model in available:
            try:
                result, tokens_in, tokens_out = self._call_one(
                    model, prompt, max_retries, temperature
                )
                self.last_model_used = model
                _increment_count(model)   # track successful requests only
                llm_usage.record_tokens(model, tokens_in, tokens_out)
                return result
            except QuotaExhaustedError as exc:
                _mark_exhausted(model)
                last_exc = exc
                continue
            except GeminiError:
                raise   # non-quota → don't try other models, they'll fail too

        raise QuotaExhaustedError(
            f"All models exhausted for today. "
            f"Chain: {', '.join(self.model_chain)}"
        ) from last_exc

    # ── internal ──────────────────────────────────────────────
    def _call_one(
        self, model: str, prompt: str, max_retries: int, temperature: Optional[float] = None
    ) -> tuple[dict, int, int]:
        """Call a single model with retry. Translates 429 into QuotaExhaustedError
        so the outer loop can advance to the next model.

        Returns (parsed_json, tokens_in, tokens_out). Token counts are 0
        when the SDK doesn't report usage_metadata."""
        config = types.GenerateContentConfig(
            temperature=self.temperature if temperature is None else temperature,
            max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json",
        )

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                _check_finish_reason(response, self.max_output_tokens)
                text = (response.text or "").strip()
                if not text:
                    raise GeminiError(f"{model}: empty response")
                parsed = _safe_json_parse(text)
                tokens_in, tokens_out = _extract_token_usage(response)
                return parsed, tokens_in, tokens_out

            except GeminiError:
                raise
            except Exception as exc:
                # Detect quota exhaustion FIRST — retrying won't help there.
                if _is_quota_error(exc):
                    raise QuotaExhaustedError(f"{model}: {exc}") from exc
                # Transient errors → backoff + retry
                last_err = exc
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise GeminiError(
                    f"{model} failed after {max_retries + 1} attempts: {exc}"
                ) from exc

        raise GeminiError(f"{model} failed: {last_err}")


def _extract_token_usage(response) -> tuple[int, int]:
    """Best-effort read of prompt/response token counts from google-genai
    responses. Field is `usage_metadata` with `prompt_token_count` and
    `candidates_token_count`. Returns (0, 0) if the field is missing —
    older SDKs and safety-filtered responses may omit it."""
    meta = getattr(response, "usage_metadata", None)
    if not meta:
        return 0, 0
    tokens_in = int(getattr(meta, "prompt_token_count", 0) or 0)
    tokens_out = int(getattr(meta, "candidates_token_count", 0) or 0)
    return tokens_in, tokens_out


# ── response validation ──────────────────────────────────────

def _check_finish_reason(response, max_tokens: int) -> None:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise GeminiError(
            "Gemini returned no candidates — likely blocked by safety filters."
        )
    reason = getattr(candidates[0], "finish_reason", None)
    reason_name = getattr(reason, "name", str(reason)) if reason is not None else "UNKNOWN"

    if reason_name in ("STOP", "FINISH_REASON_UNSPECIFIED"):
        return
    if reason_name == "MAX_TOKENS":
        raise GeminiError(
            f"Hit output token limit ({max_tokens}) — response was truncated. "
            f"Try a shorter resume/JD or raise max_output_tokens."
        )
    if reason_name == "SAFETY":
        raise GeminiError("Gemini blocked the response under safety filters.")
    if reason_name == "RECITATION":
        raise GeminiError("Gemini blocked the response for recitation/copyright.")
    raise GeminiError(f"Gemini stopped unexpectedly: finish_reason={reason_name}")


def _safe_json_parse(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        return _json.loads(cleaned)
    except _json.JSONDecodeError as exc:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return _json.loads(cleaned[start:end + 1])
            except _json.JSONDecodeError:
                pass
        raise GeminiError(f"Could not parse Gemini response as JSON: {exc}") from exc


# ── key resolution ───────────────────────────────────────────

def resolve_api_key(runtime_key: Optional[str] = None) -> str:
    """Pick an API key in priority order: runtime arg → env → .env file."""
    if runtime_key:
        return runtime_key.strip()
    load_dotenv()
    env_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    return (env_key or "").strip()
