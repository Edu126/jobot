"""Per-app key/value settings stored in the existing `meta` SQLite table.

No schema bump — settings live under the `settings.*` key prefix in
`meta` so they don't collide with `schema_version` or other meta rows.

Why not a dedicated `user_settings` table: no auth yet, one user per
Fly app. When auth ships (docs/rate-limiting-quotas.md §10) this moves
to `user_settings(user_id, key, value)` — same public API, different
storage under the hood.

Callers use:
    from core import settings
    settings.get("ui_language", default="en")
    settings.set("home_city", "Bogotá, Colombia")

Higher-level resolvers (`get_ui_language`, `get_output_language`) apply
the fallback chain described in docs/next-work.md.
"""
from __future__ import annotations

from core import db


# Small in-process cache. Cleared on `set` for the key that changed.
# Full-file reload on server restart, which is fine — settings change
# rarely (Profile toggles) relative to how often they're read.
_cache: dict[str, str] = {}

# Prefix keeps settings namespaced from other meta rows (schema_version,
# etc.). Not exposed to callers — they pass raw keys.
_PREFIX = "settings."


def get(key: str, default: str = "") -> str:
    """Read a setting. Returns `default` if the key isn't set."""
    if key in _cache:
        return _cache[key]
    full_key = _PREFIX + key
    with db.connect() as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (full_key,)
        ).fetchone()
    val = row["value"] if row else default
    _cache[key] = val
    return val


def set(key: str, value: str) -> None:
    """Persist a setting. Updates the cache atomically with the write."""
    full_key = _PREFIX + key
    with db.tx() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (full_key, value),
        )
    _cache[key] = value


def clear_cache() -> None:
    """Test/dev hook — drop the in-process cache. Safe to call anytime."""
    _cache.clear()


# ── language resolvers ────────────────────────────────────────────────
# The two knobs users see in Profile: `ui_language` and `output_language`.
# Reasoning language is coupled to UI (see docs/next-work.md).
#
# Supported languages — grow this list when adding a third locale. Keep
# in sync with `ui_web/i18n.py::TRANSLATIONS`.
SUPPORTED_LANGUAGES = ("en", "es")
DEFAULT_LANGUAGE = "en"


def get_ui_language(accept_language: str = "") -> str:
    """Resolve the UI language for the current request.

    Priority:
      1. Explicit user setting (`settings.ui_language`)
      2. Browser `Accept-Language` header — first supported match
      3. `DEFAULT_LANGUAGE` fallback (English)
    """
    explicit = get("ui_language", "")
    if explicit in SUPPORTED_LANGUAGES:
        return explicit
    return _parse_accept_language(accept_language)


def get_output_language() -> str:
    """Language for generated resumes / cover letters / LLM output.

    Priority:
      1. Explicit user setting (`settings.output_language`)
      2. Whatever `settings.ui_language` is (or its fallback)
    """
    explicit = get("output_language", "")
    if explicit in SUPPORTED_LANGUAGES:
        return explicit
    ui = get("ui_language", "")
    if ui in SUPPORTED_LANGUAGES:
        return ui
    return DEFAULT_LANGUAGE


def get_reasoning_language() -> str:
    """Language for user-facing LLM reasoning (score reasoning, matched
    skills, gaps). Coupled to UI language — a Spanish UI showing English
    gaps reads as broken. Not user-configurable independently.

    Read from core code (background workers, non-request contexts) so
    this doesn't depend on the request's Accept-Language header — it
    only uses the explicit setting.
    """
    ui = get("ui_language", "")
    if ui in SUPPORTED_LANGUAGES:
        return ui
    return DEFAULT_LANGUAGE


# ── prompt-language slot ──────────────────────────────────────────────
# Every Gemini prompt template includes this line at the top so JSON
# string values in the response come back in the right language. Kept
# short + explicit so translators / model tuners can spot it easily.

def language_instruction(lang: str) -> str:
    """Prompt-fragment: tell the model to reply in a specific language.

    Emit a strong, structured directive. Gemini honors this reliably
    across Flash / Pro tiers. Use in every prompt whose output strings
    are eventually shown to the user (score reasoning, tailored resume,
    cover letter). Skip in extraction — that's passthrough of source
    content, not generated text.
    """
    label = {"en": "English", "es": "Spanish"}.get(lang, "English")
    # LatAm register anchor for ES output. Users are in Colombia / Mexico /
    # LATAM; the default "Spanish" reads as Spain register to Gemini and
    # produces vosotros / candidatura / sueles. The extra sentence pushes
    # it toward the register a Colombian professional actually uses.
    register = (
        " Use Latin American Spanish register (NOT Spain): prefer "
        "\"postulación\" over \"candidatura\", \"acostumbras\" over \"sueles\", "
        "\"currículum\" over \"currículo\"; avoid vosotros; avoid \"vale\" as filler."
        if lang == "es" else ""
    )
    return (
        f"IMPORTANT: Respond in {label}.{register} Every string value in the JSON "
        f"response — descriptions, reasoning, bullet points, headers, "
        f"everything the user will see — must be in {label}. Field NAMES "
        f"and the JSON structure stay in English regardless."
    )


def _parse_accept_language(header: str) -> str:
    """Return the first supported language in an `Accept-Language`
    header. Tolerates quality suffixes (`;q=0.8`), locales (`es-CO`),
    and empty/missing headers.

    Doesn't respect q-priority — the first supported token wins. Good
    enough for a two-language app."""
    if not header:
        return DEFAULT_LANGUAGE
    for token in header.split(","):
        lang = token.split(";", 1)[0].strip().lower()
        # `es-CO` → `es`
        primary = lang.split("-", 1)[0]
        if primary in SUPPORTED_LANGUAGES:
            return primary
    return DEFAULT_LANGUAGE
