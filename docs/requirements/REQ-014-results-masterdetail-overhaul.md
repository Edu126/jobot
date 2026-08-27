# REQ-014: Results Master/Detail View Overhaul

Date: 2026-08-27
Source: User (product spec, verbatim en chat)
Status: Open

## What they asked for

"Mejorar la escaneabilidad de la lista de resultados (panel izquierdo) reduciendo
la carga cognitiva, optimizando el espacio horizontal y centralizando el análisis
profundo en el panel de detalle (panel derecho)."

1. **Grid:** proporción 35/65 o 40/60 (master/detail)
2. **Job card (izquierdo):** eliminar bloque Gaps; título `text-base` con
   `line-clamp-2`; score badge cuadrado → Progress Ring circular en esquina
   superior derecha (borde proporcional al fit %, solo número, sin `/100`);
   chips New/Viewed menos prominentes (dot o `font-normal`)
3. **Detail panel (derecho):** Save/Corazón se queda donde está (header del
   pane); Matched + Gaps se consolidan solo aquí (eliminados de la card izquierda)

## What they actually need

El panel izquierdo compite con el derecho — muestra tanta información (score,
gaps, badges) que el usuario no puede escanear rápido cuál job merece atención.
El need real es una lista de señales mínimas para decidir "¿vale la pena abrir
este?" — score visual compacto, título, empresa — y que todo el análisis profundo
viva a la derecha donde hay espacio y contexto. El Progress Ring comunica el score
más densamente que el badge cuadrado: misma información, menos área.

## How we'll know it worked

El usuario puede escanear la lista sin abrir el detail pane para decidir qué jobs
ignorar — el ring + título + empresa son suficientes.

## Related

ADR-012 (results workspace layout)
