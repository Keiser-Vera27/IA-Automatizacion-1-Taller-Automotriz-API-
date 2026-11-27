# Sistema de diseño — Oficial de Registros

Guía para que cualquier pantalla nueva se vea y se mueva igual que el resto.
La referencia visual viva está en **`static/guia-estilos.html`** (ábrela en el navegador:
`/web/guia-estilos.html`). Los valores reales viven en `static/style.css`.

---

## 1. Principios

1. **Oscuro, sereno y legible.** Noche índigo con vidrio translúcido. La información manda; la decoración acompaña.
2. **El brillo se gana.** El degradado holográfico es escaso: solo para lo más importante de cada pantalla.
3. **Un solo lugar para cada cosa.** Una acción principal por pantalla, una cifra protagonista, un color por significado.
4. **Datos reales, nunca de relleno.** Si no hay dato, se dice ("Sin cliente registrado", "—"); no se inventa.
5. **Pensado para el celular del taller.** Todo funciona con el pulgar: objetivos de 40 px o más, sin desborde horizontal.

---

## 2. Color

### Superficies (tema oscuro, por defecto)

| Token | Valor | Uso |
|---|---|---|
| `--fondo` | `#0A0D26` + luces violeta y estrellas | Fondo de la app |
| `--superficie-1` | `rgba(255,255,255,.055)` | Tarjetas y paneles de vidrio |
| `--superficie-2` | `rgba(255,255,255,.075)` | Bloques dentro de una tarjeta, campos |
| `--superficie-3` | `rgba(255,255,255,.11)` | Hover y elementos elevados |
| `--linea` / `--linea-fuerte` / `--linea-intensa` | blanco al 9 / 13 / 22 % | Bordes de 1 px y separadores |
| `--vidrio-blur` | `blur(18px) saturate(140%)` | `backdrop-filter` de tarjetas en oscuro |

### Texto

| Token | Valor | Uso |
|---|---|---|
| `--tinta` | `#F4F2FF` | Títulos, cifras, texto principal |
| `--tinta-2` | `#C9C5E8` | Texto secundario |
| `--tinta-3` | `#9C98C2` | Etiquetas, ayudas, fechas |

### Acentos y significado

| Color | Valor | Significado (no se usa para otra cosa) |
|---|---|---|
| **Holográfico** `--holo` | menta `#9BF3C9` → lima `#D6F56A` → amarillo `#F7E58A` → rosa `#F3A6E3` → violeta `#A58BFF` | Jerarquía máxima: sección actual del menú, acción principal, cifra protagonista. Texto encima siempre `--sobre-holo` (`#10122E`) |
| Violeta | `#A58BFF`, `#8A2BE2`, `#A855F7` | Acento de marca: foco, selección, comentarios, líneas laterales |
| Esmeralda / menta | `#34D399`, `#9BF3C9` | Aprobado, entregado, monto a favor |
| Ámbar | `#F7C56A` | Pendiente, en trabajo, avisos |
| Rosa / rojo suave | `#FDA4AF`, `#FF8FB1` | Rechazado, error, tasa alta |

**Reglas**
- Máximo **tres** piezas holográficas por pantalla (ej. menú activo + botón principal + cifra principal).
- El verde solo significa "aprobado/bien". Nunca como decoración.
- Variante clara: mismos significados con tonos más oscuros (`#047857`, `#BE123C`, `#7E22CE`). Toda regla nueva de color se escribe también para `html[data-theme="light"]`.

---

## 3. Tipografía

**Plus Jakarta Sans** (variable, autoalojada en `static/fonts/`). Sin otras fuentes.

| Token | Tamaño | Uso |
|---|---|---|
| `--t-2xl` | 30 px | Saludo, cifras protagonistas |
| `--t-xl` | 22 px | Títulos de modal |
| `h1` de vista | 30 px (`--t-2xl`), `letter-spacing: -.03em` | Título de cada sección |
| `--t-l` | 18 px | Títulos de tarjeta |
| `--t-m` | 15 px | Texto base de interfaz |
| `--t-s` | 14 px | Filas, listas |
| `--t-xs` | 13 px | Etiquetas, fechas, ayudas |

- Cifras y dinero: **`font-variant-numeric: tabular-nums`** siempre (clase `.num`).
- Etiquetas de sección pequeñas: mayúsculas, 11–12 px, `letter-spacing: .06em`, `--tinta-3`.
- En campos de formulario del celular: 16 px (evita el zoom de iOS).

---

## 4. Espacio, radios y sombras

- **Espaciado base 4:** `--e-1` 4 · `--e-2` 8 · `--e-3` 12 · `--e-4` 16 · `--e-5` 24 · `--e-6` 32 · `--e-7` 48.
- **Separación entre tarjetas:** 12–16 px. Dentro de una tarjeta: 12–18 px.
- **Radios:** píldora `999px` (botones, chips, buscadores) · 24 px (paneles grandes) · 18–20 px (tarjetas) · 14–16 px (bloques internos) · 10–12 px (botones de ícono).
- **Celular (< 768 px):** 16 px a cada lado y 100 px abajo para la barra de navegación.
- **Sombras:** casi no se usan en oscuro; el vidrio y el borde fino dan la profundidad. La pieza holográfica puede llevar un resplandor violeta suave (`0 16px 36px rgba(183,160,255,.2)`).

---

## 5. Componentes

Todos están en `static/style.css` y se ven en `guia-estilos.html`.

| Componente | Clases | Cuándo |
|---|---|---|
| Cabecera de vista | `.veh-cabecera` (h1 + p + botón) | Arriba de cada sección, con su acción principal a la derecha |
| Botón principal | `.btn .btn-primario` | Una sola acción principal por pantalla |
| Botón secundario | `.btn-chico` (`.principal` = holográfico) | Acciones dentro de tarjetas |
| Botón de ícono | `.btn-icono` (`.peligro` para eliminar) | Editar, eliminar, cerrar. Siempre con `aria-label` |
| Chips de filtro | `.veh-chip` con `aria-pressed` | Filtros rápidos (Todos, En taller, 30 días) |
| Buscador | `.buscador-grande` + `input` | Píldora con lupa |
| Cifras de resumen | `.veh-cifras > .veh-cifra` (`.menta`, `.ambar`, `.lila`, `.rojo`) | 3–4 indicadores arriba de una vista |
| Indicador grande | `.dash-kpi` (el primero puede ser holográfico) | Dashboard y ficha |
| Tarjeta de vidrio | `.gar-tarjeta`, `.srv-tarjeta`, `.vidrio` | Agrupar una sección |
| Fila de lista | `.resultado-vehiculo` (`.activo`) | Listas maestro-detalle |
| Estado | `.badge-estado` + `.estado-pendiente / -terminado / -sin-cobro / -info` | Estado de una orden |
| Placa | `.placa` (`.chica`) | Identificador del vehículo, siempre así |
| Datos separados | `.separados > span` | Varios datos en una línea (pone el punto entre ellos) |
| Modal | `mostrarModal({...})` | Resultados y confirmaciones (nunca `alert` ni `confirm`) |
| Hoja inferior | `.srv-hoja` | Formularios en el celular |

**Reglas de contenido**
- Nunca el carácter "·" en el texto: varios datos van en `.separados`.
- Fechas cortas: "20 nov 2026" (`fechaCorta`). Dinero: `$1,234.50` (`dinero`).
- Todo texto que viene de la base de datos pasa por `escaparHTML` o `textContent`.
- Sin emojis en la interfaz.

---

## 6. Movimiento

Personalidad **corporativa con toque premium**: rápido, firme, sin rebotes.

| Token | Valor | Uso |
|---|---|---|
| `--curva` | `cubic-bezier(.2,0,0,1)` | Casi todo (curva firma) |
| `--curva-entra` | `cubic-bezier(.05,.7,.1,1)` | Lo que aparece (desacelera) |
| `--curva-sale` | `cubic-bezier(.3,0,1,1)` | Lo que se va (acelera) |
| `--mov-rapido` | 140 ms | Hover, presionar |
| `--mov-estandar` | 240 ms | Tarjetas, filas, chips |
| `--mov-lento` | 360 ms | Vistas, modales |
| `--paso` | 30 ms | Escalonado entre elementos (máximo 8) |

- **Una sola entrada** en toda la app: aparece subiendo 8 px con fundido (`@keyframes aparece`).
- Lo que entra dura más que lo que sale. Los modales cierran más rápido de lo que abren.
- Botones: se hunden a 0.97 al presionar. Tarjetas de cifras: suben 2 px al pasar el mouse.
- Cifras protagonistas cuentan hasta su valor (`animarCifras`), solo si el valor cambió.
- Con "reducir movimiento" del sistema no hay animaciones (`prefiereMenosMovimiento()`).
- Nunca animar `width`/`height`/`top`: solo `transform` y `opacity`.

---

## 7. Accesibilidad

- Contraste AA mínimo; el texto sobre holográfico siempre oscuro.
- Objetivos táctiles de 40 px o más en el celular.
- Foco visible (contorno violeta) en botones, chips y campos.
- Estados no solo por color: siempre con texto ("Aprobado", "En taller").
- `aria-pressed` en chips, `aria-current` en el menú y en la fila activa, `aria-live` en zonas que cambian.

---

## 8. Lista para una pantalla nueva

1. Cabecera `.veh-cabecera` con título, una línea de contexto y la acción principal.
2. ¿Hace falta resumen? `.veh-cifras` con 3–4 indicadores reales.
3. Contenido en tarjetas de vidrio con bordes de 1 px; nada de cajas dentro de cajas.
4. Holográfico en máximo tres piezas; verde solo para aprobado.
5. Variante clara escrita y revisada.
6. Celular: 16 px a los lados, 100 px abajo, sin desborde, tablas convertidas en tarjetas.
7. Entrada con `aparece` y escalonado; respeta reducir movimiento.
8. Sin "·", sin emojis, textos de la base escapados, resultados en el modal.
