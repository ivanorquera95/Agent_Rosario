
#Baja los descuentos publicados por descuentito.ar.
#Fuente: https://github.com/nuloinc/descuentito-data
#Es un JSON por cadena, actualizado por un tercero. NO es una API oficial: hay que asumir que puede romperse o dejar de actualizarse

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://raw.githubusercontent.com/nuloinc/descuentito-data/main"
ZONA_ROSARIO = ZoneInfo("America/Argentina/Buenos_Aires")
DESTINO = Path("./data/raw/descuentos")
# El nombre del archivo en el repo -> como se llama la cadena en nuestros datos
# de precios, para poder cruzarlas despues.
CADENAS = {
    "carrefour": "Hipermercado Carrefour",
    "coto": "COTO CICSA",
    "dia": "Supermercados DIA",
    "jumbo": "Jumbo",
}
# Coto no esta en el agregador (sus promos ahi son de julio y estan vencidas),
# pero publica su propia API. La URL sale de mirar la pestaña Network al abrir
# coto.com.ar/descuentos: la pagina se arma con JavaScript, pero por debajo
# pide este JSON.
URL_COTO = (
    "https://www.coto.com.ar/rest/model/atg/actors/cProfileActor/"
    "getPromocionesMulticanal?enviroment=ag&pushSite=CotoDigital"
    "&_dynSessConf=-3991438366773056860"
)
# Identificarse es lo minimo al pegarle a la web de un comercio, igual que en
# el scraper de la agenda.
HEADERS = {"User-Agent": "RosarioVivo/1.0 (proyecto de portfolio)"}
# Si el repo no se actualiza hace mas de esto, algo pasa y el agente deberia
# saberlo antes de recomendar un descuento que ya vencio.
DIAS_PARA_CONSIDERARLO_VIEJO = 7


def ahora():
    return datetime.now(ZONA_ROSARIO)


def bajar(nombre_archivo):
    url = f"{BASE}/{nombre_archivo}.json"
    respuesta = requests.get(url, timeout=30)
    respuesta.raise_for_status()
    return respuesta.json(), respuesta.headers.get("last-modified")

def bajar_coto():
    #Promociones bancarias de Coto, de su propia API.

    respuesta = requests.get(URL_COTO, headers=HEADERS, timeout=30)
    respuesta.raise_for_status()
    datos = respuesta.json()

    if datos.get("codigoError") not in ("0", 0, None):
        raise RuntimeError(f"Coto respondió codigoError={datos.get('codigoError')}")

    promociones = (datos.get("result") or {}).get("promocionesDigitales") or []
    return datos, promociones

def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    fecha_extraccion = ahora()

    total = 0
    fallidas = []

    for archivo, cadena in CADENAS.items():
        try:
            datos, ultima_modificacion = bajar(archivo)
        except requests.RequestException as e:
            print(f"  [!] {cadena}: no se pudo bajar ({e})")
            fallidas.append(cadena)
            continue

        promociones = datos if isinstance(datos, list) else datos.get("promotions", datos)
        cantidad = len(promociones) if isinstance(promociones, list) else 0

        salida = DESTINO / f"{archivo}.json"
        salida.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"  {cadena:<24} {cantidad:>4} promocion(es)"
              f"   ultima modificacion: {ultima_modificacion or 's/d'}")
        total += cantidad

    (DESTINO / "extraccion.txt").write_text(
        f"fecha_extraccion={fecha_extraccion.isoformat(timespec='seconds')}\n"
        f"fuente={BASE}\n"
        f"cadenas={','.join(CADENAS)}\n",
        encoding="utf-8",
    )
    try:
        crudo_coto, promos_coto = bajar_coto()
        (DESTINO / "coto_api.json").write_text(
            json.dumps(crudo_coto, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  {'COTO CICSA (API propia)':<24} {len(promos_coto):>4} promocion(es)")
        total += len(promos_coto)
    except (requests.RequestException, RuntimeError) as e:
        print(f"  [!] Coto (API propia): {e}")
        fallidas.append("COTO CICSA (API propia)")

    print(f"\n{total} promociones en total, de {len(CADENAS) - len(fallidas)} cadena(s)")
    print(f"Fecha de extracción: {fecha_extraccion.isoformat(timespec='seconds')}")

    if fallidas:
        print(f"\n[!] No se pudieron bajar: {', '.join(fallidas)}")


if __name__ == "__main__":
    main()