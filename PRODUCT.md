# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Personal del taller mecánico (usuario principal).** Recepcionista y dueño del taller. Usan la app tanto en el computador del mostrador como en el celular dentro del área de trabajo; ambos contextos tienen el mismo peso. Su trabajo: registrar ingresos de vehículos, reparaciones, gastos e inventario escribiendo en lenguaje natural, cerrar órdenes, cuadrar la caja del día y consultar datos.
- **Cliente final del taller.** Abre la página de cotización desde un enlace que el taller le envía por WhatsApp, en su celular y sin iniciar sesión, para revisar y aprobar o rechazar los trabajos propuestos. (Supuesto inferido del código: `mensaje_cotizacion` arma el texto con el link; pendiente de confirmar.)
- **Superadministrador de la plataforma.** El creador del producto. Usa el panel de control para dar de alta talleres, asignar planes y módulos, y revisar métricas por taller.

## Product Purpose

Plataforma SaaS multi-taller para talleres automotrices de Ecuador que elimina el registro manual. El personal escribe lo que pasó ("Cambio de frenos placa ABC-123, pagó Carlos 40") y la IA lo convierte en registros estructurados: órdenes de reparación, gastos, inventario. Luego el mismo chat responde consultas analíticas. Éxito: el taller deja de transcribir mensajes a Excel y el dueño ve su caja y su rendimiento sin pedir reportes.

## Positioning

El registro se hace conversando, no llenando formularios: un asistente (Geor IA) recibe texto libre, extrae los datos, pide lo que falta y lo guarda aislado por taller.

## Operating Context

- Ritmo de 10 a 20 vehículos diarios por taller; registros cortos y frecuentes durante la jornada.
- Uso en mostrador (computador) y en el taller (celular, a veces con manos ocupadas o sucias, con luz variable).
- Cierre del día: cuadre de caja (órdenes cerradas, gastos, saldo neto, rendimiento por técnico) y exportación a Excel.
- Zona horaria del negocio: America/Guayaquil. Moneda: dólares.

## Capabilities and Constraints

- App principal (`static/index.html` + `script.js`): login, chat con Geor IA, vehículos y clientes, dashboard analítico y cuadre de caja, catálogo de servicios, garantías, inventario, cotizaciones.
- Panel de control (`static/admin.html`): talleres, usuarios, planes y módulos por taller, ficha 360.
- Cotización pública (`static/cotizacion.html`): página autocontenida, sin sesión, para el cliente.
- Módulos se activan o desactivan por taller según su plan (`data-modulo`); la interfaz debe ocultar lo que el plan no incluye.
- Stack: backend FastAPI en Render, Supabase (Postgres), frontend HTML/CSS/JS vanilla servido en `/web`. El rediseño mantiene ese stack y no reescribe la lógica de `script.js`.
- Ciertos datos son obligatorios solo al cerrar una orden, no al ingresar el vehículo (al ingreso: nombre y apellido del cliente, modelo, placa y motivo).

## Brand Commitments

- Nombre del producto: **Oficial de Registros** (nombre descriptivo temporal). No usar "Autotronic Solutions" en la interfaz: era solo el taller de pruebas.
- Asistente de IA dentro del chat: **Geor IA**.
- Logo "oficial con gorra": globo de chat partido en celdas con gorra de oficial mecánico. Morado `#7030EF` con gorra lima `#C6FF3D`. Archivos en `static/brand/`.
- Sin emojis en la interfaz ni en el código.
- Los mensajes de resultado (éxito o error con motivo) se muestran en un modal centrado con botón OK.
- Idioma: español de Ecuador.

## Evidence on Hand

- Logos y favicons en `static/brand/` (horizontal, horizontal-dark, símbolo, baldosa, íconos de app).
- Plantillas de Excel de inventario en `Claude outputs/`.
- No hay testimonios, clientes publicables ni métricas de uso: no inventarlos.

## Product Principles

1. Escribir es más rápido que llenar un formulario: el chat es el centro de la operación.
2. El dato que falta se pide en el momento justo (al cerrar la orden), no antes.
3. Cada taller ve solo lo suyo y solo lo que su plan incluye.
4. El cierre del día debe cuadrar sin trabajo manual.
5. Debe funcionar igual de bien en el mostrador y en el celular dentro del taller.

## Accessibility & Inclusion

- Usuarios con alfabetización digital variada; textos simples y acciones con nombres claros.
- Uso en celular dentro del taller: objetivos táctiles amplios y contraste suficiente con luz variable.
