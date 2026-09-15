#Busca colectivos directos verificando el sentido contra el recorrido real.
#Los datos salen de extraccion_recorridos.py. Solo cubre las 53 lineas urbanas

import sys
import os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import math
from pathlib import Path

DATOS = Path("./data/raw/colectivos")
# La ochava apunta hacia donde el colectivo VIENE, no hacia donde VA.
RUMBO_OCHAVA = {
    "OCHAVA N": 0, "OCHAVA NE": 45, "OCHAVA E": 90, "OCHAVA SE": 135,
    "OCHAVA S": 180, "OCHAVA SO": 225, "OCHAVA O": 270, "OCHAVA NO": 315,
}
PUNTOS_PARA_RUMBO = 3
RADIO_ORIGEN_M = 500        # 5 cuadras hasta la parada de subida
RADIO_DESTINO_M = 800       # 8 cuadras desde la parada de bajada
MAX_DIST_PARADA_TRAZADO_M = 80   # para decidir si un sentido sirve esa parada
METROS_POR_CUADRA = 100
FACTOR_PIE = 4   # caminar 1 m "cuesta" como viajar 4 m en colectivo
TOLERANCIA_CALLE_GRADOS = 40

cache_calles = None
cache = None
cache_dobles = {}

OPUESTAS = {
    "OCHAVA N": "OCHAVA S", "OCHAVA S": "OCHAVA N",
    "OCHAVA E": "OCHAVA O", "OCHAVA O": "OCHAVA E",
    "OCHAVA NE": "OCHAVA SO", "OCHAVA SO": "OCHAVA NE",
    "OCHAVA NO": "OCHAVA SE", "OCHAVA SE": "OCHAVA NO",
}


def calle_de(nombre_parada):
    # "SAN MARTIN y URUGUAY" -> la linea circula por San Martin.
    # "URUGUAY y SAN MARTIN" es otra parada: ahi circula por Uruguay.
    return nombre_parada.split(" y ")[0].strip()


def calles_doble_mano(id_linea):
    #Si en algun punto del recorrido hay dos paradas de la misma calle con ochavas opuestas, esa calle es doble mano para esta linea.
    
    if id_linea in cache_dobles:
        return cache_dobles[id_linea]

    datos = cargar_datos()

    por_calle = {}
    for p in datos["paradas"]:
        if p["id_linea"] != id_linea:
            continue
        por_calle.setdefault(calle_de(p["nombre"]), set()).add(p["ochava"])

    dobles = {
        calle for calle, ochavas in por_calle.items()
        if any(OPUESTAS.get(o) in ochavas for o in ochavas)
    }

    cache_dobles[id_linea] = dobles
    return dobles


def distancia_metros(lat1, lon1, lat2, lon2):
    # Aproximacion plana, de sobra a escala de ciudad
    dlat = (lat1 - lat2) * 111_320
    dlon = (lon1 - lon2) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def cargar_datos(forzar_recarga=False):
    #Lee los CSV una vez por proceso y los deja indexados en memoria.
    global cache
    if cache is not None and not forzar_recarga:
        return cache

    archivos = ["lineas.csv", "paradas_por_linea.csv", "trazados.csv"]
    faltantes = [a for a in archivos if not (DATOS / a).exists()]
    if faltantes:
        raise FileNotFoundError(
            f"Faltan {faltantes} en {DATOS.resolve()}. "
            "Corré antes: uv run .\\scripts\\colectivos\\extraccion_recorridos.py"
        )

    lineas = {}
    with open(DATOS / "lineas.csv", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            lineas[fila["id_linea"]] = fila

    paradas = []
    with open(DATOS / "paradas_por_linea.csv", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            paradas.append({
                "id_linea": fila["id_linea"],
                "id_parada": fila["id_parada"],
                "nombre": fila["nombre"],
                "ochava": fila["ochava"],
                "latitud": float(fila["latitud"]),
                "longitud": float(fila["longitud"]),
            })

    # (id_linea, sentido) -> lista de (lat, lon) en orden de recorrido
    trazados = {}
    with open(DATOS / "trazados.csv", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            clave = (fila["id_linea"], fila["sentido"])
            trazados.setdefault(clave, []).append(
                (float(fila["latitud"]), float(fila["longitud"]))
            )

    fecha = next(iter(lineas.values()), {}).get("fecha_extraccion")

    cache = {"lineas": lineas, "paradas": paradas, "trazados": trazados, "fecha_extraccion": fecha}
    return cache


def paradas_cerca(latitud, longitud, radio_metros):
    #Paradas dentro del radio, con la distancia a pie.
    datos = cargar_datos()
    cercanas = []
    for parada in datos["paradas"]:
        d = distancia_metros(latitud, longitud, parada["latitud"], parada["longitud"])
        if d <= radio_metros:
            cercanas.append({**parada, "distancia_m": d})
    return cercanas


def posicion_en_trazado(trazado, latitud, longitud):
    #Indice del punto del trazado mas cercano, y a que distancia quedo.
    mejor_indice, mejor_distancia = None, float("inf")
    for i, (lat, lon) in enumerate(trazado):
        d = distancia_metros(latitud, longitud, lat, lon)
        if d < mejor_distancia:
            mejor_indice, mejor_distancia = i, d
    return mejor_indice, mejor_distancia

def rumbo_grados(lat1, lon1, lat2, lon2):
    dlat = lat2 - lat1
    dlon = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.degrees(math.atan2(dlon, dlat)) % 360

def indice_calles():
    #Todas las paradas agrupadas por la calle que les da nombre.
    global cache_calles
    if cache_calles is None:
        indice = {}
        vistas = set()
        for p in cargar_datos()["paradas"]:
            if p["id_parada"] in vistas:
                continue
            vistas.add(p["id_parada"])
            indice.setdefault(calle_de(p["nombre"]), []).append((p["latitud"], p["longitud"]))
        cache_calles = indice
    return cache_calles


def rumbo_de_la_calle(nombre_parada, latitud, longitud):
    #Orientacion de la calle en ese punto, sacada de la parada mas cercana de la misma calle. Devuelve None si esa calle tiene una sola parada.
    
    mejor, mejor_distancia = None, float("inf")
    for lat, lon in indice_calles().get(calle_de(nombre_parada), []):
        d = distancia_metros(latitud, longitud, lat, lon)
        if 80 <= d < mejor_distancia:
            mejor, mejor_distancia = (lat, lon), d
    if mejor is None:
        return None
    return rumbo_grados(latitud, longitud, *mejor)


def circula_por_la_calle(trazado, indice, parada):
    #True si en ese punto el colectivo avanza a lo largo de la calle. El nombre dice por donde circula la linea: "URUGUAY y SAN MARTIN".
    
    rumbo_calle = rumbo_de_la_calle(parada["nombre"], parada["latitud"], parada["longitud"])
    if rumbo_calle is None:
        return True

    j = min(indice + PUNTOS_PARA_RUMBO, len(trazado) - 1)
    if j == indice:
        return True

    rumbo_bus = rumbo_grados(*trazado[indice], *trazado[j])
    diferencia = min((rumbo_bus - rumbo_calle) % 360, (rumbo_calle - rumbo_bus) % 360)
    # La calle sirve en los dos sentidos: 0 grados o 180 grados es "va por ahi"
    return min(diferencia, abs(180 - diferencia)) <= TOLERANCIA_CALLE_GRADOS

def ochava_sirve(trazado, indice, ochava, hay_que_desambiguar):
    #True si esa parada corresponde al sentido en que avanza el colectivo.
    
    if not hay_que_desambiguar:
        return True

    rumbo_parada = RUMBO_OCHAVA.get(ochava)
    if rumbo_parada is None:
        return True

    j = min(indice + PUNTOS_PARA_RUMBO, len(trazado) - 1)
    if j == indice:
        return True

    rumbo_bus = rumbo_grados(*trazado[indice], *trazado[j])
    diferencia = min((rumbo_bus - rumbo_parada) % 360, (rumbo_parada - rumbo_bus) % 360)
    return diferencia > 90


def largo_tramo(trazado, desde, hasta):
    #Metros recorridos entre dos posiciones del trazado.
    total = 0.0
    for i in range(desde, hasta):
        total += distancia_metros(*trazado[i], *trazado[i + 1])
    return total

def buscar_directos(origen_lat, origen_lon, destino_lat, destino_lon, radio_origen=RADIO_ORIGEN_M, radio_destino=RADIO_DESTINO_M, max_opciones=10):
    #Colectivos que te llevan del origen al destino sin transbordo.

    datos = cargar_datos()

    cerca_origen = paradas_cerca(origen_lat, origen_lon, radio_origen)
    cerca_destino = paradas_cerca(destino_lat, destino_lon, radio_destino)

    if not cerca_origen:
        return {"opciones": [], "motivo": f"No hay paradas a menos de {radio_origen} m del origen."}
    if not cerca_destino:
        return {"opciones": [], "motivo": f"No hay paradas a menos de {radio_destino} m del destino."}

    por_linea_origen = {}
    for p in cerca_origen:
        por_linea_origen.setdefault(p["id_linea"], []).append(p)

    por_linea_destino = {}
    for p in cerca_destino:
        por_linea_destino.setdefault(p["id_linea"], []).append(p)

    comunes = set(por_linea_origen) & set(por_linea_destino)

    opciones = []
    descartadas_por_sentido = 0

    for id_linea in comunes:
        mejor = None
        dobles = calles_doble_mano(id_linea)
        for sentido in ("ida", "vuelta"):
            trazado = datos["trazados"].get((id_linea, sentido))
            if not trazado:
                continue

            # Distancias acumuladas: asi el largo entre dos posiciones es una resta, y no hay que recorrer el trazado en cada par.
            acumuladas = [0.0]
            for i in range(len(trazado) - 1):
                acumuladas.append(acumuladas[-1] + distancia_metros(*trazado[i], *trazado[i + 1]))

            # Posicion de cada parada candidata sobre ESTE trazado, una sola vez
            subidas = []
            for p in por_linea_origen[id_linea]:
                i, d = posicion_en_trazado(trazado, p["latitud"], p["longitud"])
                if (d <= MAX_DIST_PARADA_TRAZADO_M
                        and circula_por_la_calle(trazado, i, p)
                        and ochava_sirve(trazado, i, p["ochava"], calle_de(p["nombre"]) in dobles)):
                    subidas.append((i, p))

            bajadas = []
            for p in por_linea_destino[id_linea]:
                i, d = posicion_en_trazado(trazado, p["latitud"], p["longitud"])
                if (d <= MAX_DIST_PARADA_TRAZADO_M
                        and circula_por_la_calle(trazado, i, p)
                        and ochava_sirve(trazado, i, p["ochava"], calle_de(p["nombre"]) in dobles)):
                    bajadas.append((i, p))

            for i_sub, subida in subidas:
                for i_baj, bajada in bajadas:
                    if subida["id_parada"] == bajada["id_parada"]:
                        continue

                    # El chequeo que importa: la bajada tiene que venir DESPUES
                    # de la subida sobre el mismo recorrido.
                    if i_baj <= i_sub:
                        descartadas_por_sentido += 1
                        continue

                    metros_bus = acumuladas[i_baj] - acumuladas[i_sub]
                    metros_pie = subida["distancia_m"] + bajada["distancia_m"]
                    costo = metros_pie * FACTOR_PIE + metros_bus

                    if mejor is not None and costo >= mejor["costo"]:
                        continue

                    mejor = {
                        "linea": datos["lineas"][id_linea]["nombre"],
                        "id_linea": id_linea,
                        "sentido": sentido,
                        "parada_subida": subida["nombre"],
                        "id_parada_subida": subida["id_parada"],
                        "parada_subida_ochava": subida["ochava"],
                        "cuadras_hasta_parada": round(subida["distancia_m"] / METROS_POR_CUADRA),
                        "parada_bajada": bajada["nombre"],
                        "id_parada_bajada": bajada["id_parada"],
                        "parada_bajada_ochava": bajada["ochava"],
                        "cuadras_desde_bajada": round(bajada["distancia_m"] / METROS_POR_CUADRA),
                        "metros_en_colectivo": round(metros_bus),
                        "cuadras_a_pie_total": round(metros_pie / METROS_POR_CUADRA),
                        "costo": costo,
                    }

        if mejor:
            opciones.append(mejor)

    opciones.sort(key=lambda o: o["costo"])

    return {
        "opciones": opciones[:max_opciones],
        "total_encontradas": len(opciones),
        "descartadas_por_sentido": descartadas_por_sentido,
        "lineas_evaluadas": len(comunes),
        "fecha_datos": datos["fecha_extraccion"],
        "motivo": None if opciones else "Ninguna línea urbana une esos dos puntos sin transbordo.",
    }


def main():
    import argparse
    from colectivos.colectivos_gran_rosario import geocodificar_direccion

    parser = argparse.ArgumentParser(description="Colectivos directos, con el sentido verificado")
    parser.add_argument("origen")
    parser.add_argument("destino")
    parser.add_argument("--radio-origen", type=int, default=RADIO_ORIGEN_M)
    parser.add_argument("--radio-destino", type=int, default=RADIO_DESTINO_M)

    args = parser.parse_args()

    o = geocodificar_direccion(args.origen)
    d = geocodificar_direccion(args.destino)

    if o is None:
        print(f"No pude encontrar el origen '{args.origen}'.")
        return
    if d is None:
        print(f"No pude encontrar el destino '{args.destino}'.")
        return

    print(f"De: {o['nombre']}")
    print(f"A:  {d['nombre']}")

    resultado = buscar_directos(
        o["latitud"], o["longitud"], d["latitud"], d["longitud"],
        radio_origen=args.radio_origen, radio_destino=args.radio_destino,
    )

    if not resultado["opciones"]:
        print(f"\n{resultado['motivo']}")
        if resultado.get("descartadas_por_sentido"):
            print(f"({resultado['descartadas_por_sentido']} descartada(s) por ir en sentido contrario)")
        return

    print(f"\n{resultado['total_encontradas']} directo(s) | "
          f"{resultado['descartadas_por_sentido']} descartado(s) por sentido | "
          f"datos del {resultado['fecha_datos']}\n")

    for o_ in resultado["opciones"]:
        print(f"Línea {o_['linea']} ({o_['sentido']})")
        print(f" - Subís en: {o_['parada_subida']} [{o_['parada_subida_ochava']}] "
              f"({o_['cuadras_hasta_parada']} cuadras a pie)")
        print(f" - Bajás en: {o_['parada_bajada']} [{o_['parada_bajada_ochava']}] "
              f"({o_['cuadras_desde_bajada']} cuadras a pie)")
        print(f" - En colectivo: {o_['metros_en_colectivo'] / 1000:.1f} km\n")


if __name__ == "__main__":
    main()