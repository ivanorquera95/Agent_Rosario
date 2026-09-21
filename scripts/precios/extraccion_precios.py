#Descarga el dataset de precios SEPA y lo descomprime.

import sys
sys.stdout.reconfigure(encoding="utf-8")
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

API_URL = "https://datos.produccion.gob.ar/api/3/action/package_show"
DATASET_ID = "sepa-precios"
ZONA_ROSARIO = ZoneInfo("America/Argentina/Buenos_Aires")

DESTINO = Path("./data/raw/precios")
ARCHIVO_METADATOS = DESTINO / "extraccion.txt"


def ahora():
    return datetime.now(ZONA_ROSARIO).isoformat(timespec="seconds")


def normalizar_texto(texto):
    return (texto or "").strip().lower()


def extraer_fecha_de_descripcion(descripcion):
    # Las descripciones traen la fecha del archivo en formato ISO
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", descripcion or "")
    if not match:
        return None
    return datetime.strptime(match.group(0), "%Y-%m-%d").date()


def limpiar_destino():
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True, exist_ok=True)


def buscar_recurso_mas_reciente():
    #El catálogo publica un ZIP por día. La URL cambia todos los días, así que se consulta cuál es el más reciente en vez de fijarla.
    
    respuesta = requests.get(API_URL, params={"id": DATASET_ID}, timeout=30)
    respuesta.raise_for_status()
    datos = respuesta.json()

    if not datos.get("success"):
        raise RuntimeError("La API de datos.produccion.gob.ar respondió success=False")

    candidatos = []
    for recurso in datos["result"]["resources"]:
        if (recurso.get("format") or "").upper() != "ZIP":
            continue
        fecha = extraer_fecha_de_descripcion(recurso.get("description", ""))
        if fecha:
            candidatos.append((fecha, recurso))

    if not candidatos:
        raise RuntimeError("No pude leer la fecha de ningún recurso ZIP del dataset")

    candidatos.sort(key=lambda par: par[0], reverse=True)
    return candidatos[0]


def descargar(recurso, fecha):
    destino = DESTINO / f"sepa_{fecha}.zip"

    print(f"Descargando {recurso['url']}")
    # En streaming porque el archivo pesa cientos de MB
    with requests.get(recurso["url"], stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for bloque in r.iter_content(chunk_size=8192):
                f.write(bloque)

    print(f"  {destino.name}: {destino.stat().st_size / 1_000_000:.1f} MB")
    return destino


def descomprimir_todo():
    #El ZIP nacional trae un ZIP por cadena adentro, así que se repite la pasada hasta que no queden ZIPs sin descomprimir.
    
    fallidos = []
    vacios = []

    while True:
        pendientes = [
            z for z in DESTINO.rglob("*.zip")
            if not (z.parent / z.stem).exists()
            and str(z) not in fallidos
            and str(z) not in vacios
        ]
        if not pendientes:
            break

        for ruta in pendientes:
            if ruta.stat().st_size == 0:
                # SEPA publica algunos zips en cero desde el origen
                vacios.append(str(ruta))
                continue

            carpeta = ruta.parent / ruta.stem
            try:
                with zipfile.ZipFile(ruta, "r") as z:
                    z.extractall(carpeta)
                print(f"  [ok] {ruta.name}")
            except zipfile.BadZipFile:
                fallidos.append(str(ruta))

    if vacios:
        print(f"\n[i] {len(vacios)} zip(s) vinieron vacíos desde el origen")
    if fallidos:
        print(f"\n[!] {len(fallidos)} zip(s) no se pudieron descomprimir:")
        for z in fallidos:
            print(f"    {Path(z).name}")

    return len(vacios), len(fallidos)


def resumen():
    carpetas = sorted(p for p in DESTINO.rglob("sepa_*") if p.is_dir())
    productos = list(DESTINO.rglob("productos.csv"))
    peso_gb = sum(p.stat().st_size for p in productos) / 1_000_000_000

    print(f"\nCarpetas de cadena : {len(carpetas)}")
    print(f"productos.csv      : {len(productos)} archivo(s), {peso_gb:.2f} GB")
    print(f"sucursales.csv     : {len(list(DESTINO.rglob('sucursales.csv')))}")
    print(f"comercio.csv       : {len(list(DESTINO.rglob('comercio.csv')))}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Descargar el dataset de precios SEPA")
    parser.add_argument("--conservar", action="store_true",
                        help="No borrar lo descargado antes (para reintentar)")

    args = parser.parse_args()
    fecha_extraccion = ahora()

    if not args.conservar:
        limpiar_destino()
    DESTINO.mkdir(parents=True, exist_ok=True)

    fecha, recurso = buscar_recurso_mas_reciente()
    antiguedad = (datetime.now(ZONA_ROSARIO).date() - fecha).days

    print(f"Archivo más reciente: {fecha} ({antiguedad} día(s) de antigüedad)")
    if antiguedad > 1:
        print("[!] SEPA no publicó datos de hoy")

    descargar(recurso, fecha)

    print("\nDescomprimiendo...")
    descomprimir_todo()

    resumen()

    # La fecha viaja en un archivo para que la limpieza la estampe en cada fila:
    # así se sabe de cuándo son los precios cuando se consultan.
    ARCHIVO_METADATOS.write_text(
        f"fecha_extraccion={fecha_extraccion}\nfecha_archivo_sepa={fecha}\n",
        encoding="utf-8",
    )
    print(f"\nFecha de extracción: {fecha_extraccion}")


if __name__ == "__main__":
    main()