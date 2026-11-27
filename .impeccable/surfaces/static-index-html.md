---
version: 1
slug: "static-index-html"
primary_target: "static/index.html"
related_targets: ["static/admin.html","static/cotizacion.html"]
---

## Alcance

App principal (static/index.html), panel de control (static/admin.html) y cotización pública (static/cotizacion.html). Modo: Operate (app y panel); la cotización es Operate para el cliente final. Rediseño completo del mundo visual; se conserva la lógica de script.js y los IDs que usa.

## Direction contract

THESIS: Geor IA es el centro de la operación y los vehículos del taller conviven con la conversación. Cada vehículo se reconoce por su placa ecuatoriana y por la imagen de su modelo. Se rechaza el chatbot metido en una tarjeta y el panel SaaS de tarjetas iguales.

OWN-WORLD: Tema holográfico nocturno (elegido por el usuario sobre la referencia fintech): fondo índigo #0A0D26 con luces violeta y estrellas, vidrio oscuro translúcido con bordes de 1 px, y un degradado holográfico (menta, lima, amarillo, rosa, violeta) reservado para máximo tres piezas de jerarquía por pantalla, con texto oscuro encima. Verde esmeralda solo para aprobado. Plus Jakarta Sans. Placa blanca con franja morada "ECUADOR". Tarjeta de vehículo estilo Uber con imagen del modelo (galería propia en static/vehiculos). Sistema completo en DESIGN.md y guía viva en static/guia-estilos.html.

STORY: El personal escribe lo que pasó y Geor lo registra; ve al instante el vehículo en "En el taller"; toca un vehículo para hablar de él; revisa el pulso del día (en el taller, entregados, cobrado).

FIRST VIEWPORT: Barra con logo, buscador de placa (tecla /) y taller. Saludo con tres cifras del día. Columna ancha: Geor IA (cabecera con su símbolo, conversación, compositor con sugerencias). Columna derecha: vehículo destacado con imagen y lista compacta del resto. En el celular: saludo, carrusel de vehículos y Geor con el compositor fijo.

FORM: Placa vehicular en tema holográfico nocturno, pedido explícito del usuario (documento "Rediseño visual definitivo"). seed: none (pinned) "Fondos oscuros elegantes", "La IA debe ser protagonista", "chat con vehículos integrados".

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
