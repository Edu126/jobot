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
        "action.view_on": "View on {site}",
        # Jobs page — top-level copy
        "jobs.title": "Jobs",
        "jobs.subtitle": "Search job boards, see AI-scored matches with reasoning, curate what to apply to.",
        "jobs.tab.broad": "Broad",
        "jobs.tab.broad_full": "Broad search",
        "jobs.tab.individual": "Individual",
        "jobs.tab.individual_full": "Individual Job Review",
        "jobs.form.add_another": "+ Add another job ({n}/3)",
        "jobs.form.add_another_short": "Add another job",
        "action.analyze": "Analyze",
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
        "profile.tab.language": "Language",
        "profile.tab.notifications": "Notifications",
        "profile.settings.ui_language": "Interface language",
        "profile.settings.output_language": "Language for generated resumes & cover letters",
        "profile.settings.output_language.hint": "Applies to tailored resumes and cover letters. You can keep your resume in one language and generate output in another.",
        "profile.settings.home_country": "Home country",
        "profile.settings.home_city": "Home city",
        "profile.settings.home_location": "Home location",
        "profile.settings.no_location": "Not set — every search defaults to Ottawa, Canada.",
        "profile.settings.no_city": "City not set",
        "profile.settings.city_placeholder": "City (e.g. Bogotá, Madrid, Toronto)",
        # Common actions
        "action.change": "Change",
        "action.view": "View →",
        # Geography first-visit banner
        "geo.banner.title": "Where are you searching from?",
        "geo.banner.subtitle": "Tell us your home country and city so we default your searches to the right region — otherwise we assume Ottawa, Canada.",
        "geo.banner.country_placeholder": "Country…",
        "geo.banner.subtitle_short": "Set your home country + city so searches default to the right region.",
        # Nav additions
        "nav.settings": "Settings",
        # Actions / states
        "action.show": "show",
        "action.show_all": "show all",
        "action.show_more": "Show {n} more",
        "action.show_less": "Show less",
        "action.reset": "Reset",
        "action.reset_filters": "Reset filters",
        "action.expand_search.tooltip": "Deeper scrape on this same query. Opens in a new tab with only fresh / unviewed jobs by default.",
        # Jobs page — mode descriptions + quick-fill
        "jobs.mode.broad_desc": "Cast a wide net — up to 3 titles at once",
        "jobs.mode.targeted_desc": "Paste a specific job link — deep-analyze one",
        "jobs.quick_fill.label": "Quick fill:",
        "jobs.quick_fill.shuffle": "Shuffle",
        "jobs.quick_fill.no_suggestions": "No suggestions yet — upload a resume to unlock these.",
        # Jobs page — recent + top matches
        "jobs.recent.title": "Recent searches",
        "jobs.recent.cached": "{n} cached",
        "jobs.top_matches.title": "Top matches for you",
        "jobs.top_matches.curated": "curated",
        "jobs.top_matches.subtitle": "Best-scoring jobs across your {n} recent searches. Click any to see full details.",
        # Filters
        "filters.only_new.tooltip": "Only jobs first seen in the last 48 hours",
        "filters.hide_viewed.tooltip": "Hide jobs you've already spent time reading",
        "filters.hide_dismissed.tooltip": "Hide jobs you've swiped away as 'not interested'",
        "filters.added": "Added",
        "filters.added.all": "All",
        "filters.added.24h": "Last 24 h",
        "filters.added.7d": "Last 7 days",
        "filters.added.30d": "Last 30 days",
        "filters.showing": "Showing",
        "filters.matches": "matches",
        "filters.no_matches": "No matches with current filters.",
        # Results page
        "results.fresh_view": "Fresh view",
        "results.switch_to_full": "switch to full list",
        "results.new_since_expand": "{n} new since your last expand",
        "results.new_since_expand_short": "{n} new since expand",
        "results.view_just_those": "view just those",
        "results.of_visible": "of {total} visible",
        "results.ranking_rest": "ranking the rest",
        "results.unviewed_from_before": "{n} unviewed from before",
        "results.already_viewed": "{n} already viewed",
        "results.ranked": "ranked",
        "results.still_evaluating": "still evaluating",
        "results.filtered_score_60": "Filtered to score ≥ 60",
        "results.hidden": "hidden",
        "results.all_ranked_sorted": "All ranked · sorted by fit",
        "results.fetched": "Fetched",
        "results.scoring_paused": "Scoring paused until tomorrow",
        "results.upload_resume_prompt": "Upload a resume on",
        "results.add_key_prompt": "Add a Gemini key on",
        "results.models_tried_today": "Models tried today: {models}. Cached scores still visible.",
        "results.no_jobs": "No jobs in this search.",
        "results.all_hidden": "All {n} jobs hidden by current filters.",
        "results.click_prompt": "Click a job on the left to see full details here.",
        # Profile page
        "profile.title": "Profile",
        "profile.subtitle": "Your resume, scored.",
        "profile.resume.current": "Current resume",
        "profile.resume.active": "Active",
        "profile.resume.stats": "{words} words · ~{pages}p · {bullets} bullets",
        "profile.resume.uploaded": "Uploaded",
        "profile.action.view_resume": "View resume",
        "profile.action.see_report": "See report",
        "profile.action.download": "Download",
        "profile.action.replace": "Replace",
        "profile.older_versions": "{n} older versions",
        "profile.upload.new_version": "Upload a new version",
        "profile.ats.good": "Good",
        "profile.ats.needs_work": "Needs work",
        "profile.ats.serious": "Serious issues",
        "profile.contact.label": "Contact info",
        "profile.contact.title": "What recruiters will see",
        "profile.contact.missing": "Missing — add it",
        "profile.contact.name": "Name",
        "profile.contact.email": "Email",
        "profile.contact.phone": "Phone",
        "profile.contact.location": "Location",
        "profile.contact.linkedin": "LinkedIn",
        "profile.contact.edit": "Edit",
        "profile.contact.save": "Save",
        "profile.contact.cancel": "Cancel",
        "profile.contact.location_placeholder": "City, region, country",
        "profile.contact.linkedin_placeholder": "linkedin.com/in/yourname",
        # Feedback widget
        "feedback.open": "Send feedback",
        "feedback.title": "Something not working?",
        "feedback.subtitle": "Tell us what you saw. We read every message.",
        "feedback.placeholder": "What's confusing, broken, or missing?",
        "feedback.include_screenshot": "Attach a screenshot of this page",
        "feedback.screenshot_ready": "Screenshot ready.",
        "feedback.send": "Send",
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
        "action.view_on": "Ver en {site}",
        # Página de empleos
        "jobs.title": "Empleos",
        "jobs.subtitle": "Busca ofertas, revisa coincidencias puntuadas por IA con reasoning, y decide a cuáles postular.",
        "jobs.tab.broad": "Amplia",
        "jobs.tab.broad_full": "Búsqueda amplia",
        "jobs.tab.individual": "Individual",
        "jobs.tab.individual_full": "Revisión de oferta puntual",
        "jobs.form.add_another": "+ Agregar otro puesto ({n}/3)",
        "jobs.form.add_another_short": "Agregar otro puesto",
        "action.analyze": "Analizar",
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
        "profile.tab.language": "Idioma",
        "profile.tab.notifications": "Notificaciones",
        "profile.settings.ui_language": "Idioma de la interfaz",
        "profile.settings.output_language": "Idioma para currículums y cartas generadas",
        "profile.settings.output_language.hint": "Se aplica a currículums adaptados y cartas de presentación. Puedes mantener tu currículum en un idioma y generar el resultado en otro.",
        "profile.settings.home_country": "País",
        "profile.settings.home_city": "Ciudad",
        "profile.settings.home_location": "Ubicación",
        "profile.settings.no_location": "Sin definir — cada búsqueda usa Ottawa, Canadá por defecto.",
        "profile.settings.no_city": "Ciudad sin definir",
        "profile.settings.city_placeholder": "Ciudad (ej. Bogotá, Madrid, Toronto)",
        # Acciones
        "action.change": "Cambiar",
        "action.view": "Ver →",
        # Banner de bienvenida (geografía)
        "geo.banner.title": "¿Desde dónde buscas empleo?",
        "geo.banner.subtitle": "Cuéntanos tu país y ciudad para que las búsquedas usen la región correcta por defecto — de lo contrario asumimos Ottawa, Canadá.",
        "geo.banner.country_placeholder": "País…",
        "geo.banner.subtitle_short": "Define tu país y ciudad para que las búsquedas usen la región correcta.",
        # Nav extras
        "nav.settings": "Ajustes",
        # Acciones / estados
        "action.show": "mostrar",
        "action.show_all": "mostrar todos",
        "action.show_more": "Mostrar {n} más",
        "action.show_less": "Mostrar menos",
        "action.reset": "Restablecer",
        "action.reset_filters": "Restablecer filtros",
        "action.expand_search.tooltip": "Búsqueda más profunda de esta misma consulta. Abre en una pestaña nueva con solo empleos nuevos / no vistos.",
        # Modo de búsqueda + quick fill
        "jobs.mode.broad_desc": "Amplio — hasta 3 puestos a la vez",
        "jobs.mode.targeted_desc": "Pega un link específico — analízalo a fondo",
        "jobs.quick_fill.label": "Autollenar:",
        "jobs.quick_fill.shuffle": "Barajar",
        "jobs.quick_fill.no_suggestions": "Sin sugerencias todavía — sube tu currículum para desbloquearlas.",
        # Recientes + top matches
        "jobs.recent.title": "Búsquedas recientes",
        "jobs.recent.cached": "{n} en caché",
        "jobs.top_matches.title": "Mejores coincidencias para ti",
        "jobs.top_matches.curated": "seleccionadas",
        "jobs.top_matches.subtitle": "Empleos mejor puntuados entre tus {n} búsquedas recientes. Toca cualquiera para ver los detalles.",
        # Filtros
        "filters.only_new.tooltip": "Solo empleos vistos por primera vez en las últimas 48 horas",
        "filters.hide_viewed.tooltip": "Ocultar empleos que ya leíste con atención",
        "filters.hide_dismissed.tooltip": "Ocultar empleos que descartaste con swipe",
        "filters.added": "Agregadas",
        "filters.added.all": "Todas",
        "filters.added.24h": "Últimas 24 h",
        "filters.added.7d": "Últimos 7 días",
        "filters.added.30d": "Últimos 30 días",
        "filters.showing": "Mostrando",
        "filters.matches": "coincidencias",
        "filters.no_matches": "Sin coincidencias con los filtros actuales.",
        # Página de resultados
        "results.fresh_view": "Vista nueva",
        "results.switch_to_full": "ver la lista completa",
        "results.new_since_expand": "{n} nuevos desde tu última ampliación",
        "results.new_since_expand_short": "{n} nuevos desde la ampliación",
        "results.view_just_those": "ver solo esos",
        "results.of_visible": "de {total} visibles",
        "results.ranking_rest": "puntuando el resto",
        "results.unviewed_from_before": "{n} sin ver de antes",
        "results.already_viewed": "{n} ya vistos",
        "results.ranked": "puntuados",
        "results.still_evaluating": "aún evaluando",
        "results.filtered_score_60": "Filtrado a puntaje ≥ 60",
        "results.hidden": "ocultos",
        "results.all_ranked_sorted": "Todos puntuados · ordenados por afinidad",
        "results.fetched": "Obtenido",
        "results.scoring_paused": "Puntuación pausada hasta mañana",
        "results.upload_resume_prompt": "Sube tu currículum en",
        "results.add_key_prompt": "Agrega una API key de Gemini en",
        "results.models_tried_today": "Modelos usados hoy: {models}. Los puntajes en caché siguen visibles.",
        "results.no_jobs": "No hay empleos en esta búsqueda.",
        "results.all_hidden": "Los {n} empleos están ocultos por los filtros actuales.",
        "results.click_prompt": "Toca un empleo a la izquierda para ver los detalles aquí.",
        # Perfil
        "profile.title": "Perfil",
        "profile.subtitle": "Tu currículum, puntuado.",
        "profile.resume.current": "Currículum actual",
        "profile.resume.active": "Activo",
        "profile.resume.stats": "{words} palabras · ~{pages}p · {bullets} viñetas",
        "profile.resume.uploaded": "Subido",
        "profile.action.view_resume": "Ver currículum",
        "profile.action.see_report": "Ver reporte",
        "profile.action.download": "Descargar",
        "profile.action.replace": "Reemplazar",
        "profile.older_versions": "{n} versiones anteriores",
        "profile.upload.new_version": "Subir una versión nueva",
        "profile.ats.good": "Bueno",
        "profile.ats.needs_work": "Requiere trabajo",
        "profile.ats.serious": "Problemas serios",
        "profile.contact.label": "Datos de contacto",
        "profile.contact.title": "Lo que verán los reclutadores",
        "profile.contact.missing": "Faltante — agrégalo",
        "profile.contact.name": "Nombre",
        "profile.contact.email": "Correo",
        "profile.contact.phone": "Teléfono",
        "profile.contact.location": "Ubicación",
        "profile.contact.linkedin": "LinkedIn",
        "profile.contact.edit": "Editar",
        "profile.contact.save": "Guardar",
        "profile.contact.cancel": "Cancelar",
        "profile.contact.location_placeholder": "Ciudad, región, país",
        "profile.contact.linkedin_placeholder": "linkedin.com/in/tunombre",
        # Feedback widget
        "feedback.open": "Enviar comentarios",
        "feedback.title": "¿Algo no funciona?",
        "feedback.subtitle": "Cuéntanos qué viste. Leemos cada mensaje.",
        "feedback.placeholder": "¿Qué está confuso, roto o falta?",
        "feedback.include_screenshot": "Adjuntar captura de esta página",
        "feedback.screenshot_ready": "Captura lista.",
        "feedback.send": "Enviar",
    },
}
