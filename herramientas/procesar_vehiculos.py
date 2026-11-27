"""
Procesa las imágenes de vehículos generadas con IA y las deja listas para la app.

Uso:
    pip install rembg onnxruntime pillow       (solo la primera vez; no es parte del servidor)
    python herramientas/procesar_vehiculos.py CARPETA_CON_IMAGENES

Cada imagen de la carpeta debe llamarse  marca-modelo-color.png  (o .jpg/.webp), por ejemplo:
    chevrolet-spark-blanco.png, kia-rio-rojo.jpg, chevrolet-d-max-gris.png

Por cada imagen:
  1. Quita el fondo (aunque venga liso o con sombra).
  2. Recorta al vehículo y lo centra en un lienzo 2:1 con un poco de aire.
  3. La guarda como WebP de 1200 x 600 en static/vehiculos/modelos/ (menos de ~80 KB).
  4. Agrega el modelo y el color a static/vehiculos/manifest.json (tipo y alias del CATALOGO).
"""
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "static" / "vehiculos" / "modelos"
MANIFIESTO = RAIZ / "static" / "vehiculos" / "manifest.json"

COLORES = {"blanco", "negro", "gris", "plata", "rojo", "azul", "amarillo"}
ANCHO, ALTO = 1200, 600
MARGEN_X, MARGEN_Y = 0.04, 0.08     # aire alrededor del vehículo (proporción del lienzo)
PESO_MAXIMO = 80 * 1024

# Tipo de carrocería y otras formas de escribir el modelo (tal como aparecen en los registros).
# La app también reconoce el modelo sin la marca si está en "alias".
CATALOGO = {
    "chevrolet-aveo":       {"tipo": "sedan",     "alias": ["aveo"]},
    "chevrolet-spark":      {"tipo": "hatchback", "alias": ["spark"]},
    "chevrolet-corsa":      {"tipo": "sedan",     "alias": ["corsa"]},
    "chevrolet-sail":       {"tipo": "sedan",     "alias": ["sail"]},
    "chevrolet-captiva":    {"tipo": "suv",       "alias": ["captiva"]},
    "chevrolet-d-max":      {"tipo": "pickup",    "alias": ["dmax", "d-max"]},
    "kia-soluto":           {"tipo": "sedan",     "alias": ["soluto"]},
    "kia-rio":              {"tipo": "sedan",     "alias": ["rio"]},
    "kia-picanto":          {"tipo": "hatchback", "alias": ["picanto"]},
    "nissan-sentra":        {"tipo": "sedan",     "alias": ["sentra"]},
    "hyundai-accent":       {"tipo": "sedan",     "alias": ["accent"]},
    "hyundai-grand-i10":    {"tipo": "hatchback", "alias": ["grand-i10", "i10"]},
    "suzuki-grand-vitara":  {"tipo": "suv",       "alias": ["vitara", "grand-vitara"]},
}


def slug(texto: str) -> str:
    """'Chevrolet Spark' -> 'chevrolet-spark' (minúsculas, sin tildes, con guiones)."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def quitar_fondo(img: Image.Image, sesion) -> Image.Image:
    from rembg import remove
    salida = remove(img, session=sesion, post_process_mask=True)
    return salida.convert("RGBA")


def encuadrar(img: Image.Image) -> Image.Image:
    """Recorta al contenido visible y lo centra en un lienzo 2:1 transparente, apoyado abajo."""
    alfa = img.split()[-1].point(lambda a: 255 if a > 24 else 0)
    caja = alfa.getbbox()
    if not caja:
        raise ValueError("no se encontró el vehículo en la imagen")
    auto = img.crop(caja)
    util_w, util_h = ANCHO * (1 - 2 * MARGEN_X), ALTO * (1 - 2 * MARGEN_Y)
    escala = min(util_w / auto.width, util_h / auto.height)
    auto = auto.resize((max(1, round(auto.width * escala)), max(1, round(auto.height * escala))), Image.LANCZOS)
    lienzo = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    x = (ANCHO - auto.width) // 2
    y = ALTO - round(ALTO * MARGEN_Y) - auto.height     # las ruedas quedan a la misma altura en todas
    lienzo.paste(auto, (x, y), auto)
    return lienzo


def guardar_webp(img: Image.Image, ruta: Path) -> int:
    """Guarda bajando la calidad hasta quedar bajo el peso máximo."""
    for calidad in (86, 80, 74, 68, 62, 56):
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=calidad, method=6, alpha_quality=90)
        if buf.tell() <= PESO_MAXIMO or calidad == 56:
            ruta.write_bytes(buf.getvalue())
            return buf.tell()
    return 0


def main(carpeta: str) -> None:
    from rembg import new_session
    sesion = new_session("isnet-general-use")
    DESTINO.mkdir(parents=True, exist_ok=True)
    manifiesto = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    manifiesto.setdefault("tipos", {})
    modelos = manifiesto.setdefault("modelos", {})

    archivos = sorted(p for p in Path(carpeta).iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
    if not archivos:
        print("No hay imágenes en", carpeta)
        return
    for ruta in archivos:
        nombre = slug(ruta.stem)
        color = nombre.rsplit("-", 1)[-1]
        clave = nombre[: -(len(color) + 1)]
        if color not in COLORES or not clave:
            print(f"  OMITIDA {ruta.name}: el nombre debe terminar en un color ({', '.join(sorted(COLORES))})")
            continue
        try:
            img = encuadrar(quitar_fondo(Image.open(ruta).convert("RGBA"), sesion))
        except Exception as e:
            print(f"  ERROR   {ruta.name}: {e}")
            continue
        destino = DESTINO / f"{clave}-{color}.webp"
        peso = guardar_webp(img, destino)
        info = modelos.setdefault(clave, {})
        info.update({k: v for k, v in CATALOGO.get(clave, {}).items() if k not in info})
        colores = set(info.get("colores", [])) | {color}
        info["colores"] = sorted(colores, key=lambda c: ["blanco", "negro", "gris", "plata", "rojo", "azul", "amarillo"].index(c))
        print(f"  OK      {destino.relative_to(RAIZ)}  ({peso // 1024} KB)")

    MANIFIESTO.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Manifiesto actualizado:", MANIFIESTO.relative_to(RAIZ))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
