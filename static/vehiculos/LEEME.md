# Imágenes de vehículos

Las tarjetas de "En el taller", la ficha del vehículo y la lista de Vehículos y clientes
muestran una imagen del modelo de cada vehículo. La app la busca en este orden:

1. El modelo en su color (`modelos/chevrolet-spark-rojo.webp`).
2. El modelo en blanco, si no existe ese color (el color real se sigue viendo en el punto de color).
3. La ilustración del tipo de carrocería (`tipos/hatchback.webp`), si el modelo no tiene imágenes.
4. La placa, si no hay nada de lo anterior.

Ninguna imagen es obligatoria: la app funciona sin ellas.

---

## Flujo de trabajo

1. **Generas** las imágenes en Gemini (o ChatGPT) con los textos de abajo.
2. **Las nombras** `marca-modelo-color.png` y las guardas en una carpeta.
3. **Se procesan** con `herramientas/procesar_vehiculos.py`, que quita el fondo, centra el vehículo,
   las deja en WebP de 1200 x 600 y actualiza `manifest.json` solo.

No hace falta que la imagen venga con fondo transparente: un fondo gris liso es mejor,
porque los generadores no siempre lo hacen bien y la herramienta lo quita.

---

## Primer lote (los que más entran al taller)

Ordenados según los registros reales. Empieza solo con la imagen en **blanco** de cada uno:
con eso ya se ven todos los vehículos de ese modelo (de cualquier color). Los demás colores se
agregan después.

| # | Archivo base | Texto para el modelo (cópialo en el prompt) | Cubre registros como |
|---|---|---|---|
| 1 | `chevrolet-aveo-blanco.png` | Chevrolet Aveo Family sedán (generación 2008 a 2017) | Aveo Family, Aveo Family taxi, Chevrolet Aveo |
| 2 | `chevrolet-spark-blanco.png` | Chevrolet Spark hatchback de primera generación (2005 a 2012) | Chevrolet Spark, Chev Spark, Spark |
| 3 | `chevrolet-corsa-blanco.png` | Chevrolet Corsa Evolution sedán (2004 a 2008) | Corsa Evo |
| 4 | `chevrolet-sail-blanco.png` | Chevrolet Sail sedán (2015 a 2022) | Sail, Chevrolet Sail |
| 5 | `kia-soluto-blanco.png` | Kia Soluto sedán (2019 en adelante) | Kia Soluto, Soluto Xcite |
| 6 | `nissan-sentra-blanco.png` | Nissan Sentra B15 sedán (2000 a 2006) | Nissan Sentra, Sentra B15 |
| 7 | `hyundai-accent-blanco.png` | Hyundai Accent sedán (2012 a 2018) | Hyundai Accent |
| 8 | `kia-rio-blanco.png` | Kia Rio R sedán (2012 a 2017) | Kia Rio R, Rio R taxi, Rio Stylus |
| 9 | `hyundai-grand-i10-blanco.png` | Hyundai Grand i10 hatchback (2014 a 2019) | Hyundai Grand i10 |
| 10 | `suzuki-grand-vitara-blanco.png` | Suzuki Grand Vitara SZ de 5 puertas (2010 a 2015) | Vitara |
| 11 | `chevrolet-captiva-blanco.png` | Chevrolet Captiva SUV (2008 a 2016) | Chevrolet Captiva |
| 12 | `kia-picanto-blanco.png` | Kia Picanto hatchback (2011 a 2017) | Kia Picanto |
| 13 | `chevrolet-d-max-blanco.png` | Chevrolet D-Max doble cabina (2014 a 2022) | Chevrolet D-Max, Dmax |

Si en tu taller entra otra generación del mismo modelo (por ejemplo, el Spark GT nuevo),
cambia el texto entre paréntesis.

---

## Texto para Gemini

**Paso 1: imagen base en blanco** (una conversación nueva por modelo):

> Genera un render 3D fotorrealista de estudio de un **[TEXTO DEL MODELO]** color blanco.
> Vista lateral tres cuartos desde adelante, con el frente hacia la izquierda (ángulo de 30 grados).
> El auto completo, centrado y ocupando casi todo el ancho.
> Fondo liso gris claro uniforme, sin piso visible, sin sombra proyectada y sin reflejos en el suelo.
> Luz suave de estudio desde arriba. Sin placa, sin logotipos visibles, sin personas, sin texto.
> Ruedas y rines originales de fábrica. Formato horizontal.

**Paso 2: los otros colores, en la misma conversación y a partir de esa imagen:**

> Usa exactamente la imagen anterior y cambia solo el color de la carrocería a **rojo**.
> Mantén la misma forma, ángulo, encuadre, luces, ruedas, vidrios y el mismo fondo gris liso.

Repite el paso 2 con: negro, gris, plata, azul (y amarillo para los modelos que se usan como taxi:
Aveo Family, Kia Rio, Sail). Así todas las imágenes del modelo coinciden.

**Consejos**
- Si sale con placa, logotipos o texto, pide: "quita la placa y cualquier logotipo".
- Si cambia el ángulo al recolorear, vuelve a subir la imagen blanca y repite el paso 2.
- Descarga en la mayor resolución disponible.

---

## Nombres de los archivos

`marca-modelo-color.png` (o .jpg), en minúsculas, sin tildes y con guiones:
`chevrolet-spark-blanco.png`, `chevrolet-spark-rojo.png`, `kia-rio-amarillo.png`.

Colores que entiende la app: `blanco`, `negro`, `gris`, `plata`, `rojo`, `azul`, `amarillo`.
Los parecidos se asignan solos al mostrar: blanca o perla -> blanco, negra -> negro,
plateado -> plata, vino o guinda -> rojo, celeste -> azul, plomo o grafito -> gris, amarilla -> amarillo.

---

## Procesar las imágenes

```bash
pip install rembg onnxruntime pillow        # solo la primera vez (no es parte del servidor)
python herramientas/procesar_vehiculos.py RUTA/DE/LA/CARPETA
```

La herramienta:
- Quita el fondo y deja el vehículo apoyado a la misma altura en todas las imágenes.
- Guarda `static/vehiculos/modelos/marca-modelo-color.webp` (1200 x 600, menos de ~80 KB).
- Agrega el modelo y sus colores a `manifest.json`, con su tipo de carrocería y los alias
  (por ejemplo, "Aveo Family" y "Aveo" encuentran `chevrolet-aveo`).

Para un modelo que no esté en la lista de la herramienta, agrégalo al `CATALOGO` de
`herramientas/procesar_vehiculos.py` con su tipo y sus alias antes de procesarlo.

---

## manifest.json (referencia)

```json
{
  "tipos": { "hatchback": "tipos/hatchback.webp" },
  "modelos": {
    "chevrolet-spark": { "tipo": "hatchback", "alias": ["spark"], "colores": ["blanco", "rojo"] }
  }
}
```

- La clave es `marca-modelo` ("Chevrolet Spark" -> `chevrolet-spark`).
- `alias`: el modelo sin la marca u otras formas de escribirlo.
- `colores`: solo los que tienen imagen. Si falta el color pedido, se usa el blanco.

**Tipos de carrocería (respaldo opcional):** genera una imagen por tipo con el texto del paso 1
usando "un [sedán / hatchback / SUV / pickup / van] genérico sin marca", guárdala en `tipos/`
y regístrala en `"tipos"`: `sedan`, `hatchback`, `suv`, `pickup`, `van`.
