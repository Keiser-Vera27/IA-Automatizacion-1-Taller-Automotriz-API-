---
version: 1
slug: "static-index-html"
primary_target: "static/index.html"
related_targets: ["static/admin.html","static/cotizacion.html"]
---

## Alcance

App principal (static/index.html), panel de control (static/admin.html) y cotización pública (static/cotizacion.html). Modo: Operate (app y panel); la cotización es Operate para el cliente final. Rediseño completo del mundo visual; se conserva la lógica de script.js y los IDs que usa.

## Direction contract

THESIS: El vehículo se reconoce por su placa, no por un número de orden. La placa ecuatoriana es el identificador visual en toda la app. Se rechaza el panel SaaS genérico de tarjetas iguales con degradados y vidrio.

OWN-WORLD: Fondo claro neutro con tinte violeta frío; barra superior morada #7030EF sólida con el logo oscuro (celdas blancas, gorra lima). Lima #C6FF3D solo como señal sobre morado o tinta (selección actual, foco). Barlow para la interfaz, Barlow Semi Condensed para placas y cifras de dinero. Placa: rectángulo blanco con borde de tinta, franja superior morada con la palabra Ecuador, caracteres condensados en negrita. Bordes de 1px, radios de 8 a 12px, sombras cortas con desplazamiento.

STORY: El personal busca o escribe una placa y encuentra el vehículo al instante; ve qué está en proceso y qué está listo; registra con Geor IA escribiendo; cierra el día con la caja cuadrada. El cliente abre su cotización y la aprueba.

FIRST VIEWPORT: Barra superior morada con logo a la izquierda, buscador de placa al centro (siempre visible) y caja de hoy a la derecha. Debajo, navegación lateral en escritorio (barra inferior en celular). Área de trabajo: el compositor de Geor IA arriba y la lista de vehículos del día, cada fila encabezada por su placa. La acción principal es Enviar a Geor IA.

FORM: Placa vehicular, candidato 1 de 7 de la lista propia, elegido por el usuario en lugar del asignado (Rótulo de taller, candidato 5). seed:f8999ec4037fb6c3 (ronda degradada, sin catálogo).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
