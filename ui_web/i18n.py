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
        "action.mark_applied": "Mark as Applied",
        "action.applied": "Applied",
        "action.click_to_unmark": "Click to unmark",
        "action.view_in_applied": "View in applied jobs",
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
        "jobs.form.job_placeholder_first_generic": "Job title",
        "jobs.form.job_placeholder_first_personal": "Job title (e.g. {role})",
        "jobs.form.job_placeholder_more": "Another job title (e.g. BIM Modeler)",
        # Loading stages (longOp overlay text) — broad search / multi-run / URL import
        "jobs.stages.search.starting": "Starting the search…",
        "jobs.stages.search.linkedin": "Scanning LinkedIn postings…",
        "jobs.stages.search.indeed": "Checking Indeed board…",
        "jobs.stages.search.google": "Sweeping Google for Jobs…",
        "jobs.stages.search.descriptions": "Reading full job descriptions…",
        "jobs.stages.search.dedup": "Deduplicating across sources…",
        "jobs.stages.search.still_working": "Still working (this is longer than usual)",
        "jobs.stages.multi.first": "Running the first search…",
        "jobs.stages.multi.cool1": "Cooling down before the next…",
        "jobs.stages.multi.second": "Running the second search…",
        "jobs.stages.multi.cool2": "Cooling down before the last…",
        "jobs.stages.multi.third": "Running the last search…",
        "jobs.stages.multi.organizing": "Almost done — organizing results…",
        "jobs.stages.multi.still_working": "Still working (multi runs can take up to 3 min)",
        "jobs.stages.url.fetching": "Fetching the page…",
        "jobs.stages.url.extracting": "Extracting job details from the layout…",
        "jobs.stages.url.scoring": "Scoring against your resume…",
        "jobs.stages.url.still_working": "Still working — some sites take a bit",
        # Tailor drawer + tailor flow — the whole "Personalizando a la vacante" surface
        "tailor.drawer.label": "Tailor resume",
        "tailor.drawer.title": "Ready when you are",
        "tailor.drawer.empty": "Pick a job to tailor for.",
        "action.close": "Close",
        "tailor.for_this_role": "For this role",
        "tailor.score_disclaimer": "The AI fit score is a guide to help you prioritise — a highlight, not a final decision. AI scoring isn't fully deterministic and can vary slightly; use your own judgement on whether to apply.",
        "tailor.setup.title": "Setup needed:",
        "tailor.setup.upload_resume": "Upload a resume on the <a href=\"/profile\" class=\"underline\">Profile</a> tab.",
        "tailor.setup.add_key": "Add <code class=\"text-xs bg-base-200 px-1 rounded\">GOOGLE_API_KEY</code> on the <a href=\"/profile\" class=\"underline\">Profile</a> tab.",
        "tailor.runs.title": "Runs for this job",
        "tailor.runs.separator": "or generate a new one below",
        "tailor.level.label": "Tailoring level",
        "tailor.level.conservative.label": "Conservative",
        "tailor.level.conservative.desc": "Light edits. Never adds skills.",
        "tailor.level.balanced.label": "Balanced",
        "tailor.level.balanced.desc": "Real tailoring. Drops irrelevant bullets.",
        "tailor.level.aggressive.label": "Aggressive",
        "tailor.level.aggressive.desc": "Max keyword alignment using JD vocab.",
        "tailor.action.generate_new": "Generate a new version",
        "tailor.action.generate_first": "Generate tailored resume + cover letter",
        "tailor.action.generating": "Generating…",
        "tailor.action.save_interested": "Save as interested",
        "tailor.action.mark_applied": "Mark applied",
        "tailor.action.download_resume": "Resume DOCX",
        "tailor.action.download_cover": "Cover letter DOCX",
        "tailor.stages.reading": "Reading your resume…",
        "tailor.stages.analyzing": "Analyzing the job requirements…",
        "tailor.stages.bullets": "Writing tailored bullets…",
        "tailor.stages.cover_letter": "Drafting the cover letter…",
        "tailor.stages.polishing": "Almost there — polishing…",
        "tailor.stages.still_working": "Model is thinking hard — up to 3 min on Aggressive",
        "tailor.fallback.title": "We kept your resume as-is",
        "tailor.fallback.body": "Your original resume already scores well for this role — the {level} pass didn't improve it, so we're skipping the rewrite. Your cover letter below <em>is</em> tailored to this specific posting.",
        "tailor.fallback.try_aggressive": "Try Aggressive instead",
        "tailor.fallback.downloads_note": "Downloads still work — you get the original DOCX + the tailored cover letter.",
        "tailor.ribbon.moved_up": "Moved up a tier",
        "tailor.meta.pts": "pts",
        "tailor.meta.from_score": "from {score}",
        "tailor.meta.level_tailoring": "<strong>{level}</strong> tailoring",
        "tailor.meta.modified_tooltip": "How much of your resume text differs from the original — a rough guide for fact-checking effort",
        "tailor.meta.resume_modified": "Resume modified <strong>{pct}%</strong>",
        "tailor.insight.jumped": "{level} tailoring moved this from {before} to {after} — worth applying.",
        "tailor.result.resume_title": "Tailored resume",
        "tailor.result.resume_preview_note": "preview — full DOCX below",
        "tailor.result.cover_letter_title": "Cover letter",
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
        # Friendly date label for LinkedIn jobs with no date_posted
        "jobs.date_recent": "≤24h",
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
        "profile.settings.city_placeholder": "City, Country (e.g. Bogotá, Colombia)",
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
        # Score card / detail — chip section headers
        "jobs.matched": "Matched",
        "jobs.gaps": "Gaps",
        "jobs.gaps_flagged": "Gaps flagged",
        # Filters
        "filters.only_new.tooltip": "Only recently added jobs (last 48 h) or new since your last Expand",
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
        "results.pane.list": "Job list",
        "results.pane.detail": "Job detail",
        "results.still_finding": "Still finding more jobs · showing what we have so far",
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
        "profile.ats.excellent": "Excellent",
        "profile.ats.good": "Good",
        "profile.ats.almost_there": "Almost there",
        "profile.ats.poor": "Poor",
        # Legacy 3-tier labels, retained for backward compatibility.
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
        "feedback.label": "Feedback",
        "feedback.title": "Something not working?",
        "feedback.subtitle": "Tell us what you saw. We read every message.",
        "feedback.placeholder": "What's confusing, broken, or missing?",
        "feedback.attach_image": "Attach a screenshot (image, up to 2 MB)",
        "feedback.remove_image": "Remove",
        "feedback.send": "Send",
        "feedback.error_server": "Could not send — please try again in a moment.",
        "feedback.error_network": "Network error — check your connection.",
        # Journey page (was hard-coded EN, i18n'd in the "truth pass" PR)
        "journey.page_title": "Journey — Jobot",
        "journey.rail.aria": "Section navigation",
        "journey.rail.week": "Your week",
        "journey.rail.applications": "Applications",
        "journey.rail.insights": "Insights",
        "journey.title": "Journey",
        "journey.subtitle": "Your job-hunt so far.",
        "journey.empty.title": "Your journey starts here",
        "journey.empty.body": "As you search, tailor, and track applications, this page fills in with your rhythm — the numbers that matter, when you tend to work, and what the data starts telling us.",
        "journey.empty.hint": "Come back after a few sessions.",
        "journey.week.title": "This week",
        "journey.week.subtitle": "the last 7 days",
        "journey.week.jobs_viewed": "Jobs viewed",
        "journey.week.tailored": "Tailored resumes",
        "journey.week.applied": "Applied",
        "journey.week.streak": "{n}-day streak",
        "journey.week.most_active_dow": "You show up most on <strong class=\"text-base-content/85\">{day}s</strong>",
        "journey.apps.title": "Applications — this month",
        "journey.apps.stats_subtitle": "how many jobs made it to each step",
        "journey.apps.kanban_subtitle": "your active pipeline — click a card to tailor, use Move to shift status",
        "journey.apps.aria_view_mode": "Funnel view mode",
        "journey.apps.tab_stats": "Stats",
        "journey.apps.tab_kanban": "Kanban",
        "journey.funnel.viewed": "Viewed",
        "journey.funnel.saved": "Saved",
        "journey.funnel.applied": "Applied",
        "journey.funnel.interviewing": "Interviewing",
        "journey.funnel.offer": "Offer",
        "journey.funnel.moved_to_next": "{pct}% moved to next",
        "journey.kanban.empty_title": "No applications yet.",
        "journey.kanban.empty_body": "Save a job from the <a href=\"/jobs\" class=\"link\">Jobs tab</a> and it lands here.",
        "journey.kanban.column_empty": "nothing here yet",
        "journey.kanban.closed_summary": "Closed applications ({n})",
        "journey.insights.what_we_noticed": "What we noticed",
        "journey.insights.not_enough_yet": "Not enough activity yet to spot patterns. Keep at it and this fills in.",
        "journey.insights.prep_time_title": "How long you usually take to prep a job",
        "journey.insights.min": "min",
        "journey.insights.prep_time_caption": "From opening a job to downloading the tailored resume.",
        "journey.events_tracked_total": "events tracked total.",
        # Profile — reworded stats + status strings (was hard-coded EN)
        "profile.resume.stats_1page": "{words} words · 1 page",
        "profile.resume.stats_npages": "{words} words · {pages} pages",
        "profile.resume.looks_clean": "Resume looks clean.",
        "profile.resume.reparsed_toast": "Resume re-parsed cleanly",
        # Profile Notifications tab (was hard-coded EN)
        "profile.notif.title": "Browser notifications",
        "profile.notif.explainer": "Get a system alert when long tasks (bulk runs, tailoring) finish and you're on another tab. Tab title + in-app toast always work — this is the OS-level layer.",
        "profile.notif.unsupported": "Not supported in this browser",
        "profile.notif.blocked": "Blocked",
        "profile.notif.blocked_help": "You (or your browser) blocked notifications for this site. Re-enable via the lock icon in the address bar.",
        "profile.notif.enabled": "Enabled",
        "profile.notif.turn_off": "Turn off",
        "profile.notif.enable": "Enable notifications",
        "profile.notif.enabled_toast": "Notifications enabled",
        "profile.notif.disabled_toast": "Notifications disabled",
        "profile.notif.permission_denied_toast": "Permission denied",
        # Danger zone (data destruction) — moved from Journey per user request
        "profile.danger.title": "Danger zone",
        "profile.danger.subtitle": "Destructive actions. Both require typing a confirmation phrase — server rejects anything else.",
        "profile.danger.reset_stats": "Reset stats",
        "profile.danger.delete_all": "Delete all my data",
        "profile.danger.reset_stats.explainer": "Wipes your activity history (events on the Journey page). Your resume, applications, and settings are preserved.",
        "profile.danger.delete_all.explainer": "Permanently deletes your resume, applications, job scores, events, saved searches — everything. This cannot be undone. Language settings are kept so the app boots in the same language.",
        "profile.danger.type_to_confirm": "Type <strong>{phrase}</strong> to confirm.",
        "profile.danger.confirm_reset": "Reset stats",
        "profile.danger.confirm_delete": "Yes, delete everything",
        # Onboarding wizard
        "onboarding.wizard.title": "Welcome to Jobot",
        "onboarding.wizard.subtitle": "Three quick things before you start.",
        "onboarding.wizard.step.language": "Language",
        "onboarding.wizard.step.resume": "Resume",
        "onboarding.wizard.step.location": "Location",
        "onboarding.wizard.location.title": "Where are you searching from?",
        "onboarding.wizard.location.subtitle": "We default every search to your city — without this every search hits Ottawa, Canada.",
        "onboarding.wizard.location.done": "Done",
        "onboarding.wizard.lang.title": "How should Jobot talk to you?",
        "onboarding.wizard.lang.subtitle": "Pick the interface language and the language for generated resumes and cover letters.",
        "onboarding.wizard.resume.title": "Upload your resume",
        "onboarding.wizard.resume.subtitle": "We use it to score job matches and tailor applications. PDF or DOCX.",
        "onboarding.wizard.resume.uploading": "Uploading…",
        "onboarding.wizard.resume.uploaded": "Resume uploaded",
        "onboarding.wizard.resume.error": "Could not upload — try again.",
        "onboarding.wizard.next": "Next",
        "onboarding.wizard.finish": "Let's go",
        "onboarding.wizard.skip": "Skip for now",
        # Driver.js tour
        "tour.step.jobs.title": "Search for jobs",
        "tour.step.jobs.body": "Enter a job title and location, run a search. Jobot scores every result against your resume.",
        "tour.step.journey.title": "Track your applications",
        "tour.step.journey.body": "Save interesting jobs and follow them all the way to offer.",
        "tour.step.settings.title": "Settings",
        "tour.step.settings.body": "Change language, location, and notifications here. You can also replay this tour any time.",
        "tour.done": "Got it",
        # Settings panel — tour re-trigger
        "settings.tour.button": "Take the app tour",
        # What's new bell
        "whats_new.title": "What's new",
        "whats_new.body": "Setup wizard, app tour, and a 'what's new' bell — onboarding shipped.",
        "whats_new.close": "Got it",
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
        "action.mark_applied": "Marcar como postulado",
        "action.applied": "Postulado",
        "action.click_to_unmark": "Haz clic para desmarcar",
        "action.view_in_applied": "Ver en postulaciones",
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
        "jobs.form.job_placeholder_first_generic": "Puesto",
        "jobs.form.job_placeholder_first_personal": "Puesto (ej. {role})",
        "jobs.form.job_placeholder_more": "Otro puesto (ej. Modelador BIM)",
        # Etapas de carga (texto del overlay longOp) — búsqueda / múltiple / URL
        "jobs.stages.search.starting": "Iniciando la búsqueda…",
        "jobs.stages.search.linkedin": "Explorando ofertas en LinkedIn…",
        "jobs.stages.search.indeed": "Revisando el tablón de Indeed…",
        "jobs.stages.search.google": "Rastreando Google Empleos…",
        "jobs.stages.search.descriptions": "Leyendo descripciones completas…",
        "jobs.stages.search.dedup": "Eliminando duplicados entre fuentes…",
        "jobs.stages.search.still_working": "Sigue trabajando (esto tarda más de lo habitual)",
        "jobs.stages.multi.first": "Ejecutando la primera búsqueda…",
        "jobs.stages.multi.cool1": "Enfriando antes de la siguiente…",
        "jobs.stages.multi.second": "Ejecutando la segunda búsqueda…",
        "jobs.stages.multi.cool2": "Enfriando antes de la última…",
        "jobs.stages.multi.third": "Ejecutando la última búsqueda…",
        "jobs.stages.multi.organizing": "Casi listo — organizando resultados…",
        "jobs.stages.multi.still_working": "Sigue trabajando (varias búsquedas pueden tardar hasta 3 min)",
        "jobs.stages.url.fetching": "Cargando la página…",
        "jobs.stages.url.extracting": "Extrayendo datos de la oferta…",
        "jobs.stages.url.scoring": "Puntuando contra tu currículum…",
        "jobs.stages.url.still_working": "Sigue trabajando — algunos sitios tardan más",
        # Panel Personalizar (tailor) — la vista completa de "Personalizando a la vacante"
        "tailor.drawer.label": "Personalizar currículum",
        "tailor.drawer.title": "Cuando quieras, empezamos",
        "tailor.drawer.empty": "Elige una oferta para personalizar.",
        "action.close": "Cerrar",
        "tailor.for_this_role": "Para esta oferta",
        "tailor.score_disclaimer": "La puntuación de afinidad con IA es una guía para ayudarte a priorizar — un apoyo, no la decisión final. El puntaje con IA no es totalmente determinista y puede variar un poco; usa tu criterio para decidir si aplicar.",
        "tailor.setup.title": "Falta configurar:",
        "tailor.setup.upload_resume": "Sube un currículum en la pestaña <a href=\"/profile\" class=\"underline\">Perfil</a>.",
        "tailor.setup.add_key": "Agrega <code class=\"text-xs bg-base-200 px-1 rounded\">GOOGLE_API_KEY</code> en la pestaña <a href=\"/profile\" class=\"underline\">Perfil</a>.",
        "tailor.runs.title": "Versiones para esta oferta",
        "tailor.runs.separator": "o genera una nueva abajo",
        "tailor.level.label": "Nivel de personalización",
        "tailor.level.conservative.label": "Conservador",
        "tailor.level.conservative.desc": "Ediciones ligeras. No agrega skills.",
        "tailor.level.balanced.label": "Equilibrado",
        "tailor.level.balanced.desc": "Personalización real. Quita bullets irrelevantes.",
        "tailor.level.aggressive.label": "Agresivo",
        "tailor.level.aggressive.desc": "Máxima alineación con vocabulario de la oferta.",
        "tailor.action.generate_new": "Generar otra versión",
        "tailor.action.generate_first": "Generar currículum + carta de presentación",
        "tailor.action.generating": "Generando…",
        "tailor.action.save_interested": "Guardar como interesante",
        "tailor.action.mark_applied": "Marcar como postulado",
        "tailor.action.download_resume": "Currículum DOCX",
        "tailor.action.download_cover": "Carta de presentación DOCX",
        "tailor.stages.reading": "Leyendo tu currículum…",
        "tailor.stages.analyzing": "Analizando los requisitos de la oferta…",
        "tailor.stages.bullets": "Escribiendo bullets personalizados…",
        "tailor.stages.cover_letter": "Redactando la carta de presentación…",
        "tailor.stages.polishing": "Casi listo — puliendo…",
        "tailor.stages.still_working": "El modelo está trabajando fuerte — hasta 3 min en Agresivo",
        "tailor.fallback.title": "Mantuvimos tu currículum tal cual",
        "tailor.fallback.body": "Tu currículum original ya puntúa bien para esta oferta — la pasada {level} no lo mejoró, así que saltamos la reescritura. La carta de presentación de abajo <em>sí</em> está personalizada para esta oferta específica.",
        "tailor.fallback.try_aggressive": "Probar Agresivo",
        "tailor.fallback.downloads_note": "Las descargas siguen funcionando — recibes el DOCX original + la carta personalizada.",
        "tailor.ribbon.moved_up": "Subió un tier",
        "tailor.meta.pts": "pts",
        "tailor.meta.from_score": "desde {score}",
        "tailor.meta.level_tailoring": "Personalización <strong>{level}</strong>",
        "tailor.meta.modified_tooltip": "Cuánto se aleja el texto del original — una guía para tu esfuerzo de verificación",
        "tailor.meta.resume_modified": "Currículum modificado <strong>{pct}%</strong>",
        "tailor.insight.jumped": "La personalización {level} movió esto de {before} a {after} — vale la pena postularse.",
        "tailor.result.resume_title": "Currículum personalizado",
        "tailor.result.resume_preview_note": "vista previa — DOCX completo abajo",
        "tailor.result.cover_letter_title": "Carta de presentación",
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
        # Etiqueta amigable para LinkedIn sin fecha de publicación
        "jobs.date_recent": "hoy",
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
        "profile.settings.city_placeholder": "Ciudad, país (ej. Bogotá, Colombia)",
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
        # Score card / detail — chip section headers
        "jobs.matched": "Coincide",
        "jobs.gaps": "Brechas",
        "jobs.gaps_flagged": "Brechas señaladas",
        # Filtros
        "filters.only_new.tooltip": "Solo empleos añadidos recientemente (últimas 48 h) o nuevos desde tu última Ampliación",
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
        "results.pane.list": "Lista de empleos",
        "results.pane.detail": "Detalle del empleo",
        "results.still_finding": "Seguimos buscando más empleos · mostrando lo que tenemos por ahora",
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
        "profile.ats.excellent": "Excelente",
        "profile.ats.good": "Bueno",
        "profile.ats.almost_there": "Casi listo",
        "profile.ats.poor": "Bajo",
        # Legacy 3-tier labels
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
        "feedback.label": "Comentarios",
        "feedback.title": "¿Algo no funciona?",
        "feedback.subtitle": "Cuéntanos qué viste. Leemos cada mensaje.",
        "feedback.placeholder": "¿Qué está confuso, roto o falta?",
        "feedback.attach_image": "Adjuntar captura (imagen, hasta 2 MB)",
        "feedback.remove_image": "Quitar",
        "feedback.send": "Enviar",
        "feedback.error_server": "No pudimos enviarlo — intenta de nuevo en un momento.",
        "feedback.error_network": "Error de red — revisa tu conexión.",
        # Trayecto (Journey) — sweep 2026-08-20, registro LatAm
        "journey.page_title": "Trayecto — Jobot",
        "journey.rail.aria": "Navegación de secciones",
        "journey.rail.week": "Tu semana",
        "journey.rail.applications": "Postulaciones",
        "journey.rail.insights": "Observaciones",
        "journey.title": "Trayecto",
        "journey.subtitle": "Tu búsqueda de empleo hasta hoy.",
        "journey.empty.title": "Tu trayecto empieza aquí",
        "journey.empty.body": "A medida que buscas, ajustas y postulas, esta página se va llenando con tu ritmo — los números que importan, cuándo acostumbras trabajar y lo que los datos empiezan a mostrar.",
        "journey.empty.hint": "Vuelve después de unas cuantas sesiones.",
        "journey.week.title": "Esta semana",
        "journey.week.subtitle": "los últimos 7 días",
        "journey.week.jobs_viewed": "Empleos vistos",
        "journey.week.tailored": "Currículums ajustados",
        "journey.week.applied": "Postulaciones enviadas",
        "journey.week.streak": "Racha de {n} días",
        "journey.week.most_active_dow": "Sueles moverte más los <strong class=\"text-base-content/85\">{day}</strong>",
        "journey.apps.title": "Postulaciones — este mes",
        "journey.apps.stats_subtitle": "cuántos empleos llegaron a cada etapa",
        "journey.apps.kanban_subtitle": "tu pipeline activo — haz clic en una tarjeta para ajustar, usa Mover para cambiar de estado",
        "journey.apps.aria_view_mode": "Modo de vista del embudo",
        "journey.apps.tab_stats": "Estadísticas",
        "journey.apps.tab_kanban": "Kanban",
        "journey.funnel.viewed": "Vistos",
        "journey.funnel.saved": "Guardados",
        "journey.funnel.applied": "Postulados",
        "journey.funnel.interviewing": "Entrevistando",
        "journey.funnel.offer": "Oferta",
        "journey.funnel.moved_to_next": "{pct}% pasó al siguiente",
        "journey.kanban.empty_title": "Aún no hay postulaciones.",
        "journey.kanban.empty_body": "Guarda un empleo desde la <a href=\"/jobs\" class=\"link\">pestaña de Empleos</a> y aparecerá aquí.",
        "journey.kanban.column_empty": "nada por aquí todavía",
        "journey.kanban.closed_summary": "Postulaciones cerradas ({n})",
        "journey.insights.what_we_noticed": "Lo que notamos",
        "journey.insights.not_enough_yet": "Aún no hay suficiente actividad para detectar patrones. Sigue así y esto se llena.",
        "journey.insights.prep_time_title": "Cuánto sueles tardar en preparar una postulación",
        "journey.insights.min": "min",
        "journey.insights.prep_time_caption": "Desde que abres un empleo hasta que descargas el currículum ajustado.",
        "journey.events_tracked_total": "eventos registrados en total.",
        # Perfil — cifras y estados (barrido de strings)
        "profile.resume.stats_1page": "{words} palabras · 1 página",
        "profile.resume.stats_npages": "{words} palabras · {pages} páginas",
        "profile.resume.looks_clean": "El currículum se ve limpio.",
        "profile.resume.reparsed_toast": "Currículum re-analizado sin problemas",
        # Perfil — pestaña de Notificaciones
        "profile.notif.title": "Notificaciones del navegador",
        "profile.notif.explainer": "Recibe una alerta del sistema cuando terminen las tareas largas (búsquedas masivas, ajustes de currículum) y estés en otra pestaña. El título de la pestaña y los avisos internos siempre funcionan — esto es la capa a nivel del sistema operativo.",
        "profile.notif.unsupported": "No compatible con este navegador",
        "profile.notif.blocked": "Bloqueadas",
        "profile.notif.blocked_help": "Tú (o tu navegador) bloqueaste las notificaciones para este sitio. Vuelve a habilitarlas desde el ícono de candado en la barra de direcciones.",
        "profile.notif.enabled": "Activadas",
        "profile.notif.turn_off": "Desactivar",
        "profile.notif.enable": "Activar notificaciones",
        "profile.notif.enabled_toast": "Notificaciones activadas",
        "profile.notif.disabled_toast": "Notificaciones desactivadas",
        "profile.notif.permission_denied_toast": "Permiso denegado",
        # Zona peligrosa (borrar datos)
        "profile.danger.title": "Zona peligrosa",
        "profile.danger.subtitle": "Acciones destructivas. Ambas piden que escribas una frase de confirmación — el servidor rechaza cualquier otra cosa.",
        "profile.danger.reset_stats": "Reiniciar estadísticas",
        "profile.danger.delete_all": "Borrar todos mis datos",
        "profile.danger.reset_stats.explainer": "Borra tu historial de actividad (los eventos de la página Trayecto). Tu currículum, postulaciones y ajustes se mantienen.",
        "profile.danger.delete_all.explainer": "Borra permanentemente tu currículum, postulaciones, puntajes, eventos, búsquedas guardadas — todo. No se puede deshacer. Los ajustes de idioma se mantienen para que la app arranque en el mismo idioma.",
        "profile.danger.type_to_confirm": "Escribe <strong>{phrase}</strong> para confirmar.",
        "profile.danger.confirm_reset": "Reiniciar",
        "profile.danger.confirm_delete": "Sí, borrar todo",
        # Asistente de configuración inicial
        "onboarding.wizard.title": "Bienvenido a Jobot",
        "onboarding.wizard.subtitle": "Tres cosas rápidas antes de empezar.",
        "onboarding.wizard.step.language": "Idioma",
        "onboarding.wizard.step.resume": "Currículum",
        "onboarding.wizard.step.location": "Ubicación",
        "onboarding.wizard.location.title": "¿Desde dónde buscas empleo?",
        "onboarding.wizard.location.subtitle": "Usamos tu ciudad para hacer las búsquedas en la región correcta — sin esto usamos Ottawa, Canadá.",
        "onboarding.wizard.location.done": "Listo",
        "onboarding.wizard.lang.title": "¿En qué idioma quieres que te hable Jobot?",
        "onboarding.wizard.lang.subtitle": "Elige el idioma de la interfaz y el idioma para currículums y cartas generadas.",
        "onboarding.wizard.resume.title": "Sube tu currículum",
        "onboarding.wizard.resume.subtitle": "Lo usamos para puntuar las ofertas y personalizar postulaciones. PDF o DOCX.",
        "onboarding.wizard.resume.uploading": "Subiendo…",
        "onboarding.wizard.resume.uploaded": "Currículum subido",
        "onboarding.wizard.resume.error": "No se pudo subir — intenta de nuevo.",
        "onboarding.wizard.next": "Siguiente",
        "onboarding.wizard.finish": "Empecemos",
        "onboarding.wizard.skip": "Omitir por ahora",
        # Tour guiado
        "tour.step.jobs.title": "Busca empleos",
        "tour.step.jobs.body": "Ingresa un puesto y ciudad, ejecuta la búsqueda. Jobot puntúa cada resultado contra tu currículum.",
        "tour.step.journey.title": "Sigue tus postulaciones",
        "tour.step.journey.body": "Guarda empleos interesantes y síguelos hasta la oferta.",
        "tour.step.settings.title": "Ajustes",
        "tour.step.settings.body": "Cambia idioma, ubicación y notificaciones aquí. También puedes repetir este tour cuando quieras.",
        "tour.done": "Entendido",
        # Panel de ajustes — repetir tour
        "settings.tour.button": "Recorrer la app",
        # Campana de novedades
        "whats_new.title": "Novedades",
        "whats_new.body": "Asistente de configuración, tour de la app y campana de novedades — onboarding listo.",
        "whats_new.close": "Entendido",
    },
}
