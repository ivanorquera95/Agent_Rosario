import sys
sys.stdout.reconfigure(encoding="utf-8")
import csv
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://ws.rosario.gob.ar/ubicaciones/public"
HEADERS = {"User-Agent": "RosarioVivo/1.0 (proyecto de portfolio)"}
ZONA_ROSARIO = ZoneInfo("America/Argentina/Buenos_Aires")

SALIDA = Path("./data/raw/colectivos")
PAUSA_SEGUNDOS = 0.4
REINTENTOS = 3


def ahora():
    return datetime.now(ZONA_ROSARIO).isoformat(timespec="seconds")


def pedir(url, params=None):
    ultimo_error = None
    for intento in range(REINTENTOS):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            ultimo_error = e
            time.sleep(1 + intento)
    raise ultimo_error


def obtener_lineas():
    # nombre=all es obligatorio: sin ese parametro el endpoint devuelve 400
    return pedir(f"{BASE_URL}/lineas", {"nombre": "all"})


def obtener_detalle(id_empresa, id_linea):
    return pedir(
        f"{BASE_URL}/linea/{id_empresa}/{id_linea}",
        {"conGeometria": "true", "usarCoordenadasWGS84": "true", "conParadas": "true"},
    )


def escribir_csv(ruta, columnas, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas, quoting=csv.QUOTE_MINIMAL)
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"  {ruta}: {len(filas)} filas")


def extraer(max_lineas=None, pausa=PAUSA_SEGUNDOS):
    fecha_extraccion = ahora()

    lineas_crudas = obtener_lineas()
    if max_lineas:
        lineas_crudas = lineas_crudas[:max_lineas]
    print(f"Líneas a procesar: {len(lineas_crudas)}")

    filas_lineas = []
    filas_paradas = []
    filas_trazados = []
    fallidas = []
    sin_vuelta = []

    for i, linea in enumerate(lineas_crudas, 1):
        id_linea = linea["id"]
        id_empresa = linea["idEmpresa"]

        try:
            detalle = obtener_detalle(id_empresa, id_linea)
        except requests.RequestException as e:
            print(f"  [{i}/{len(lineas_crudas)}] {linea['nombre']}: FALLÓ ({e})")
            fallidas.append(linea["nombre"])
            continue

        filas_lineas.append({
            "id_linea": id_linea,
            "id_empresa": id_empresa,
            "nombre_empresa": linea.get("nombreEmpresa"),
            "nombre": linea.get("nombre"),
            "nombre_corto": linea.get("nombreCorto"),
            "codigo_emr": linea.get("codigoEMR"),
            "color": linea.get("color"),
            "fecha_extraccion": fecha_extraccion,
        })

        for parada in detalle.get("paradas", []):
            filas_paradas.append({
                "id_linea": id_linea,
                "id_parada": parada["id"],
                "nombre": parada.get("nombre"),
                # "OCHAVA NE" / "OCHAVA SO": la vereda, que junto al trazado
                # permite saber en que sentido para el colectivo
                "ochava": parada.get("descripcion"),
                "latitud": parada.get("latitud"),
                "longitud": parada.get("longitud"),
                "fecha_extraccion": fecha_extraccion,
            })

        puntos_linea = 0
        for sentido, clave in (("ida", "geojsonIda"), ("vuelta", "geojsonVuelta")):
            geojson = detalle.get(clave) or {}
            tramos = geojson.get("coordinates", [])
            if not tramos and sentido == "vuelta":
                sin_vuelta.append(linea["nombre"])
            for numero_tramo, tramo in enumerate(tramos):
                for orden, punto in enumerate(tramo):
                    filas_trazados.append({
                        "id_linea": id_linea,
                        "sentido": sentido,
                        "tramo": numero_tramo,
                        "orden": orden,
                        "longitud": punto[0],
                        "latitud": punto[1],
                        "fecha_extraccion": fecha_extraccion,
                    })
                    puntos_linea += 1

        print(f"  [{i}/{len(lineas_crudas)}] {linea['nombre']:<22} "
              f"{len(detalle.get('paradas', [])):>3} paradas | {puntos_linea:>4} puntos")

        time.sleep(pausa)

    print("\nGuardando:")
    escribir_csv(
        SALIDA / "lineas.csv",
        ["id_linea", "id_empresa", "nombre_empresa", "nombre", "nombre_corto",
         "codigo_emr", "color", "fecha_extraccion"],
        filas_lineas,
    )
    escribir_csv(
        SALIDA / "paradas_por_linea.csv",
        ["id_linea", "id_parada", "nombre", "ochava", "latitud", "longitud", "fecha_extraccion"],
        filas_paradas,
    )
    escribir_csv(
        SALIDA / "trazados.csv",
        ["id_linea", "sentido", "tramo", "orden", "longitud", "latitud", "fecha_extraccion"],
        filas_trazados,
    )

    print(f"\nFecha de extracción: {fecha_extraccion}")
    print(f"Líneas: {len(filas_lineas)} | Paradas: {len(filas_paradas)} | Puntos: {len(filas_trazados)}")

    if sin_vuelta:
        print(f"\n[i] {len(sin_vuelta)} línea(s) sin trazado de vuelta (¿circulares?):")
        for nombre in sin_vuelta:
            print(f"    - {nombre}")

    if fallidas:
        print(f"\n[!] {len(fallidas)} línea(s) no se pudieron traer:")
        for nombre in fallidas:
            print(f"    - {nombre}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extraer líneas, paradas y trazados de colectivos de Rosario")
    parser.add_argument("--max-lineas", type=int, default=None, help="Procesar solo las primeras N (para probar)")
    parser.add_argument("--pausa", type=float, default=PAUSA_SEGUNDOS, help="Segundos entre pedidos")

    args = parser.parse_args()
    extraer(max_lineas=args.max_lineas, pausa=args.pausa)


if __name__ == "__main__":
    main()