import sys
import os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from colectivos.recorridos import buscar_directos
from colectivos.recorridos_google import buscar_viajes
import requests
from pyproj import Transformer
from comun.localidades import (
    dentro_del_gran_rosario,
    detectar_localidad,
    nombra_otra_ciudad,
)

BASE_URL = "https://ws.rosario.gob.ar/ubicaciones/public"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "RosarioVivo/1.0 (proyecto de portfolio)"}

MAX_PARADAS = 5
MAX_ARRIBOS_POR_LINEA = 3

# EPSG:22185 = Gauss-Krüger faja 5 (Campo Inchauspe), el sistema en el que la municipalidad devuelve x/y.
# El endpoint de paradas espera estas coordenadas proyectadas; el de viajes acepta WGS84 con usarCoordenadasWGS84=true.
a_local = Transformer.from_crs("EPSG:4326", "EPSG:22185", always_xy=True)
a_geografico = Transformer.from_crs("EPSG:22185", "EPSG:4326", always_xy=True)


def latlon_a_xy(latitud, longitud):
    return a_local.transform(longitud, latitud)


def xy_a_latlon(x, y):
    longitud, latitud = a_geografico.transform(x, y)
    return latitud, longitud


def error(mensaje, instruccion, **extra):
    resultado = {"error": mensaje, "instruccion_para_el_agente": instruccion}
    resultado.update(extra)
    return resultado


def geocodificar_con_nominatim(direccion):
    #La API de comollego SI calcula viajes a las localidades del gran Rosario, asi que lo unico que falta son las coordenadas.
    try:
        respuesta = requests.get(
            NOMINATIM_URL,
            params={"q": f"{direccion}, Santa Fe, Argentina", "format": "json", "limit": 5},
            headers=HEADERS,
            timeout=15,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.RequestException:
        return None

    for d in datos:
        latitud, longitud = float(d["lat"]), float(d["lon"])
        # Nominatim resuelve cualquier lugar del mundo: aca se acota al Gran Rosario
        if not dentro_del_gran_rosario(latitud, longitud):
            continue
        x, y = latlon_a_xy(latitud, longitud)
        return {
            "nombre": d.get("display_name", "").split(",")[0],
            "x": x, "y": y,
            "latitud": latitud, "longitud": longitud,
            "fuente": "nominatim",
        }
        
    return None


def geocodificar_direccion(texto):
    if nombra_otra_ciudad(texto):
        return None

    # Si el usuario nombro una localidad del Gran Rosario a pesar de nombrar una calle conocida por Rosario 
    # ("Urquiza 1000, Funes" -> Urquiza 1000 de Rosario, a 12 km).
    if detectar_localidad(texto):
        return geocodificar_con_nominatim(texto)

    try:
        respuesta = requests.get(
            f"{BASE_URL}/geojson/ubicaciones",
            params={"term": texto, "extendido": "true", "conOtrasLocalidades": "false"},
            headers=HEADERS,
            timeout=15,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.RequestException:
        return geocodificar_con_nominatim(texto)

    con_coordenadas = [f for f in datos.get("features", []) if f.get("geometry")]
    if not con_coordenadas:
        return geocodificar_con_nominatim(texto)

    mejor = con_coordenadas[0]
    coordenadas = mejor["geometry"]["coordinates"]

    # Los parques y las plazas vienen como poligono, no como punto. Asi que se aplana hasta llegar a los pares de numeros y se toma el centro.
    def aplanar(estructura):
        if isinstance(estructura, (list, tuple)) and len(estructura) == 2 \
                and all(isinstance(v, (int, float)) for v in estructura):
            return [tuple(estructura)]
        if isinstance(estructura, (list, tuple)):
            return [punto for sub in estructura for punto in aplanar(sub)]
        return []

    puntos = aplanar(coordenadas)
    if not puntos:
        return geocodificar_con_nominatim(texto)

    x = sum(p[0] for p in puntos) / len(puntos)
    y = sum(p[1] for p in puntos) / len(puntos)
    latitud, longitud = xy_a_latlon(x, y)

    return {
        "nombre": mejor["properties"].get("name") or mejor["properties"].get("direccion", texto),
        "x": x, "y": y,
        "latitud": latitud, "longitud": longitud,
        "fuente": "municipal",
    }


def paradas_cercanas(x, y, radio_metros=300):
    # Este endpoint NO acepta usarCoordenadasWGS84: espera x/y proyectadas.
    respuesta = requests.get(
        f"{BASE_URL}/paradas",
        params={"xOrigen": x, "yOrigen": y, "radio": radio_metros},
        headers=HEADERS,
        timeout=15,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def cuando_llega(id_parada, id_linea=None):
    params = {"parada": id_parada}
    if id_linea:
        params["linea"] = id_linea
    respuesta = requests.get(f"{BASE_URL}/cuandollega", params=params, headers=HEADERS, timeout=15)
    respuesta.raise_for_status()
    return respuesta.json()


def proximos_colectivos(lugar, linea=None, radio_metros=300):
    ubicacion = geocodificar_direccion(lugar)

    if ubicacion is None:
        if nombra_otra_ciudad(lugar):
            return error(
                f"'{lugar}' es otra ciudad. Solo cubro Rosario y el Gran Rosario.",
                "Decíselo al usuario tal cual. NO busques alternativas ni inventes paradas.",
            )
        return error(
            f"No pude encontrar '{lugar}'.",
            "Pedile al usuario que lo escriba de otra forma. NO inventes una parada.",
        )

    try:
        paradas = paradas_cercanas(ubicacion["x"], ubicacion["y"], radio_metros)
    except requests.RequestException:
        return error("No pude conectarme al servicio de colectivos.",
                     "Decile al usuario que el servicio no está disponible ahora. "
                     "NO inventes horarios.")

    if not paradas:
        return error(
            f"No hay paradas de colectivo a menos de {radio_metros} metros de {ubicacion['nombre']}.",
            "Decíselo al usuario. Podés ofrecerle buscar con un radio más grande.",
            ubicacion_resuelta=ubicacion["nombre"],
        )

    resultado_paradas = []
    paradas_con_error = 0

    for parada in paradas[:MAX_PARADAS]:
        try:
            arribos_lineas = cuando_llega(parada["id"])
        except requests.RequestException:
            # La API municipal devuelve 500 para algunas paradas puntuales (por ejemplo la 7314). Se saltea esa y no se pierden las demas.
            paradas_con_error += 1
            continue

        if linea:
            buscada = linea.lower()
            arribos_lineas = [
                al for al in arribos_lineas
                if buscada in al["linea"]["nombre"].lower()
                or buscada == (al["linea"].get("codigoEMR") or "").lower()
            ]

        if not arribos_lineas:
            continue

        lineas_info = []
        for al in arribos_lineas:
            proximos = sorted(al.get("arribos", []), key=lambda a: a["arriboEnMinutos"])
            proximos = proximos[:MAX_ARRIBOS_POR_LINEA]
            lineas_info.append({
                # La empresa no se devuelve a proposito: el formato de respuesta no la incluye, asi que no tiene que llegar al modelo.
                "linea": al["linea"]["nombre"],
                "proximos_arribos_minutos": [p["arriboEnMinutos"] for p in proximos],
                "tipo_dato": proximos[0]["tipo"] if proximos else None,
            })

        resultado_paradas.append({
            "parada_id": parada["id"],
            "parada_nombre": parada["nombre"],
            "parada_descripcion": parada.get("descripcion", ""),
            "distancia_metros": parada["distancia"],
            "lineas": lineas_info,
        })

    if not resultado_paradas:
        mensaje = (f"No encontré la línea {linea} en las paradas cercanas a {ubicacion['nombre']}."
                   if linea else
                   f"No hay arribos disponibles en las paradas cercanas a {ubicacion['nombre']}.")
        return error(
            mensaje,
            "Decíselo al usuario tal cual. NO inventes una parada ni un horario.",
            ubicacion_resuelta=ubicacion["nombre"],
        )

    return {
        "lugar_buscado": lugar,
        "ubicacion_resuelta": ubicacion["nombre"],
        "paradas_con_arribos": resultado_paradas,
        "paradas_salteadas_por_error": paradas_con_error,
    }


def planificar_viaje(origen, destino, max_opciones=10):
    ubic_origen = geocodificar_direccion(origen)
    if ubic_origen is None:
        if nombra_otra_ciudad(origen):
            return error(f"'{origen}' es otra ciudad. Solo cubro Rosario y el Gran Rosario.",
                         "Decíselo al usuario tal cual. NO ofrezcas otro origen.")
        return error(f"No pude encontrar el origen '{origen}'.",
                     "Pedile al usuario que lo escriba de otra forma. NO inventes una dirección.")

    ubic_destino = geocodificar_direccion(destino)
    if ubic_destino is None:
        if nombra_otra_ciudad(destino):
            return error(f"'{destino}' es otra ciudad. Solo cubro Rosario y el Gran Rosario.",
                         "Decíselo al usuario tal cual. NO ofrezcas otro destino.")
        return error(f"No pude encontrar el destino '{destino}'.",
                     "Pedile al usuario que lo escriba de otra forma. NO inventes una dirección.")

    try:
        respuesta = requests.get(
            f"{BASE_URL}/geojson/comollego",
            params={
                "xOrigen": ubic_origen["longitud"],
                "yOrigen": ubic_origen["latitud"],
                "xDestino": ubic_destino["longitud"],
                "yDestino": ubic_destino["latitud"],
                "cantCuadras": 8,
                "incluirBicicletasRentadas": "false",
                "usarCoordenadasWGS84": "true",
            },
            headers=HEADERS,
            timeout=20,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.RequestException:
        return error("No pude conectarme al servicio de colectivos.",
                     "Decile al usuario que el servicio no está disponible ahora. "
                     "NO inventes un recorrido.")

    rutas = datos.get("rutas", [])
    if not rutas:
        return error(
            f"No encontré una ruta en colectivo entre '{origen}' y '{destino}'.",
            "Decíselo al usuario tal cual. NO inventes una línea ni una parada.",
            origen_resuelto=ubic_origen["nombre"],
            destino_resuelto=ubic_destino["nombre"],
        )

    opciones = []

    for ruta in rutas:
        tramos_colectivo = [
            f["properties"] for f in ruta["tramos"]["features"]
            if f["properties"]["modo_descripcion"] == "Colectivo"
        ]
        if not tramos_colectivo:
            continue

        primer_tramo = tramos_colectivo[0]

        # tramos[0] = el colectivo que tomás, con su parada de subida.
        # tramos[1] (si existe) = la segunda linea, y su parada de abordaje es justo donde bajas del primero: ese es el transbordo.
        tramos_resumen = [
            {
                "linea": tramo["linea"]["nombre"],
                "parada_abordaje_nombre": tramo["desde"]["properties"]["nombre"],
            }
            for tramo in tramos_colectivo
        ]

        parada_id = primer_tramo["desde"]["properties"]["parada"]

        try:
            arribos_lineas = cuando_llega(parada_id)
            proximos = []
            for al in arribos_lineas:
                if al["linea"]["nombre"] == primer_tramo["linea"]["nombre"]:
                    proximos = sorted(al.get("arribos", []), key=lambda a: a["arriboEnMinutos"])
                    break
            minutos_espera = [p["arriboEnMinutos"] for p in proximos[:2]]
            arribos_fallo = False
        except requests.RequestException:
            # Distinguir "no hay servicio ahora" de "la API fallo" importa: el agente tiene que poder decir cual de las dos es.
            minutos_espera = []
            arribos_fallo = True

        caminatas = [
            f["properties"] for f in ruta["tramos"]["features"]
            if f["properties"]["modo_descripcion"] == "Caminata"
        ]
        cuadras_antes = next(
            (round(c["distancia"] / 100) for c in caminatas if c["secuencia"] == 1), 0
        )
        cuadras_despues = round(caminatas[-1]["distancia"] / 100) if caminatas else 0

        opciones.append({
            "linea": primer_tramo["linea"]["nombre"],
            "parada_abordaje_id": parada_id,
            "parada_abordaje_nombre": primer_tramo["desde"]["properties"]["nombre"],
            "cuadras_caminando_hasta_parada": cuadras_antes,
            "cuadras_caminando_desde_bajada": cuadras_despues,
            "minutos_espera_en_vivo": minutos_espera,
            "arribos_no_disponibles": arribos_fallo,
            "duracion_total_minutos": round(ruta["duracion"] / 60),
            "cantidad_transbordos": ruta["cantidadTransbordos"],
            "tramos": tramos_resumen,
        })

    if not opciones:
        return error(
            f"No encontré una opción en colectivo entre '{origen}' y '{destino}'.",
            "Decíselo al usuario tal cual. NO inventes una línea ni una parada.",
            origen_resuelto=ubic_origen["nombre"],
            destino_resuelto=ubic_destino["nombre"],
        )

    return {
        "origen_resuelto": ubic_origen["nombre"],
        "destino_resuelto": ubic_destino["nombre"],
        "opciones": opciones[:max_opciones],
    }

CUADRAS_MAXIMAS_A_PIE = 10

def resolver_punto(texto):
    #Texto -> coordenadas, con tres intentos en orden de confiabilidad:
    #geocodificador municipal, Nominatim, y por ultimo Google Places(para lugares que no tienen una calle asignada)

    ubicacion = geocodificar_direccion(texto)
    if ubicacion:
        return ubicacion

    # Se importa este modulo aca porque arriba haria un ciclo.
    from colectivos.resolver_ubicacion import rankear_lugares
    from lugares.lugares import buscar_lugares

    try:
        resultado = buscar_lugares(nombre=texto, limite=10)
    except Exception:
        return None

    if resultado.get("error"):
        return None

    r = rankear_lugares(texto, resultado.get("lugares", []))
    if not r["ganador"]:
        return None

    ganador = r["ganador"]
    return {
        "nombre": ganador.get("nombre"),
        "latitud": ganador["latitud"],
        "longitud": ganador["longitud"],
        "fuente": "google_places",
    }

MAX_OPCIONES_CON_ARRIBO = 6


def agregar_arribos(opciones):
    #buscar_directos sale de los CSV, asi que sabe que linea y que parada pero no cuanto falta. El dato en vivo lo tiene la API municipal.
  
    for opcion in opciones[:MAX_OPCIONES_CON_ARRIBO]:
        try:
            arribos_lineas = cuando_llega(opcion["id_parada_subida"])
        except requests.RequestException:
            # Hay paradas que devuelven 500. Se distingue de "no hay servicio".
            opcion["minutos_espera"] = []
            opcion["arribos_no_disponibles"] = True
            continue

        minutos = []
        for al in arribos_lineas:
            if al["linea"]["nombre"] == opcion["linea"]:
                minutos = [a["arriboEnMinutos"]
                           for a in sorted(al.get("arribos", []),
                                           key=lambda x: x["arriboEnMinutos"])[:2]]
                break

        opcion["minutos_espera"] = minutos
        opcion["arribos_no_disponibles"] = False

    return opciones

def agregar_arribos_a_google(opciones):
    #Pide el arribo en vivo del PRIMER tramo de cada opcion de Google si ese primer tramo es una linea urbana.
    
    for opcion in opciones[:MAX_OPCIONES_CON_ARRIBO]:
        primer_tramo = opcion["tramos"][0]
        id_parada = primer_tramo.get("id_parada_municipal")

        if not id_parada:
            primer_tramo["minutos_espera"] = []
            primer_tramo["solo_horario_de_tabla"] = True
            continue

        try:
            arribos_lineas = cuando_llega(id_parada)
        except requests.RequestException:
            primer_tramo["minutos_espera"] = []
            primer_tramo["solo_horario_de_tabla"] = True
            continue

        # Google abrevia distinto que la API municipal: "142 N" contra
        # "142 NEGRO". Se compara contra el nombre, el corto y el codigo.
        from colectivos.recorridos import cargar_datos
        datos = cargar_datos()
        nombres_validos = set()
        for linea in datos["lineas"].values():
            if primer_tramo["linea"].upper() in (
                linea["nombre"].upper(), linea["nombre_corto"].upper(), linea["codigo_emr"].upper()
            ):
                nombres_validos.add(linea["nombre"].upper())

        minutos = []
        for al in arribos_lineas:
            if al["linea"]["nombre"].upper() in nombres_validos:
                minutos = [a["arriboEnMinutos"]
                           for a in sorted(al.get("arribos", []),
                                           key=lambda x: x["arriboEnMinutos"])[:2]]
                break

        primer_tramo["minutos_espera"] = minutos
        primer_tramo["solo_horario_de_tabla"] = not minutos

    return opciones

def planificar_viaje_completo(origen, destino, max_opciones=10, punto_origen=None, punto_destino=None):
    #Punto_origen y punto_destino permiten pasar coordenadas ya resueltas que ubica los lugares con Google Places
    #Sin esto, el texto se geocodificaria devolveria otra cosa ("Seminario Arquidiocesano" terminaba en una plazoleta).
    o = punto_origen or resolver_punto(origen)
    if o is None:
        return error(f"No pude encontrar el origen '{origen}'.",
                     "Pedile al usuario que lo escriba de otra forma. NO inventes una dirección.")

    d = punto_destino or resolver_punto(destino)
    if d is None:
        return error(f"No pude encontrar el destino '{destino}'.",
                     "Pedile al usuario que lo escriba de otra forma. NO inventes una dirección.")

    directos = buscar_directos(o["latitud"], o["longitud"], d["latitud"], d["longitud"],
                               max_opciones=max_opciones)
    opciones = directos.get("opciones", [])

    if opciones:
        agregar_arribos(opciones)

    resultado = {
        "origen_resuelto": o["nombre"],
        "destino_resuelto": d["nombre"],
        "directos": opciones,
        "fecha_datos_directos": directos.get("fecha_datos"),
    }

    if not opciones:
        motivo = "Ninguna línea urbana une esos dos puntos sin transbordo."
    elif opciones[0]["cuadras_a_pie_total"] > CUADRAS_MAXIMAS_A_PIE:
        motivo = f"El mejor directo deja {opciones[0]['cuadras_a_pie_total']} cuadras a pie."
    else:
        return resultado

    resultado["motivo_otras_fuentes"] = motivo

    # Segundo nivel: comollego resuelve transbordos dentro de Rosario, que los directos no cubren, y trae arribos en vivo.
    con_transbordo = planificar_viaje(origen, destino, max_opciones=max_opciones)
    if not con_transbordo.get("error"):
        resultado["con_transbordo"] = con_transbordo["opciones"]
        return resultado

    resultado["sin_opciones_urbanas"] = con_transbordo["error"]

    # Tercer nivel: Google, el unico que conoce los interurbanos.
    google = buscar_viajes(o["latitud"], o["longitud"], d["latitud"], d["longitud"])
    if google.get("error"):
        resultado["google_error"] = google["error"]
    else:
        resultado["google"] = agregar_arribos_a_google(google["opciones"])
        resultado["aviso_google"] = (
            "Horarios de tabla, no arribos en vivo. Incluye interurbanos que el sistema "
            "municipal no tiene. Donde dice parada_sugerida, Google mandó a la parada "
            "equivocada y esa es la correcta."
        )

    return resultado

def imprimir_proximos(resultado):
    if resultado.get("error"):
        print(resultado["error"])
        return

    print(f"Ubicación: {resultado['ubicacion_resuelta']}")
    for parada in resultado["paradas_con_arribos"]:
        descripcion = f" - {parada['parada_descripcion']}" if parada["parada_descripcion"] else ""
        print(f"\n[{parada['parada_id']}] {parada['parada_nombre']}{descripcion} "
              f"(a {parada['distancia_metros']}m)")
        for linea in parada["lineas"]:
            minutos = linea["proximos_arribos_minutos"]
            texto = ", ".join(f"{m} min" for m in minutos) if minutos else "sin datos"
            print(f"   Línea {linea['linea']}: {texto} [{linea['tipo_dato'] or '-'}]")

    if resultado["paradas_salteadas_por_error"]:
        print(f"\n({resultado['paradas_salteadas_por_error']} parada(s) salteadas por error de la API)")


def imprimir_viaje(resultado):
    if resultado.get("error"):
        print(resultado["error"])
        return

    print(f"De: {resultado['origen_resuelto']}")
    print(f"A:  {resultado['destino_resuelto']}")

    for opcion in resultado["opciones"]:
        espera = ", ".join(f"{m} min" for m in opcion["minutos_espera_en_vivo"])
        if not espera:
            espera = "sin datos en vivo" if not opcion["arribos_no_disponibles"] else "la API no respondió"

        print(f"\nLínea {opcion['linea']}")
        print(f" - Parada de abordaje: {opcion['parada_abordaje_nombre']} "
              f"({opcion['cuadras_caminando_hasta_parada']} cuadras a pie)")
        print(f" - Tiempo para el próximo: {espera}")
        print(f" - Duración total: {opcion['duracion_total_minutos']} minutos")

        if opcion["cantidad_transbordos"] == 0:
            print(" - Sin transbordos")
        else:
            siguiente = opcion["tramos"][1]
            print(f" - Transbordos: {opcion['cantidad_transbordos']} "
                  f"(al {siguiente['linea']} en {siguiente['parada_abordaje_nombre']})")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Colectivos de Rosario en vivo")
    parser.add_argument("lugar", help="Dirección o esquina de origen")
    parser.add_argument("--destino", default=None, help="Si se indica, planifica el viaje completo")
    parser.add_argument("--linea", default=None, help="Filtrar por línea, ej: '142'")
    parser.add_argument("--radio", type=int, default=300, help="Radio de búsqueda de paradas en metros")

    args = parser.parse_args()

    if args.destino:
        imprimir_viaje(planificar_viaje(args.lugar, args.destino))
    else:
        imprimir_proximos(proximos_colectivos(args.lugar, linea=args.linea, radio_metros=args.radio))


if __name__ == "__main__":
    main()