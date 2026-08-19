"""Two-language UI translation. No Babel, no `.po` files, no compile step.

At two languages a dict lookup is more honest than a full i18n
framework — smaller install, no build step, trivially readable diffs
when translations change. When a third language arrives we can either
extend the dict or migrate to Babel; the `_()` call site doesn't need
to change either way.

## Usage

Templates use the `_()` Jinja global (registered in `ui_web/deps.py`):

    <button>{{ _('nav.jobs') }}</button>
    <span>{{ _('jobs.results.count', n=totalJobs) }}</span>

Python code uses `translate()` directly:

    from ui_web.i18n import translate
    msg = translate("errors.rate_limited", lang="es")

## Fallback chain

    lookup in `lang` dict → lookup in EN dict → return the raw key

Returning the key on miss is deliberate: an untranslated string shows
up as e.g. `nav.jobs` in the UI, which is loud enough to spot in a
screenshot but doesn't crash the render. Better than blank space or an
error.

## Per-request language

The current UI language is stashed in a ContextVar by
`IdentityMiddleware` at the start of each request. `_()` reads that
ContextVar so templates never have to pass `lang` explicitly.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from core.settings import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


# Set by request middleware; read by `_()` / `translate()`. Absent
# outside a request context (background workers, scripts) — resolvers
# fall back to `DEFAULT_LANGUAGE`.
_current_ui_language: ContextVar[str] = ContextVar(
    "current_ui_language", default=DEFAULT_LANGUAGE
)


def set_ui_language(lang: str) -> object:
    """Bind the UI language for the current request context. Returns a
    Token the caller passes back to `reset_ui_language`. Usually
    middleware handles both — call sites don't need to touch this."""
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    return _current_ui_language.set(lang)


def reset_ui_language(token: object) -> None:
    _current_ui_language.reset(token)  # type: ignore[arg-type]


def current_ui_language() -> str:
    return _current_ui_language.get()


def translate(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Translate a key. `lang` overrides the ContextVar (useful for
    background workers / scripts). `kwargs` interpolate via `str.format`
    — a `{name}` placeholder in the template string becomes the kwarg
    value.

    Fallback chain:
      1. `lang` dict
      2. `en` dict
      3. the raw key (so misses are visible in the UI)
    """
    resolved_lang = lang or _current_ui_language.get() or DEFAULT_LANGUAGE
    template = (
        TRANSLATIONS.get(resolved_lang, {}).get(key)
        or TRANSLATIONS.get(DEFAULT_LANGUAGE, {}).get(key)
        or key
    )
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            # A translator forgot a placeholder — return unformatted
            # rather than crashing the request.
            return template
    return template


# ── translations ──────────────────────────────────────────────────────
#
# Keys are dotted for grep-ability: `page.section.thing`. When adding a
# string, put the EN entry AND the ES entry in the same change. Missing
# ES entries fall back to EN silently, which is fine during transition
# but hides accidental gaps — grep `translate\(['\"]` regularly.
#
# Seeded with the ~30 core strings for PR 1. UI translation passes
# (PR 4, PR 7) grow this table as templates get wrapped.

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Navigation (top + mobile bottom nav)
        "nav.jobs": "Jobs",
        "nav.journey": "Journey",
        "nav.profile": "Profile",
        "nav.back_to_search": "Back to search",
        # Common actions
        "action.save": "Save",
        "action.cancel": "Cancel",
        "action.refresh": "Refresh",
        "action.dismiss": "Dismiss",
        "action.undo": "Undo",
        "action.expand_search": "Expand search",
        "action.run_search": "Run search",
        "action.run_n_searches": "Run {n} searches",
        "action.tailor": "Tailor",
        "action.open_posting": "Open posting",
        "action.show_description": "Show description",
        "action.apply_on": "Apply on {company}",
        # Jobs page — top-level copy
        "jobs.title": "Jobs",
        "jobs.subtitle": "Search job boards, see AI-scored matches with reasoning, curate what to apply to.",
        "jobs.tab.broad": "Broad",
        "jobs.tab.broad_full": "Broad search",
        "jobs.tab.individual": "Individual",
        "jobs.tab.individual_full": "Individual Job Review",
        "jobs.form.add_another": "+ Add another job ({n}/3)",
        "jobs.form.location_placeholder": "City, region, country",
        "jobs.form.job_placeholder_first": "Job title (e.g. Revit specialist)",
        "jobs.form.job_placeholder_more": "Another job title (e.g. BIM Modeler)",
        # Filters
        "filters.min_score": "Min score",
        "filters.hide_french": "Hide French job postings",
        "filters.only_new": "Only new",
        "filters.hide_viewed": "Hide viewed",
        "filters.hide_dismissed": "Hide dismissed",
        "filters.remote": "Remote",
        "filters.remote.any": "Any",
        "filters.remote.remote": "Remote only",
        "filters.remote.onsite": "On-site only",
        # Chips shown on job cards
        "chip.new": "New",
        "chip.fresh": "Fresh",
        "chip.viewed": "Viewed",
        "chip.dismissed": "Dismissed",
        "chip.remote": "Remote",
        # Toasts
        "toast.saved_as_interested": "Saved as interested",
        "toast.dismissed": "Dismissed",
        "toast.could_not_save": "Couldn't save — try again",
        "toast.could_not_dismiss": "Couldn't dismiss — try again",
        "toast.undo_failed": "Undo failed — try again",
        # Profile — settings block
        "profile.settings.ui_language": "Interface language",
        "profile.settings.output_language": "Language for generated resumes & cover letters",
        "profile.settings.home_country": "Home country",
        "profile.settings.home_city": "Home city",
    },
    "es": {
        # Navegación
        "nav.jobs": "Empleos",
        "nav.journey": "Trayecto",
        "nav.profile": "Perfil",
        "nav.back_to_search": "Volver a la búsqueda",
        # Acciones comunes
        "action.save": "Guardar",
        "action.cancel": "Cancelar",
        "action.refresh": "Actualizar",
        "action.dismiss": "Descartar",
        "action.undo": "Deshacer",
        "action.expand_search": "Ampliar búsqueda",
        "action.run_search": "Buscar",
        "action.run_n_searches": "Ejecutar {n} búsquedas",
        "action.tailor": "Personalizar",
        "action.open_posting": "Ver oferta",
        "action.show_description": "Ver descripción",
        "action.apply_on": "Aplicar en {company}",
        # Página de empleos
        "jobs.title": "Empleos",
        "jobs.subtitle": "Busca ofertas, revisa coincidencias puntuadas por IA con reasoning, y decide a cuáles postular.",
        "jobs.tab.broad": "Amplia",
        "jobs.tab.broad_full": "Búsqueda amplia",
        "jobs.tab.individual": "Individual",
        "jobs.tab.individual_full": "Revisión de oferta puntual",
        "jobs.form.add_another": "+ Agregar otro puesto ({n}/3)",
        "jobs.form.location_placeholder": "Ciudad, región, país",
        "jobs.form.job_placeholder_first": "Puesto (ej. Especialista en Revit)",
        "jobs.form.job_placeholder_more": "Otro puesto (ej. Modelador BIM)",
        # Filtros
        "filters.min_score": "Puntaje mínimo",
        "filters.hide_french": "Ocultar ofertas en francés",
        "filters.only_new": "Solo nuevas",
        "filters.hide_viewed": "Ocultar vistas",
        "filters.hide_dismissed": "Ocultar descartadas",
        "filters.remote": "Remoto",
        "filters.remote.any": "Cualquiera",
        "filters.remote.remote": "Solo remoto",
        "filters.remote.onsite": "Solo presencial",
        # Etiquetas de tarjeta
        "chip.new": "Nueva",
        "chip.fresh": "Reciente",
        "chip.viewed": "Vista",
        "chip.dismissed": "Descartada",
        "chip.remote": "Remoto",
        # Notificaciones
        "toast.saved_as_interested": "Guardada como interesante",
        "toast.dismissed": "Descartada",
        "toast.could_not_save": "No se pudo guardar — intenta de nuevo",
        "toast.could_not_dismiss": "No se pudo descartar — intenta de nuevo",
        "toast.undo_failed": "No se pudo deshacer — intenta de nuevo",
        # Perfil
        "profile.settings.ui_language": "Idioma de la interfaz",
        "profile.settings.output_language": "Idioma para currículums y cartas generadas",
        "profile.settings.home_country": "País",
        "profile.settings.home_city": "Ciudad",
    },
}
