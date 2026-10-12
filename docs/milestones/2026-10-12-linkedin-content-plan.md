# LinkedIn content plan — building Jobot in public (2026-10-12)

12 posts in 6 weeks, Tuesday + Thursday. The arc runs from the origin, to the
first numbers that didn't hold, to reversed decisions and the voice coach, and
closes with an honest open problem. No user is ever named. Before publishing,
apply README rule 4: blur user data and never show real profiles. Publish P12
once REQ-052 has results, so it ends with an "after".

Assets ready in `assets/`: voice-lab, feedback-before-1. Everything else is
marked "needs capture".

Order: P1 → P12.

---

## P1 · Origin — a tool built for one real person
**Hook:** "My first job-matching score couldn't tell that AutoCAD and 'CAD software' are the same thing."

**EN:** Someone close to me was job-hunting in architecture and construction. The first tool I built him did keyword matching: "AutoCAD" vs "CAD software" scored as a miss. Strong matches looked weak, and he stopped trusting it. So I rebuilt it as Jobot: search wide, let an AI explain *why* a job fits, and tailor the résumé for the few worth applying to. The goal is 5–10 good applications a day, not 100. I build it with an AI pair. I own the product, the users and the testing; the AI writes most of the code. I'll share what actually happens: the numbers that didn't hold up, the decisions we reversed, and what real users told us. #buildinpublic

**ES:** Alguien cercano buscaba trabajo en arquitectura y construcción. La primera herramienta que le hice comparaba palabras clave: "AutoCAD" contra "software CAD" contaba como no-match. Los buenos empleos se veían débiles y dejó de confiar en ella. La reconstruí como Jobot: buscar amplio, que una IA explique *por qué* encaja un empleo y adaptar el CV para los pocos que valen la pena. La meta son 5–10 buenas postulaciones al día, no 100. La construyo con una IA como pareja de trabajo: yo pongo el producto, los usuarios y las pruebas; la IA escribe casi todo el código. Voy a contar lo que de verdad pasa: los números que no aguantaron, las decisiones que revertimos y lo que dijeron los usuarios reales.

**Asset:** needs capture — v1 (Streamlit) and v2 side by side.

## P2 · Experiment — score 90, the recruiter rejects
**Hook:** "Our app said 90% fit. A recruiter judge said: reject."

**EN:** We built an adversarial test: generate tailored résumés, then have a strict "recruiter" model screen them. We used one real profile against 5 jobs. Jobot's fit score said 90–92. The recruiter judge rejected 14 out of 14 résumés, for concrete reasons: background in the wrong field, no evidence of a required skill, bullets that list duties with no results. Our score measured keyword coverage. The recruiter measured whether you'd get a call. Those are different questions. Caveat: the judge is the same model family, so take it with a grain of salt. Lesson: a score users trust blindly needs an adversary. #AI #buildinpublic

**ES:** Armamos una prueba adversaria: generar CVs adaptados y que un modelo "reclutador" estricto los filtrara. Usamos un perfil real contra 5 empleos. El puntaje de Jobot decía 90–92. El juez reclutador rechazó 14 de 14 CVs, por razones concretas: experiencia en otro campo, sin evidencia de una habilidad requerida, viñetas que listan tareas sin resultados. Nuestro puntaje medía cobertura de palabras clave. El reclutador medía si te llamarían. Son preguntas distintas. Ojo: el juez es de la misma familia de modelos, así que hay que tomarlo con pinzas. Lección: un puntaje en el que los usuarios confían a ciegas necesita un adversario.

**Asset:** needs capture — cropped table from `data/adversarial_eval_2026-09-14.md`, with the profile and companies anonymized.

## P3 · Temperature 0 is not deterministic
**Hook:** "Same prompt, same model, temperature 0 — different score."

**EN:** A user scored the same job three times and got three different numbers. We set temperature to 0 and measured: still ±3–10 points of drift on identical input, sometimes enough to flip the verdict band. Temperature 0 doesn't make an LLM deterministic. The fix wasn't a prompt tweak. We cache the first score per résumé-text hash, so the same input always shows the same number, and we added an honest note in the UI that scores are estimates. #LLM

**ES:** Un usuario puntuó el mismo empleo tres veces y obtuvo tres números distintos. Pusimos temperature en 0 y medimos: seguía variando ±3–10 puntos con la misma entrada, a veces lo suficiente para cambiar de banda. Temperature 0 no hace determinista a un LLM. La solución no fue retocar el prompt. Guardamos en caché el primer puntaje por hash del texto del CV, así la misma entrada siempre muestra el mismo número, y agregamos una nota honesta en la interfaz de que los puntajes son estimaciones.

**Asset:** needs capture — a simple chart of the drift across 3 runs.

## P4 · User feedback — the résumé that lost 17 jobs
**Hook:** "A user's tailored résumé came back with 5 jobs. He has 22."

**EN:** In "aggressive" mode, about 1 run in 5 quietly dropped most of a user's work history. We guessed twice: first more output tokens, then a stricter "never drop an entry" rule. We tested both on his real data and neither changed anything. The model wasn't getting cut off; it was *choosing* to summarize. The fix was a guard in code: if a section shrinks below 60% of the original, retry once, then restore it verbatim. Lesson: reproduce first. Guessed fixes feel productive and prove nothing.

**ES:** En modo "agresivo", más o menos 1 de cada 5 corridas borraba en silencio casi todo el historial laboral de un usuario. Adivinamos dos veces: primero más tokens de salida, después una regla más estricta de "nunca borres una entrada". Probamos ambas con sus datos reales y ninguna cambió nada. El modelo no se estaba cortando; estaba *eligiendo* resumir. La solución fue una guarda en el código: si una sección baja de 60% del original, reintenta una vez y después la restaura tal cual. Lección: primero reproducir. Los arreglos adivinados se sienten productivos y no prueban nada.

**Asset:** needs capture — before/after diagram (22 → 5 → 22).

## P5 · Voice lab
**Hook:** "Our AI interviewer sounded like a sales pitch."

**EN/ES:** use the drafts in `2026-10-01-voice-lab.md`, plus the closing twist: text-to-speech had faked a big pacing difference (11.5 s vs 7.6 s), while the real Live model barely had one (9.0 vs 8.1). "The lab only became honest once it tested the real model." / "El laboratorio solo fue honesto cuando probó el modelo real."

**Asset:** `assets/2026-10-01-voice-lab.png` ✅

## P6 · Honest feedback — from "Solid" to 30/100
**Hook:** "Our coach rated 'I don't care about the position' as Solid."

**EN/ES:** use the drafts in `2026-10-01-honest-session-score.md`.

**Asset:** `assets/2026-10-01-feedback-before-1.png` ✅ + needs capture — the "after" (session 39).

## P7 · Experiment — 19% → 0%, and how we nearly broke the controls
**Hook:** "We got false positives to 0%. Then our good answers started failing."

**EN:** We built a junk-answer set: 12 bad interview answers plus 3 good controls, 3 runs each. At baseline, the judge called junk "solid" 19% of the time. A band rule took that to 8%. A stricter definition of "result" got it to 0%, but 3 of 9 good answers started failing because the model began quoting the wrong sentence. One more rule, that the quote must include what *you* did, brought it to 0% junk with 9/9 controls passing. Lesson: measure both sides. Fixing false positives is easy if you don't look at what you broke.

**ES:** Armamos un set de respuestas basura: 12 respuestas malas de entrevista más 3 buenas de control, 3 corridas cada una. En la línea base, el juez llamó "sólida" a la basura el 19% de las veces. Una regla de bandas lo bajó a 8%. Una definición más estricta de "resultado" lo llevó a 0%, pero 3 de 9 buenas empezaron a fallar porque el modelo citaba la frase equivocada. Una regla más, que la cita incluya lo que *tú* hiciste, dejó 0% de basura con 9/9 controles bien. Lección: mide ambos lados. Bajar los falsos positivos es fácil si no miras lo que rompiste.

**Asset:** needs capture — the EXP-002 results table as a chart.

## P8 · Reversed decision — the rebrand
**Hook:** "AI agents built a full rebrand in an afternoon. We threw it away."

**EN:** I had parallel AI agents build a complete plum rebrand. It was fast and polished, and it was wrong: it added color fragmentation instead of reducing it. We went back to the existing green identity and changed it in small steps. What came out of it was a written rule, "subtract first": lead every redesign with what to cut, not with three styling options. Speed of generation isn't the bottleneck. Judgment is.

**ES:** Puse agentes de IA en paralelo a construir un rebrand completo en color ciruela. Fue rápido y pulido, y estaba mal: sumaba fragmentación de color en vez de reducirla. Volvimos a la identidad verde que ya teníamos y la cambiamos en pasos pequeños. De ahí salió una regla escrita, "restar primero": todo rediseño empieza por lo que se quita, no por tres opciones de estilo. La velocidad para generar no es el cuello de botella. El criterio sí.

**Asset:** needs capture — plum vs today's green (`docs/experiments/ai-accent-lab.html`).

## P9 · From avatar to wave
**Hook:** "We gave our AI coach a face. Then we took it away."

**EN:** First the coach was an orb, then a floating 3D head driven by real audio. It didn't feel right: too "AI". So we built a lab with four voice-only visuals and picked a simple wave that moves with whoever is talking. No face, no lip-sync. It's calmer, and it fits a calm interviewer. Sometimes the right feature is less of it.

**ES:** Primero el coach fue un orbe, después una cabeza 3D flotante movida por el audio real. No se sentía bien: demasiado "IA". Armamos un laboratorio con cuatro visuales solo de voz y elegimos una onda simple que se mueve con quien habla. Sin cara, sin lip-sync. Es más calmado y encaja con un entrevistador tranquilo. A veces la función correcta es tener menos de ella.

**Asset:** needs capture — the 4 visuals from `/lab/avatar` + a GIF of the wave.

## P10 · Measure what you can see
**Hook:** "We were tracking 'applications' — a thing we could never see."

**EN:** Our dashboard showed 0 responses out of 14 applications. That number was fake: people apply on the company's site, outside our app. So we changed the final metric to the last thing we actually see someone do, which is downloading a tailored résumé. That signal separates real effort: one person had downloaded 64 of 70 tailored résumés, another 1 of 8. Don't build a funnel that ends in a number you can't observe.

**ES:** Nuestro tablero mostraba 0 respuestas de 14 postulaciones. Ese número era falso: la gente postula en el sitio de la empresa, fuera de nuestra app. Así que cambiamos la métrica final por lo último que realmente vemos hacer a alguien: descargar un CV adaptado. Esa señal separa el esfuerzo real: una persona había descargado 64 de 70 CVs adaptados, otra 1 de 8. No construyas un embudo que termina en un número que no puedes observar.

**Asset:** needs capture — the `/admin/pulse` funnel, with no names.

## P11 · Lessons from building with AI agents
**Hook:** "Five rules I now follow when building with an AI pair."

**EN:**
1. One rulebook. Ours drifted between two files, so now there's one.
2. Every decision written down in under 150 words. It's how the AI remembers *why*.
3. Measure folklore. We designed around a "4,000-character prompt hang" that, once we measured it, no longer happens.
4. Reproduce before fixing. Guessed fixes failed twice.
5. Nothing reaches me unseen. A cheap model takes the screenshots, the AI judges them, and I do the final QA. We banned screenshots once to save budget, and the UI came back looking junior.

**ES:**
1. Un solo reglamento. El nuestro se desincronizó entre dos archivos, así que ahora hay uno.
2. Cada decisión por escrito en menos de 150 palabras. Así la IA recuerda el *porqué*.
3. Mide el folclore. Diseñamos alrededor de un "cuelgue a los 4.000 caracteres" que, cuando lo medimos, ya no ocurre.
4. Reproduce antes de arreglar. Los arreglos adivinados fallaron dos veces.
5. Nada me llega sin revisar. Un modelo barato toma las capturas, la IA las juzga y yo hago el QA final. Una vez prohibimos las capturas para ahorrar y la interfaz volvió con cara de junior.

**Asset:** needs capture — a diagram of the REQ → ADR → build → -edu loop.

## P12 · Open problem — a 95 I didn't deserve
**Hook:** "I scored 95 on a mock interview. My answers were weak."

**EN:** I practised reading Jobot's own prepared answers aloud and scored 95. My reaction to the answers: "so short, so lame." Two lessons. First, a session where you read your answers shouldn't count toward readiness, so now it's labelled "With help" and excluded. Second, nothing was ever checking whether the prepared answers were good. Next step: a reference set of strong, medium and weak answers labelled by hand, and an evaluator measured against it. Not solved yet. I'll report back.

**ES:** Practiqué leyendo en voz alta las respuestas que Jobot me preparó y saqué 95. Mi reacción a las respuestas: "tan cortas, tan flojas". Dos lecciones. Primera: una sesión en la que lees tus respuestas no debería contar para tu preparación, así que ahora se marca "Con ayuda" y se excluye. Segunda: nada revisaba si las respuestas preparadas eran buenas. Siguiente paso: un set de referencia de respuestas fuertes, medias y débiles etiquetadas a mano, y un evaluador medido contra él. Aún no está resuelto. Les cuento.

**Asset:** needs capture — Feedback for session 55 with the "With help" label.
