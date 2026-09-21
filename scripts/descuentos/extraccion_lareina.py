#Baja las promociones de La Reina, incluido lo que dicen las imagenes.

from __future__ import annotations
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from google.cloud import vision

URL = "https://www.lareinaweb.com.ar/"
AGENTE = "RosarioVivo/1.0 (proyecto de portfolio)"
ESPERA = 20
DESTINO = Path("data/raw/descuentos/lareina")
IMAGENES = DESTINO / "imagenes"
VERDAD = Path("tests/verdad_lareina.json")
DIAS_SEMANA = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]


# ---------------------------------------------------------------- utilidades

def limpiar(texto: str) -> str:
    return " ".join(texto.split())


def sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- la pagina

def bajar() -> str:
    respuesta = requests.get(URL, headers={"User-Agent": AGENTE}, timeout=ESPERA)
    respuesta.raise_for_status()
    respuesta.encoding = respuesta.apparent_encoding or "utf-8"
    return respuesta.text


def parsear(crudo: str, fecha: date) -> dict:
    sopa = BeautifulSoup(crudo, "html.parser")

    promos = []
    vistas = set()

    for bloque in sopa.find_all("div", class_="promo-item"):
        descripcion = bloque.find("div", class_="promo-desc")
        texto = limpiar(descripcion.get_text(" ", strip=True)) if descripcion else ""
        if not texto:
            continue

        imagen = bloque.find("img")
        id_promo = limpiar(imagen.get("alt", "")) if imagen else ""
        url_imagen = imagen.get("src") if imagen else None

        # Los carruseles suelen repetir slides para que el loop sea
        # continuo. Si el mismo id y el mismo texto aparecen dos veces,
        # es la misma promo.
        clave = (id_promo, texto)
        if clave in vistas:
            continue
        vistas.add(clave)

        promos.append(
            {
                "id_promo": id_promo or None,
                "imagen": url_imagen,
                "texto": texto,
            }
        )

    return {
        "cadena": "La Reina",
        "fecha_extraccion": fecha.isoformat(),
        "cantidad": len(promos),
        "promos": promos,
    }


# ------------------------------------------------------------- las imagenes

def urls_de_la_imagen(url: str) -> list[str]:
    sin_medida = re.sub(r"-\d{2,4}x\d{2,4}(?=\.\w+$)", "", url)
    return [sin_medida, url] if sin_medida != url else [url]


def bajar_imagen(url: str, destino: Path) -> Path | None:
    if destino.exists():
        return destino

    for candidata in urls_de_la_imagen(url):
        try:
            respuesta = requests.get(candidata, headers={"User-Agent": AGENTE}, timeout=ESPERA)
            respuesta.raise_for_status()
        except Exception:
            continue
        destino.write_bytes(respuesta.content)
        return destino

    print(f"    no pude bajar la imagen: {url}")
    return None


_cliente_vision = None


def cliente_vision():
    # Perezoso: si el cliente se crea al importar, el script no arranca
    # cuando faltan las credenciales.
    global _cliente_vision
    if _cliente_vision is None:
        _cliente_vision = vision.ImageAnnotatorClient()
    return _cliente_vision


def leer_imagen(archivo: Path) -> str:
    imagen = vision.Image(content=archivo.read_bytes())
    respuesta = cliente_vision().text_detection(image=imagen)

    if respuesta.error.message:
        raise RuntimeError(f"Vision fallo: {respuesta.error.message}")

    return respuesta.full_text_annotation.text if respuesta.full_text_annotation else ""


def porcentajes_de(texto: str) -> list[int]:

    pegados = {int(n) for n in re.findall(r"(\d{1,2})\s*%", texto)}

    if texto.count("%") > len(pegados):
        pegados |= {
            int(n) for n in re.findall(r"\b(\d{2})\b", texto) if int(n) % 5 == 0
        }

    return sorted(c for c in pegados if 5 <= c <= 50)


def dias_de(texto: str) -> list[str]:
    limpio = sin_acentos(texto).lower()
    dias = [d for d in DIAS_SEMANA if d.lower() in limpio]
    if dias:
        return dias
    # "TODOS LOS DIAS" en el cartel. Vision a veces deforma alguna letra
    # ("TODOŞ"), asi que alcanza con reconocer el final de la frase.
    return ["Todos"] if "los dias" in limpio else []


def porcentaje_del_texto(texto: str) -> int | None:
    encontrado = re.search(r"(\d{1,2})\s*%", texto or "")
    return int(encontrado.group(1)) if encontrado else None


def leer_las_imagenes(datos: dict) -> tuple[int, int]:
    IMAGENES.mkdir(parents=True, exist_ok=True)
    print("\nleyendo las imagenes con Vision:")

    coinciden = discrepan = 0

    for promo in datos["promos"]:
        url = promo.get("imagen")
        if not url:
            continue

        nombre = re.sub(r"[^A-Za-z0-9]+", "_", promo.get("id_promo") or "promo")
        extension = Path(url).suffix or ".webp"
        local = bajar_imagen(url, IMAGENES / f"{nombre}{extension}")
        if local is None:
            continue

        crudo = leer_imagen(local)
        promo["ocr_texto"] = limpiar(crudo)
        promo["ocr_dias"] = dias_de(crudo)

        # Varios carteles muestran mas de un porcentaje, uno por segmento
        # ("20% plan inicial, 25% turbo, 30% epico"). Se guardan todos, y
        # como principal va el menor: es el que le toca a cualquiera, y
        # quedarse corto es mejor error que prometer de mas.
        todos = porcentajes_de(crudo)
        promo["ocr_porcentajes"] = todos
        promo["ocr_porcentaje"] = min(todos) if todos else None

        en_texto = porcentaje_del_texto(promo["texto"])
        marca = ""
        if en_texto is not None:
            # Alcanza con que la imagen contenga ese numero: un cartel
            # puede tener dos porcentajes y elegir uno no es leer mal.
            if en_texto in set(todos):
                coinciden += 1
                marca = "verificado"
            else:
                discrepan += 1
                marca = f"NO COINCIDE (el texto dice {en_texto})"

        print(
            f"  {promo['id_promo']:<10} "
            f"{str(promo['ocr_porcentaje']):>4}%   "
            f"{','.join(promo['ocr_dias']) or '-':<26} {marca}"
        )

    return coinciden, discrepan


# ------------------------------------------------------------ verificacion

def comparar_con_la_verdad(datos: dict) -> None:
    #tests/verdad_lareina.json tiene los valores leidos a ojo de cada cartel. 
    
    if not VERDAD.exists():
        return

    with VERDAD.open(encoding="utf-8") as f:
        esperado = json.load(f)

    aciertos = fallos = 0
    print("\ncontra el set de verdad:")

    for promo in datos["promos"]:
        real = esperado.get(promo["id_promo"])
        if not real:
            continue

        leido = promo.get("ocr_porcentajes") or []
        bien = leido == real["porcentajes"]
        aciertos += bien
        fallos += not bien

        if not bien:
            print(f"  {promo['id_promo']:<10} leyo {leido}  deberia ser {real['porcentajes']}")

    print(f"  {aciertos} de {aciertos + fallos} correctas")


# ---------------------------------------------------------------------------

def main() -> None:
    hoy = date.today()
    DESTINO.mkdir(parents=True, exist_ok=True)

    crudo = bajar()

    # Guardamos el HTML tal cual vino, para poder reparsear sin volver a
    # pedirle nada al sitio si despues cambiamos el parser.
    (DESTINO / f"{hoy.isoformat()}.html").write_text(crudo, encoding="utf-8")

    datos = parsear(crudo, hoy)

    if datos["cantidad"] == 0:
        raise SystemExit(
            "Bajo la pagina pero no encontre ninguna promo.\n"
            "Cambio el HTML: revisar el .html crudo antes de seguir."
        )

    print(f"promos: {datos['cantidad']}")

    coinciden, discrepan = leer_las_imagenes(datos)

    archivo = DESTINO / f"{hoy.isoformat()}.json"
    archivo.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nverificacion contra el texto: {coinciden} coinciden, {discrepan} no")
    comparar_con_la_verdad(datos)
    print(f"\narchivo: {archivo}")


if __name__ == "__main__":
    main()