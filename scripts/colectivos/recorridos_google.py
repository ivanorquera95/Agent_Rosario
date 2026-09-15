#Viajes en colectivo via Google Routes API. Google conoce los interurbanos que la API municipal no tiene, y cubre todo el area metropolitana. 
#En cambio solo trae horarios de tabla, no arribos en vivo.
#Tambien arma combinaciones que un local no haria por eso cada opcion pasa por un chequeo de sentido contra los trazados municipales. 
#Routes API se factura: 10.000 llamadas gratis por mes y despues USD 5 por mil.

import sys
import os
import re
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from dotenv import load_dotenv

from colectivos.recorridos import (
    cargar_datos,
    posicion_en_trazado,
    ochava_sirve,
    circula_por_la_calle,
    calle_de,
    calles_doble_mano,
    distancia_metros,
    MAX_DIST_PARADA_TRAZADO_M,
)

# Las empresas interurbanas no cargan el nombre de la parada y Google devuelve
# su codigo interno: "ROS03", "CAPB04". Para el usuario no significa nada.
PATRON_CODIGO_PARADA = re.compile(r"^[A-Z]{2,6}[-_]?\d{1,3}$")
MAX_DIST_REFERENCIA_M = 250
MAX_DIST_MATCH_PARADA_M = 60
RADIO_PARADA_ALTERNATIVA_M = 700

load_dotenv()

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

CAMPOS = ",".join([
    "routes.duration",
    "routes.legs.steps.travelMode",
    "routes.legs.steps.distanceMeters",
    "routes.legs.steps.transitDetails",
])

METROS_POR_CUADRA = 100


def error(mensaje, instruccion, **extra):
    resultado = {"error": mensaje, "instruccion_para_el_agente": instruccion}
    resultado.update(extra)
    return resultado


def coordenadas(parada):
    punto = (parada or {}).get("location", {}).get("latLng", {})
    lat, lon = punto.get("latitude"), punto.get("longitude")
    return (lat, lon) if lat is not None and lon is not None else None


def paradas_de_la_linea(id_linea, punto):
    #Paradas de esa linea que estan sobre ese punto, con su ochava.
    datos = cargar_datos()
    return [
        p for p in datos["paradas"]
        if p["id_linea"] == id_linea
        and distancia_metros(punto[0], punto[1], p["latitud"], p["longitud"]) <= MAX_DIST_MATCH_PARADA_M
    ]
    
    
def describir_parada(nombre, punto):
    #Si el nombre es un codigo interno, busca una esquina conocida cerca.
    #Las paradas municipales cubren Rosario pero no las localidades vecinas, asi que afuera no va a haber ninguna cerca.
    
    nombre = (nombre or "").strip()

    if not PATRON_CODIGO_PARADA.match(nombre) or not punto:
        return {"nombre": nombre, "es_codigo": False, "referencia": None}

    mejor, mejor_distancia = None, float("inf")
    for p in cargar_datos()["paradas"]:
        d = distancia_metros(punto[0], punto[1], p["latitud"], p["longitud"])
        if d < mejor_distancia:
            mejor, mejor_distancia = p, d

    if mejor is None or mejor_distancia > MAX_DIST_REFERENCIA_M:
        return {"nombre": nombre, "es_codigo": True, "referencia": None}

    return {
        "nombre": nombre,
        "es_codigo": True,
        "referencia": mejor["nombre"],
        "metros_a_la_referencia": round(mejor_distancia),
    }
    
    
def id_parada_municipal(nombre_linea, punto):
    #Busca el id municipal de la parada que Google devolvio por coordenadas. Sirve para pedir el arribo en vivo del primer tramo cuando es una linea urbana. 
    
    if not punto:
        return None

    datos = cargar_datos()
    ids = [
        id_linea for id_linea, linea in datos["lineas"].items()
        if (nombre_linea or "").upper() in (
            linea["nombre"].upper(), linea["nombre_corto"].upper(), linea["codigo_emr"].upper()
        )
    ]
    if not ids:
        return None

    mejor, mejor_distancia = None, float("inf")
    for p in datos["paradas"]:
        if p["id_linea"] not in ids:
            continue
        d = distancia_metros(punto[0], punto[1], p["latitud"], p["longitud"])
        if d < mejor_distancia:
            mejor, mejor_distancia = p, d

    if mejor is None or mejor_distancia > MAX_DIST_MATCH_PARADA_M:
        return None
    return mejor["id_parada"]
 
def verificar_sentido(nombre_linea, subida, bajada):
    #Tres resultados posibles, y la diferencia importa:
    #  - correcto: ubique las dos paradas y la bajada viene despues de la subida
    #  - sentido_invertido: las ubique, pero el orden o la ochava dicen que no
    #  - no_verificable: no pude ubicarlas. Puede ser un interurbano
    if not subida or not bajada:
        return "no_verificable"

    datos = cargar_datos()

    ids = [
        id_linea for id_linea, linea in datos["lineas"].items()
        if (nombre_linea or "").upper() in (
            linea["nombre"].upper(), linea["nombre_corto"].upper(), linea["codigo_emr"].upper()
        )
    ]
    if not ids:
        return "no_verificable"

    encontro_las_dos_paradas = False
    bajada_en_alguna_rama = False
    subida_en_alguna_rama = False

    for id_linea in ids:
        dobles = calles_doble_mano(id_linea)
        candidatas_sub = paradas_de_la_linea(id_linea, subida)
        candidatas_baj = paradas_de_la_linea(id_linea, bajada)

        if not candidatas_sub or not candidatas_baj:
            continue

        for sentido in ("ida", "vuelta"):
            trazado = datos["trazados"].get((id_linea, sentido))
            if not trazado:
                continue

            posibles_sub = []
            posibles_baj = []

            for p in candidatas_sub:
                i, d = posicion_en_trazado(trazado, p["latitud"], p["longitud"])
                if d > MAX_DIST_PARADA_TRAZADO_M or not circula_por_la_calle(trazado, i, p):
                    continue
                if ochava_sirve(trazado, i, p["ochava"], calle_de(p["nombre"]) in dobles):
                    posibles_sub.append(i)

            for p in candidatas_baj:
                i, d = posicion_en_trazado(trazado, p["latitud"], p["longitud"])
                if d > MAX_DIST_PARADA_TRAZADO_M or not circula_por_la_calle(trazado, i, p):
                    continue
                if ochava_sirve(trazado, i, p["ochava"], calle_de(p["nombre"]) in dobles):
                    posibles_baj.append(i)

            if posibles_sub:
                subida_en_alguna_rama = True
            if posibles_baj:
                bajada_en_alguna_rama = True

            if posibles_sub and posibles_baj:
                encontro_las_dos_paradas = True
                if any(b > s for s in posibles_sub for b in posibles_baj):
                    return "correcto"

    # Las dos en la misma rama y el orden no da: va al reves.
    if encontro_las_dos_paradas:
        return "sentido_invertido"

    # Cada una en una rama distinta: estas tomando la rama equivocada. Es el caso del 113, donde la parada de Uruguay es de la rama que baja al sur y el destino esta en la que sube.
    if subida_en_alguna_rama and bajada_en_alguna_rama:
        return "sentido_invertido"

    # Si alguna de las dos no aparece en ninguna rama, no hay con que comparar: puede ser un trazado recortado, como el del 135 en Velez Sarsfield.
    return "no_verificable"

def parada_correcta(nombre_linea, subida, bajada):
    #Cuando Google manda a una parada de la rama equivocada, busca la parada de esa misma linea, cerca, que si sirve para ese tramo.

    datos = cargar_datos()

    ids = [
        id_linea for id_linea, linea in datos["lineas"].items()
        if (nombre_linea or "").upper() in (
            linea["nombre"].upper(), linea["nombre_corto"].upper(), linea["codigo_emr"].upper()
        )
    ]

    mejor = None

    for id_linea in ids:
        dobles = calles_doble_mano(id_linea)
        candidatas_baj = paradas_de_la_linea(id_linea, bajada)
        if not candidatas_baj:
            continue

        for sentido in ("ida", "vuelta"):
            trazado = datos["trazados"].get((id_linea, sentido))
            if not trazado:
                continue

            posibles_baj = []
            for p in candidatas_baj:
                i, d = posicion_en_trazado(trazado, p["latitud"], p["longitud"])
                if d > MAX_DIST_PARADA_TRAZADO_M or not circula_por_la_calle(trazado, i, p):
                    continue
                if ochava_sirve(trazado, i, p["ochava"], calle_de(p["nombre"]) in dobles):
                    posibles_baj.append(i)

            if not posibles_baj:
                continue
            ultima_bajada = max(posibles_baj)

            for p in datos["paradas"]:
                if p["id_linea"] != id_linea:
                    continue
                metros = distancia_metros(subida[0], subida[1], p["latitud"], p["longitud"])
                if metros > RADIO_PARADA_ALTERNATIVA_M:
                    continue
                i, d = posicion_en_trazado(trazado, p["latitud"], p["longitud"])
                if d > MAX_DIST_PARADA_TRAZADO_M or not circula_por_la_calle(trazado, i, p):
                    continue
                if not ochava_sirve(trazado, i, p["ochava"], calle_de(p["nombre"]) in dobles):
                    continue
                if i >= ultima_bajada:
                    continue
                if mejor is None or metros < mejor["metros"]:
                    mejor = {
                        "nombre": p["nombre"],
                        "ochava": p["ochava"],
                        "id_parada": p["id_parada"],
                        "latitud": p["latitud"],
                        "longitud": p["longitud"],
                        "metros": round(metros),
                        "cuadras": round(metros / METROS_POR_CUADRA),
                    }

    return mejor

def buscar_viajes(origen_lat, origen_lon, destino_lat, destino_lon, max_opciones=6):
    if not API_KEY:
        return error("No está configurada GOOGLE_PLACES_API_KEY.",
                     "Decile al usuario que la búsqueda de viajes no está disponible ahora.")

    cuerpo = {
        "origin": {"location": {"latLng": {"latitude": origen_lat, "longitude": origen_lon}}},
        "destination": {"location": {"latLng": {"latitude": destino_lat, "longitude": destino_lon}}},
        "travelMode": "TRANSIT",
        "computeAlternativeRoutes": True,
        "languageCode": "es-419",
    }

    cabeceras = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": CAMPOS,
    }

    try:
        respuesta = requests.post(API_URL, json=cuerpo, headers=cabeceras, timeout=30)
        if respuesta.status_code != 200:
            detalle = respuesta.json().get("error", {}).get("message", respuesta.text[:200])
            return error(f"Google Routes rechazó la consulta ({respuesta.status_code}): {detalle}",
                         "Decile al usuario que el servicio no está disponible ahora. "
                         "NO inventes un recorrido.")
        datos = respuesta.json()
    except requests.RequestException:
        return error("No pude conectarme a Google Routes.",
                     "Decile al usuario que el servicio no está disponible ahora. "
                     "NO inventes un recorrido.")

    opciones = []

    for ruta in datos.get("routes", []):
        tramos = []
        metros_a_pie = 0

        for leg in ruta.get("legs", []):
            for paso in leg.get("steps", []):
                detalle = paso.get("transitDetails")

                if not detalle:
                    if paso.get("travelMode") == "WALK":
                        metros_a_pie += paso.get("distanceMeters", 0)
                    continue

                linea = detalle.get("transitLine", {})
                paradas = detalle.get("stopDetails", {})
                horarios = detalle.get("localizedValues", {})

                nombre = linea.get("nameShort") or linea.get("name") or "?"
                subida = coordenadas(paradas.get("departureStop"))
                bajada = coordenadas(paradas.get("arrivalStop"))

                estado = verificar_sentido(nombre, subida, bajada)
                sugerida = parada_correcta(nombre, subida, bajada) if estado == "sentido_invertido" else None

                nombre_google = (paradas.get("departureStop") or {}).get("name")
                nombre_bajada = (paradas.get("arrivalStop") or {}).get("name")

                subida_desc = describir_parada(nombre_google, subida)
                bajada_desc = describir_parada(nombre_bajada, bajada)

                tramos.append({
                    "linea": nombre,
                    "parada_subida": sugerida["nombre"] if sugerida else subida_desc["nombre"],
                    "parada_subida_ochava": sugerida["ochava"] if sugerida else None,
                    "parada_subida_es_codigo": False if sugerida else subida_desc["es_codigo"],
                    "parada_subida_referencia": None if sugerida else subida_desc["referencia"],
                    "parada_corregida": bool(sugerida),
                    "parada_que_decia_google": nombre_google if sugerida else None,
                    "parada_bajada": bajada_desc["nombre"],
                    "parada_bajada_es_codigo": bajada_desc["es_codigo"],
                    "parada_bajada_referencia": bajada_desc["referencia"],
                    "sale": horarios.get("departureTime", {}).get("time", {}).get("text"),
                    "llega": horarios.get("arrivalTime", {}).get("time", {}).get("text"),
                    "sentido_verificado": estado,
                    # Si la parada fue corregida, el arribo se pide en la
                    # corregida y no en la que daba Google.
                    "id_parada_municipal": (sugerida["id_parada"] if sugerida
                                            else id_parada_municipal(nombre, subida)),
                })

        if not tramos:
            continue

        segundos = int(str(ruta.get("duration", "0s")).rstrip("s") or 0)

        opciones.append({
            "lineas": [t["linea"] for t in tramos],
            "tramos": tramos,
            "cantidad_transbordos": max(0, len(tramos) - 1),
            "duracion_minutos": round(segundos / 60),
            "cuadras_a_pie_total": round(metros_a_pie / METROS_POR_CUADRA),
            # Si CUALQUIER tramo va en sentido invertido, la opcion es sospechosa: es el caso de tomarse la linea para el lado equivocado.
            "sentido_invertido": any(t["sentido_verificado"] == "sentido_invertido" for t in tramos),
            "tramos_no_verificables": sum(
                1 for t in tramos if t["sentido_verificado"] == "no_verificable"
            ),
            "invertidos_sin_arreglo": sum(
                1 for t in tramos
                if t["sentido_verificado"] == "sentido_invertido" and not t["parada_corregida"]
            ),
        })

    if not opciones:
        return error("Google no encontró un viaje en transporte público entre esos dos puntos.",
                     "Decíselo al usuario tal cual. NO inventes una línea ni una parada.")

    # Lo sospechoso al final; entre el resto, menos transbordos y menos tiempo
    opciones.sort(key=lambda o: (o["invertidos_sin_arreglo"] > 0, o["duracion_minutos"]))

    return {
        "fuente": "google",
        "aviso_datos": "Horarios de tabla, no arribos en vivo.",
        "opciones": opciones[:max_opciones],
        "total_encontradas": len(opciones),
    }


def imprimir(resultado):
    if resultado.get("error"):
        print(resultado["error"])
        return

    print(f"{resultado['total_encontradas']} opción(es) | {resultado['aviso_datos']}\n")

    for o in resultado["opciones"]:
        marcas = []
        if o["sentido_invertido"]:
            marcas.append("SENTIDO INVERTIDO")
        if o["tramos_no_verificables"]:
            marcas.append(f"{o['tramos_no_verificables']} tramo(s) sin verificar")
        marca = f"  [{', '.join(marcas)}]" if marcas else ""

        print(f"{' + '.join(o['lineas'])} — {o['duracion_minutos']} min, "
              f"{o['cuadras_a_pie_total']} cuadras a pie{marca}")

        for t in o["tramos"]:
            estado = {"correcto": "ok", "sentido_invertido": "corregida",
                      "no_verificable": "sin verificar"}[t["sentido_verificado"]]
            print(f"   {t['linea']}: {t['parada_subida']} ({t['sale']}) -> "
                  f"{t['parada_bajada']} ({t['llega']})  [{estado}]")
            if t["parada_corregida"]:
                print(f"      (Google decía {t['parada_que_decia_google']}, "
                      f"ahí el colectivo va para el otro lado)")


def main():
    import argparse
    from colectivos.colectivos_gran_rosario import geocodificar_direccion

    parser = argparse.ArgumentParser(description="Viajes en colectivo via Google Routes")
    parser.add_argument("origen")
    parser.add_argument("destino")

    args = parser.parse_args()

    o = geocodificar_direccion(args.origen)
    if o is None:
        print(f"No pude encontrar el origen '{args.origen}'.")
        return

    d = geocodificar_direccion(args.destino)
    if d is None:
        print(f"No pude encontrar el destino '{args.destino}'.")
        return

    print(f"De: {o['nombre']}")
    print(f"A:  {d['nombre']}\n")

    imprimir(buscar_viajes(o["latitud"], o["longitud"], d["latitud"], d["longitud"]))


if __name__ == "__main__":
    main()