# Prompts para generar las imágenes de vehículos (Gemini)

Lista de los modelos que faltan, ordenada por prioridad. Ya están hechos (no los repitas):
Chevrolet Aveo, Spark, Sail, Onix, Corsa, D-Max, Tracker, Captiva · Suzuki Grand Vitara ·
Kia Picanto · Toyota Yaris, Corolla, Fortuner, RAV4 · Nissan Sentra (2016-2019), Versa,
Frontier, Kicks, X-Trail · Mazda BT-50.

---

## 1. Prompt base (cópialo completo y cambia solo lo que está entre corchetes)

Abre **una conversación nueva por modelo** y pega:

```
Genera una imagen fotorrealista de estudio de un [MODELO Y GENERACIÓN] color blanco.

Descripción para que sea exacto: [DETALLES DEL MODELO].

Encuadre y estilo (obligatorio):
- Vista lateral tres cuartos desde adelante: el frente del vehículo mira hacia la IZQUIERDA de la imagen, ángulo de unos 30 grados, cámara a la altura de las puertas.
- El vehículo completo, centrado, ocupando casi todo el ancho, con un poco de aire arriba y abajo. No cortes ninguna parte.
- Fondo liso gris claro uniforme, sin piso visible, sin sombra proyectada en el suelo y sin reflejos.
- Luz suave de estudio desde arriba, como foto de catálogo de concesionario.
- Versión de fábrica: rines, faros, parrilla y espejos originales de ese modelo y año, sin accesorios ni modificaciones.
- Sin placa (deja el espacio vacío), sin logotipos ni emblemas legibles, sin texto, sin marcas de agua, sin personas.
- Formato horizontal (más ancho que alto).
```

**Para cada color adicional**, en la MISMA conversación y después de tener la blanca:

```
Usa exactamente la imagen anterior y cambia solo el color de la carrocería a [COLOR].
Mantén idéntica la forma, el ángulo, el encuadre, las luces, los rines, los vidrios, las partes negras de plástico y el fondo gris liso.
```

Colores, en este orden: rojo, gris, negro, plata, azul. En los modelos marcados como **taxi**, agrega también amarillo.

**Si algo sale mal**
- Salió con placa, logotipo o texto: "Quita la placa, los logotipos y cualquier texto".
- El frente mira a la derecha: "Gira el vehículo para que el frente mire a la izquierda, misma vista tres cuartos".
- Es otra generación del modelo: repite pegando de nuevo la descripción de detalles.
- Modelos poco conocidos (marcados con ⚠): sube también una foto real del vehículo y escribe
  "Usa esta foto solo como referencia del modelo" antes del prompt.

---

## 2. Nombres de los archivos

`marca-modelo-color.png`, en minúsculas, sin tildes y con guiones. El nombre de cada modelo está
en la columna **Archivo** (agrega el color al final): `kia-soluto-blanco.png`, `kia-soluto-rojo.png`.
Si no les cambias el nombre, igual los identifico, pero con el nombre voy más rápido.

---

## 3. Prioridad 1: los que ya entraron a tu taller

| Archivo | [MODELO Y GENERACIÓN] | [DETALLES DEL MODELO] |
|---|---|---|
| `kia-soluto` | Kia Soluto sedán (2019 en adelante) | Sedán compacto de 4 puertas, parrilla "nariz de tigre" pequeña con contorno cromado, faros alargados hacia los guardafangos, rines de 14 pulgadas. **Taxi** |
| `kia-rio-r` | Kia Rio R sedán (2012 a 2017) | Sedán de 4 puertas de tercera generación, parrilla nariz de tigre angosta, faros grandes rasgados hacia atrás, línea lateral marcada. **Taxi** |
| `kia-rio-stylus` | Kia Rio Stylus sedán (2005 a 2011) | Sedán de 4 puertas de segunda generación, formas redondeadas, parrilla ovalada pequeña, faros grandes en forma de gota. **Taxi** |
| `kia-rio` | Kia Rio sedán de cuarta generación fabricado en México (2018 a 2023) | Sedán de 4 puertas, parrilla nariz de tigre ancha con malla, faros con contorno LED, líneas rectas modernas. **Taxi** |
| `hyundai-accent` | Hyundai Accent sedán (2012 a 2017) | Sedán de 4 puertas generación RB, parrilla hexagonal grande, faros alargados, línea lateral ascendente hacia atrás. **Taxi** |
| `hyundai-grand-i10` | Hyundai Grand i10 hatchback de 5 puertas (2014 a 2019) | Hatchback pequeño, parrilla hexagonal con faros antiniebla redondos, faros rasgados, rines de 14 pulgadas. |
| `toyota-hilux` | Toyota Hilux doble cabina (2016 a 2020) | Pickup doble cabina de octava generación, parrilla grande con barras cromadas, faros alargados que se unen a la parrilla, estribos laterales. |
| `nissan-almera` | Nissan Almera sedán (2012 a 2019) | Sedán de 4 puertas, parrilla en V cromada, faros grandes redondeados, techo alto, rines de 15 pulgadas. **Taxi** |
| `renault-logan` | Renault Logan sedán (2015 a 2022) | Sedán de 4 puertas de segunda generación, parrilla con barra cromada horizontal, faros rasgados con fondo negro. **Taxi** |
| `mazda-3` | Mazda 3 sedán (2014 a 2018) | Sedán de 4 puertas, parrilla de cinco puntos grande con marco cromado en ala, faros estilizados, capó largo. |
| `mazda-allegro` | Mazda Allegro sedán (1995 a 2003) ⚠ | Sedán de 4 puertas, versión del Mazda 323 de esa época, formas redondeadas de los noventa, parrilla delgada, faros rectangulares. |
| `chevrolet-n200` | Chevrolet N200 furgoneta (2010 a 2020) ⚠ | Minivan de carga pequeña tipo furgoneta, frente corto y recto, puerta lateral corrediza, techo alto. |
| `changan-cs55` | Changan CS55 SUV (2018 a 2022) | SUV compacta, parrilla grande con barras cromadas horizontales, faros LED delgados, tapizado negro en guardafangos. |
| `jac-s5` | JAC S5 SUV (2013 a 2019) ⚠ | SUV compacta, parrilla trapezoidal cromada, faros grandes rasgados, barras en el techo. |
| `jac-t6` | JAC T6 pickup doble cabina (2016 a 2022) ⚠ | Pickup doble cabina, parrilla grande cromada con barras horizontales, faros rasgados, estribos laterales. |
| `volkswagen-voyage` | Volkswagen Voyage sedán (2013 a 2022) | Sedán compacto de 4 puertas, versión sedán del Gol G6, parrilla delgada horizontal que une los faros. |
| `chevrolet-steem` | Chevrolet Steem / Suzuki Swift (1995 a 2005) ⚠ | Hatchback pequeño de los noventa, versión del Suzuki Swift de segunda generación, formas sencillas y redondeadas. |
| `zotye-nomada` | Zotye Nómada SUV ⚠ | Sube una foto real como referencia: es un modelo poco conocido y la IA puede inventarlo. |

---

## 4. Prioridad 2: Nissan clásicos

| Archivo | [MODELO Y GENERACIÓN] | [DETALLES DEL MODELO] |
|---|---|---|
| `nissan-sentra-b13` | Nissan Sentra B13 sedán (1991 a 1994, muy común en Latinoamérica hasta 2017) | Sedán de 4 puertas cuadrado y sencillo, parrilla delgada con barras horizontales, faros rectangulares delgados, rines de 13 pulgadas con tapacubos. **Taxi** |
| `nissan-sentra-b14` | Nissan Sentra B14 sedán (1995 a 1999) | Sedán de 4 puertas, formas más redondeadas que el B13, parrilla ovalada pequeña cromada, faros alargados. **Taxi** |
| `nissan-sentra-b15` | Nissan Sentra B15 sedán (2000 a 2006) | Sedán de 4 puertas, parrilla trapezoidal con barras horizontales, faros grandes con fondo cromado, maletero alto. **Taxi** |
| `nissan-tiida` | Nissan Tiida sedán fabricado en México (2007 a 2018) | Sedán de 4 puertas alto y redondeado, parrilla en V con malla, faros grandes que suben hacia el capó, techo arqueado. **Taxi** |
| `nissan-march` | Nissan March hatchback (2011 a 2019) | Hatchback pequeño de 5 puertas, formas redondeadas, faros grandes en forma de gota, parrilla pequeña. |
| `nissan-navara` | Nissan Navara D40 doble cabina (2008 a 2014) | Pickup doble cabina, parrilla grande cromada con tres barras, guardafangos marcados, estribos. |

---

## 5. Prioridad 3: comunes en Ecuador (para cuando entren)

| Archivo | [MODELO Y GENERACIÓN] | [DETALLES DEL MODELO] |
|---|---|---|
| `chevrolet-vitara` | Chevrolet Vitara de 3 puertas (1995 a 2013) | SUV pequeña de 3 puertas con rueda de repuesto en el portón trasero, formas cuadradas de los noventa, guardafangos de plástico. |
| `chevrolet-luv-d-max` | Chevrolet Luv D-Max doble cabina (2005 a 2013) | Pickup doble cabina, parrilla con barra cromada central y emblema, faros grandes angulares. |
| `chevrolet-luv` | Chevrolet Luv doble cabina (1997 a 2004) | Pickup doble cabina de los noventa, frente cuadrado, faros rectangulares, parrilla cromada. |
| `chevrolet-optra` | Chevrolet Optra sedán (2004 a 2012) | Sedán mediano de 4 puertas, parrilla con barra cromada central, faros grandes redondeados. **Taxi** |
| `chevrolet-cruze` | Chevrolet Cruze sedán (2011 a 2016) | Sedán mediano de 4 puertas, parrilla dividida en dos con barra cromada, faros rasgados hacia atrás. |
| `chevrolet-beat` | Chevrolet Beat hatchback (2018 a 2022) | Hatchback pequeño de 5 puertas, parrilla dividida, faros grandes que suben hacia el capó. |
| `chevrolet-groove` | Chevrolet Groove SUV (2021 en adelante) | SUV pequeña, faros LED separados en dos niveles, parrilla negra ancha. |
| `kia-sportage` | Kia Sportage SUV (2016 a 2021) | SUV compacta de cuarta generación, parrilla nariz de tigre, faros altos rasgados, antiniebla en bloque de cuatro. |
| `kia-cerato` | Kia Cerato sedán (2014 a 2018) | Sedán mediano de 4 puertas, parrilla nariz de tigre, faros rasgados, línea lateral fluida. |
| `kia-sorento` | Kia Sorento SUV (2015 a 2020) | SUV mediana de 7 asientos, parrilla nariz de tigre grande, faros alargados. |
| `hyundai-tucson` | Hyundai Tucson SUV (2016 a 2021) | SUV compacta, parrilla hexagonal grande cromada, faros rasgados. |
| `hyundai-creta` | Hyundai Creta SUV (2016 a 2021) | SUV pequeña, parrilla hexagonal con tres barras cromadas, barras en el techo. |
| `hyundai-santa-fe` | Hyundai Santa Fe SUV (2013 a 2018) | SUV mediana, parrilla hexagonal con barras horizontales, faros rasgados. |
| `hyundai-i10` | Hyundai i10 hatchback (2008 a 2013) | Hatchback pequeño de 5 puertas, formas redondeadas, faros grandes, parrilla pequeña. |
| `chery-tiggo-2` | Chery Tiggo 2 SUV (2017 a 2022) | SUV pequeña, parrilla con barras horizontales cromadas, faros alargados. |
| `chery-tiggo-4` | Chery Tiggo 4 SUV (2019 en adelante) | SUV compacta, parrilla grande con patrón de rombos, faros LED delgados. |
| `chery-tiggo-7` | Chery Tiggo 7 SUV (2020 en adelante) | SUV mediana, parrilla grande con patrón de puntos cromados, faros delgados. |
| `chery-qq` | Chery QQ hatchback (2006 a 2013) | Hatchback muy pequeño de 5 puertas, faros grandes redondos, formas de burbuja. |
| `great-wall-wingle-5` | Great Wall Wingle 5 doble cabina (2011 a 2020) | Pickup doble cabina, parrilla cromada grande, faros alargados. |
| `great-wall-haval-h6` | Haval H6 SUV (2016 a 2020) | SUV compacta, parrilla grande con barras horizontales cromadas, faros LED. |
| `renault-sandero` | Renault Sandero hatchback (2015 a 2022) | Hatchback de 5 puertas, parrilla con barra cromada, faros rasgados. |
| `renault-duster` | Renault Duster SUV (2016 a 2021) | SUV compacta robusta, parrilla con barras cromadas, protector frontal gris, barras en el techo. |
| `renault-kwid` | Renault Kwid hatchback (2019 en adelante) | Hatchback pequeño alto tipo crossover, guardafangos negros, parrilla delgada. |
| `volkswagen-gol` | Volkswagen Gol hatchback (2013 a 2022) | Hatchback de 5 puertas, parrilla delgada horizontal que une los faros. |
| `suzuki-swift` | Suzuki Swift hatchback (2018 en adelante) | Hatchback de 5 puertas, parrilla ovalada grande, manijas traseras en el pilar. |
| `mazda-2` | Mazda 2 sedán (2016 a 2022) | Sedán compacto de 4 puertas, parrilla de cinco puntos con ala cromada, faros delgados. |
| `mazda-cx-5` | Mazda CX-5 SUV (2017 a 2022) | SUV compacta, parrilla grande de cinco puntos, faros muy delgados. |
| `mitsubishi-l200` | Mitsubishi L200 doble cabina (2016 a 2019) | Pickup doble cabina, frente "Dynamic Shield" con molduras cromadas en forma de X. |
| `mitsubishi-montero-sport` | Mitsubishi Montero Sport SUV (2016 a 2020) | SUV mediana, frente con molduras cromadas en forma de X, luces traseras verticales largas. |

---

## 6. Cuando termines

Deja las imágenes en la carpeta **imagenes vehiculos** y avísame. Las proceso, las reviso una por una
y muevo los originales a `procesadas`.
