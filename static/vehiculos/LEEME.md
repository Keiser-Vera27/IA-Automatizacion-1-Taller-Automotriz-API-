# Imágenes de vehículos

Las tarjetas de "En el taller" muestran una imagen del modelo de cada vehículo.
Las imágenes viven en esta carpeta y la app las busca en este orden:

1. El modelo en su color (`modelos/chevrolet-spark-rojo.webp`).
2. El modelo en blanco, si no existe ese color (el color real se sigue viendo en el punto de color de la tarjeta).
3. La ilustración del tipo de carrocería (`tipos/hatchback.webp`), si el modelo no tiene imágenes.
4. La placa, si no hay nada de lo anterior.

Ninguna imagen es obligatoria: la app funciona sin ellas.

## Cómo agregar un modelo

1. Genera las imágenes (ver "Cómo generarlas").
2. Guárdalas en `modelos/` con el nombre `marca-modelo-color.webp`, todo en minúsculas, sin tildes y con guiones:
   - `chevrolet-spark-blanco.webp`, `chevrolet-spark-rojo.webp`, `toyota-hilux-plata.webp`
3. Agrega el modelo a `manifest.json` con los colores que tiene:

```json
{
  "tipos": {
    "hatchback": "tipos/hatchback.webp",
    "pickup": "tipos/pickup.webp"
  },
  "modelos": {
    "chevrolet-spark": { "tipo": "hatchback", "colores": ["blanco", "negro", "gris", "plata", "rojo", "azul"] },
    "toyota-hilux":    { "tipo": "pickup",    "colores": ["blanco", "plata"], "alias": ["hilux"] }
  }
}
```

- La clave es `marca-modelo` tal como se escribe en el registro ("Chevrolet Spark" -> `chevrolet-spark`).
- También se reconoce el modelo sin marca ("Spark" -> `spark`) si lo pones en `alias`.
- Colores que entiende la app: `blanco`, `negro`, `gris`, `plata`, `rojo`, `azul`.
  Los parecidos se asignan solos: plateado -> plata, vino o guinda -> rojo, celeste -> azul, perla -> blanco, plomo o grafito -> gris.

## Cómo generarlas (para que todas se vean iguales)

Usa cualquier generador de imágenes con IA (ChatGPT, Gemini u otro).

**Paso 1: imagen base en blanco.** Una por modelo, con este texto (cambia el modelo y el año):

> Render 3D de estudio de un Chevrolet Spark 2016 color blanco, vista lateral tres cuartos desde adelante (ángulo de 30 grados), auto completo centrado, fondo transparente, luz suave de estudio desde arriba, sin placa, sin logotipos visibles, sin personas, sin texto, estilo fotorrealista limpio como en las apps de transporte. Formato horizontal 2:1.

**Paso 2: los demás colores, a partir de esa misma imagen.** Sube la imagen base y pide:

> Cambia solo el color de la carrocería a rojo. Mantén exactamente la misma forma, ángulo, luces, sombras, ruedas, vidrios y fondo transparente.

Repite el paso 2 para negro, gris, plata y azul. Así las seis imágenes del modelo coinciden.

**Tipos de carrocería (respaldo):** genera una imagen por tipo con el texto del paso 1, cambiando el modelo por el tipo
(por ejemplo, "un sedán genérico sin marca"): `sedan`, `hatchback`, `suv`, `camioneta`, `pickup`, `van`, `moto`.

## Formato de los archivos

- WebP con fondo transparente, 1200 x 600 px aproximadamente (relación 2:1).
- El auto debe ocupar casi todo el ancho, con un poco de aire arriba y abajo.
- Peso recomendado: menos de 80 KB por imagen.

## Modelos sugeridos para empezar

Lista orientativa de modelos frecuentes en talleres de Ecuador; ajústala a lo que más entra en tu taller.

| Marca | Modelos |
|---|---|
| Chevrolet | Spark, Aveo, Sail, Onix, Corsa, D-Max, Tracker, Captiva, Grand Vitara |
| Kia | Picanto, Rio, Soluto, Sportage, Sorento |
| Hyundai | i10, Accent, Tucson, Creta, Santa Fe |
| Toyota | Hilux, Yaris, Corolla, Fortuner, RAV4 |
| Nissan | Sentra, Versa, Frontier, Kicks, X-Trail |
| Mazda | BT-50, Mazda 2, Mazda 3, CX-5 |
| Suzuki | Swift, Vitara, Jimny |
| Renault | Logan, Sandero, Duster |
| Ford | Ranger, Explorer |
| Great Wall | Wingle, Haval H6 |
| Chery | Tiggo 2, Tiggo 4, Tiggo 7 |
| Mitsubishi | L200, Montero Sport |
| Volkswagen | Gol, Amarok |
