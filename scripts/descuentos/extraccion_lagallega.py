#Baja los beneficios de La Gallega: los siete dias mas las promos permanentes.

from __future__ import annotations
import html
import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE = "https://www.lagallega.com.ar"
PAGINA_CON_SESION = f"{BASE}/Beneficios.asp"
AGENTE = "RosarioVivo/1.0 (proyecto de portfolio)"
ESPERA = 20
PAUSA = 2
DESTINO = Path("data/raw/descuentos/lagallega")


def abrir_sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers["User-Agent"] = AGENTE
    respuesta = sesion.get(PAGINA_CON_SESION, timeout=ESPERA)
    respuesta.raise_for_status()
    return sesion


def bajar_dia(sesion: requests.Session, numero: int) -> str | None:
    respuesta = sesion.get(f"{BASE}/PromoxDia.asp?Dia={numero}", timeout=ESPERA)
    respuesta.raise_for_status()
    respuesta.encoding = respuesta.apparent_encoding or "utf-8"
    return None if "login.asp" in respuesta.text else respuesta.text


def limpiar(texto: str) -> str:
    return " ".join(texto.split())


def sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def id_de_la_imagen(bloque) -> tuple[str | None, str | None]:
    imagen = bloque.find("img")
    if imagen is None:
        return None, None
    ruta = imagen.get("src", "")
    encontrado = re.search(r"/(\d+)\.\w+$", ruta)
    return (encontrado.group(1) if encontrado else None), ruta


def parsear(crudo: str, fecha: date) -> dict:
    sopa = BeautifulSoup(crudo, "html.parser")

    activo = sopa.find("div", class_="DiaOpAct")
    dia = html.unescape(activo.get_text(strip=True)) if activo else None

    promos = []
    for bloque in sopa.find_all("div", class_="conteProDia"):
        # La letra chica vive DENTRO del texto principal. La sacamos del
        # arbol primero para que los dos textos no se mezclen.
        chica = bloque.find(id="Detlatar2")
        letra_chica = limpiar(chica.get_text(" ", strip=True)) if chica else ""
        if chica is not None:
            chica.extract()

        principal = bloque.find(id="Detlatar")
        texto = limpiar(principal.get_text(" ", strip=True)) if principal else ""
        if not texto:
            continue

        id_promo, imagen = id_de_la_imagen(bloque)
        promos.append(
            {
                "id_promo": id_promo,
                "imagen": imagen,
                "texto": texto,
                "letra_chica": letra_chica,
            }
        )

    return {
        "cadena": "La Gallega",
        "fecha_extraccion": fecha.isoformat(),
        "dia": dia,
        "cantidad": len(promos),
        "promos": promos,
    }


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    hoy = date.today()

    sesion = abrir_sesion()
    guardados: dict[str, int] = {}
    problemas = []

    for numero in range(8):
        if numero:
            time.sleep(PAUSA)

        crudo = bajar_dia(sesion, numero)
        if crudo is None:
            problemas.append((numero, "redirigio al login"))
            continue

        datos = parsear(crudo, hoy)
        dia = datos.get("dia")

        if not dia or datos["cantidad"] == 0:
            problemas.append((numero, "sin promos o sin dia"))
            continue
        if dia in guardados:
            problemas.append((numero, f"{dia} ya estaba"))
            continue

        nombre = "dia_" + sin_acentos(dia).lower().replace(" ", "_")
        (DESTINO / f"{nombre}.json").write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        guardados[dia] = datos["cantidad"]
        print(f"  Dia={numero}  {dia:<18} {datos['cantidad']} promos")

    print(f"\ndias guardados: {len(guardados)}")

    if problemas:
        print("\nno se pudieron leer:")
        for numero, motivo in problemas:
            print(f"  Dia={numero}  {motivo}")


if __name__ == "__main__":
    main()