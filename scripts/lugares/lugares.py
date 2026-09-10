import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import math
import unicodedata
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
API_URL_TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"
API_URL_NEARBY_SEARCH = "https://places.googleapis.com/v1/places:searchNearby"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "RosarioVivo/1.0 (proyecto de portfolio)"}

# Las 17 localidades del Gran Rosario, con su centro y un radio propio:
LOCALIDADES = {
    "Rosario":                   (-32.9594, -60.6617, 12000),
    "Villa Gobernador Gálvez":   (-33.0251, -60.6337, 5000),
    "San Lorenzo":               (-32.7455, -60.7431, 5000),
    "Granadero Baigorria":       (-32.8548, -60.7074, 5000),
    "Capitán Bermúdez":          (-32.8167, -60.7167, 4000),
    "Pérez":                     (-32.9982, -60.7709, 5000),
    "Funes":                     (-32.9169, -60.8106, 6000),
    "Fray Luis Beltrán":         (-32.7874, -60.7295, 4000),
    "Roldán":                    (-32.9001, -60.9066, 6000),
    "Puerto General San Martín": (-32.7116, -60.7341, 4000),
    "Soldini":                   (-33.0242, -60.7553, 3000),
    "Arroyo Seco":               (-33.1546, -60.5082, 5000),
    "Ricardone":                 (-32.7707, -60.7842, 3000),
    "Ibarlucea":                 (-32.8524, -60.7894, 3000),
    "Pueblo Esther":             (-33.0789, -60.5641, 4000),
    "Alvear":                    (-33.0575, -60.6196, 3000),
    "General Lagos":             (-33.1104, -60.5637, 3000),
}

MARGEN_GRADOS = 0.05
RADIO_TIERRA_METROS = 6_371_000
RADIO_BUSQUEDA_POR_DEFECTO = 1000
MAX_RESULTADOS_GOOGLE = 20
RADIO_MAXIMO_METROS = 50000

CATEGORIAS = {
    "bar": "bar",
    "cafeteria": "cafe",
    "cafe": "cafe",
    "restaurante": "restaurant",
    "comida_rapida": "fast_food_restaurant",
    "pub": "pub",
    "heladeria": "ice_cream_shop",
    "panaderia": "bakery",
    "supermercado": "supermarket",
    "farmacia": "pharmacy",
    "hospital": "hospital",
    "banco": "bank",
    "cajero": "atm",
    "plaza": "park",
    "gimnasio": "gym",
    "hotel": "hotel",
    "estacion_servicio": "gas_station",
    "libreria": "book_store",
    "peluqueria": "hair_salon",
}

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.businessStatus",
    "places.nationalPhoneNumber",
    "places.regularOpeningHours",
])


def normalizar(texto):
    sin_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sin_acentos.lower().strip()


def error(mensaje, instruccion, **extra):
    resultado = {"error": mensaje, "instruccion_para_el_agente": instruccion}
    resultado.update(extra)
    return resultado


def distancia_metros(lat1, lon1, lat2, lon2):
    # Haversine
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * RADIO_TIERRA_METROS * math.asin(math.sqrt(a))


def localidad_de(latitud, longitud):
    # La MAS CERCANA de las que contienen el punto, no la primera que matchea:
    # Rosario tiene 12 km de radio y se comia a todos los vecinos.
    candidatas = [
        (distancia_metros(latitud, longitud, lat, lon), nombre)
        for nombre, (lat, lon, radio) in LOCALIDADES.items()
        if distancia_metros(latitud, longitud, lat, lon) <= radio
    ]
    if not candidatas:
        return None
    return min(candidatas)[1]


def limites_gran_rosario():
    # El rectangulo que Google usa como restriccion sale de las localidades, no a mano
    latitudes = [lat for lat, _, _ in LOCALIDADES.values()]
    longitudes = [lon for _, lon, _ in LOCALIDADES.values()]
    return {
        "sur": min(latitudes) - MARGEN_GRADOS,
        "norte": max(latitudes) + MARGEN_GRADOS,
        "oeste": min(longitudes) - MARGEN_GRADOS,
        "este": max(longitudes) + MARGEN_GRADOS,
    }


def resolver_zona(lugar):
    #Filtro previo gratuito con Nominatim
    #valida que la zona pedida este en el Gran Rosario ANTES de gastar una consulta de Google. Nunca elige el resultado final.
    
    if not lugar:
        lat, lon, radio = LOCALIDADES["Rosario"]
        return {"nombre": "Rosario (ciudad completa)", "localidad": "Rosario",
                "latitud": lat, "longitud": lon, "radio_default": radio}

    consulta = lugar if "rosario" in normalizar(lugar) else f"{lugar}, Santa Fe, Argentina"
    respuesta = requests.get(
        NOMINATIM_URL,
        params={"q": consulta, "format": "json", "limit": 5},
        headers=NOMINATIM_HEADERS,
        timeout=15,
    )
    respuesta.raise_for_status()
    resultados = respuesta.json()

    for r in resultados:
        latitud, longitud = float(r["lat"]), float(r["lon"])
        localidad = localidad_de(latitud, longitud)
        if localidad:
            return {"nombre": r["display_name"], "localidad": localidad,
                    "latitud": latitud, "longitud": longitud,
                    "radio_default": RADIO_BUSQUEDA_POR_DEFECTO}

    return None


def resolver_categoria(categoria):
    return CATEGORIAS.get(normalizar(categoria).replace(" ", "_"))


def extraer_lugar(p):
    horario = p.get("regularOpeningHours", {})
    return {
        "nombre": p.get("displayName", {}).get("text", "(sin nombre)"),
        "direccion": p.get("formattedAddress"),
        "latitud": p.get("location", {}).get("latitude"),
        "longitud": p.get("location", {}).get("longitude"),
        "telefono": p.get("nationalPhoneNumber"),
        "abierto_ahora": horario.get("openNow") if horario else None,
    }

def buscar_lugares(categoria=None, nombre=None, lugar=None, abierto_ahora=False,
                   radio_metros=None, limite=10):
    if not API_KEY:
        return error(
            "No está configurada GOOGLE_PLACES_API_KEY.",
            "Decile al usuario que la búsqueda de lugares no está disponible ahora.",
        )

    limite = max(1, min(int(limite or 10), MAX_RESULTADOS_GOOGLE))

    if not categoria and not nombre:
        return error(
            "Hay que indicar una categoría (ej: 'bar') o un nombre (ej: 'El Cairo').",
            "Pedile al usuario qué tipo de lugar busca.",
            categorias_disponibles=sorted(CATEGORIAS.keys()),
        )

    tipo_google = None
    if categoria:
        tipo_google = resolver_categoria(categoria)
        if tipo_google is None:
            return error(
                f"La categoría '{categoria}' no existe.",
                "Mostrale al usuario las categorías disponibles y pedile que elija una. "
                "NO uses otra categoría como si fuera la que pidió.",
                categorias_disponibles=sorted(CATEGORIAS.keys()),
            )

    try:
        zona = resolver_zona(lugar)
    except requests.RequestException:
        return error("No pude conectarme al servicio de mapas.",
                     "Decile al usuario que la búsqueda no está disponible ahora.")

    if zona is None:
        return error(
            f"'{lugar}' no está en el Gran Rosario, así que no consulté la API.",
            "Decile al usuario que solo cubrís el Gran Rosario y mostrale las localidades. "
            "NO inventes lugares fuera de esa zona.",
            localidades_cubiertas=sorted(LOCALIDADES.keys()),
        )

    if radio_metros is None:
        radio = zona["radio_default"]
    else:
        # el 0 es falso en Python: con "radio_metros or default" un radio de 0
        # se ignoraba en silencio
        radio = max(1, min(int(radio_metros), RADIO_MAXIMO_METROS))

    limites = limites_gran_rosario()
    cabeceras = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    if nombre:
        cuerpo = {
            "textQuery": f"{nombre} en {zona['nombre']}" if lugar else f"{nombre} en {zona['localidad']}, Argentina",
            "languageCode": "es",
            "maxResultCount": limite,
            "locationRestriction": {
                "rectangle": {
                    "low": {"latitude": limites["sur"], "longitude": limites["oeste"]},
                    "high": {"latitude": limites["norte"], "longitude": limites["este"]},
                }
            },
        }
        if abierto_ahora:
            cuerpo["openNow"] = True
        if tipo_google:
            cuerpo["includedType"] = tipo_google
        url = API_URL_TEXT_SEARCH
        descripcion = f"'{nombre}' en {zona['nombre']}"
    else:
        cuerpo = {
            "includedTypes": [tipo_google],
            # searchNearby no soporta openNow, se filtra despues. Pedimos de mas
            # para que el filtro no deje la lista corta.
            "maxResultCount": min(MAX_RESULTADOS_GOOGLE, limite * 3) if abierto_ahora else limite,
            "languageCode": "es",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": zona["latitud"], "longitude": zona["longitud"]},
                    "radius": radio,
                }
            },
        }
        url = API_URL_NEARBY_SEARCH
        descripcion = f"{categoria} cerca de {zona['nombre']}"

    try:
        respuesta = requests.post(url, json=cuerpo, headers=cabeceras, timeout=15)
        if respuesta.status_code != 200:
            detalle = respuesta.json().get("error", {}).get("message", respuesta.text[:200])
            return error(f"Google Places rechazó la consulta ({respuesta.status_code}): {detalle}",
                         "Decile al usuario que la búsqueda no está disponible ahora. "
                         "NO inventes lugares.")
        datos = respuesta.json()
    except requests.RequestException:
        return error("No pude conectarme a Google Places.",
                     "Decile al usuario que la búsqueda no está disponible ahora. "
                     "NO inventes lugares.")

    lugares = [extraer_lugar(p) for p in datos.get("places", [])]

    if abierto_ahora and not nombre:
        lugares = [l for l in lugares if l["abierto_ahora"] is True][:limite]

    return {
        "consulta": descripcion,
        "localidad": zona["localidad"],
        "zona_interpretada": zona["nombre"],
        "cantidad_encontrada": len(lugares),
        "lugares": lugares,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Buscar lugares en el Gran Rosario con Google Places")
    parser.add_argument("--categoria", default=None, help=f"Categoría: {', '.join(sorted(CATEGORIAS.keys()))}")
    parser.add_argument("--nombre", default=None, help="Nombre específico, ej: 'El Cairo'")
    parser.add_argument("--lugar", default=None, help="Zona, barrio, localidad o intersección")
    parser.add_argument("--abierto-ahora", action="store_true", help="Solo lugares abiertos ahora")
    parser.add_argument("--radio", type=int, default=None, help="Radio en metros")
    parser.add_argument("--limite", type=int, default=10, help="Máximo de resultados")

    args = parser.parse_args()
    resultado = buscar_lugares(
        categoria=args.categoria,
        nombre=args.nombre,
        lugar=args.lugar,
        abierto_ahora=args.abierto_ahora,
        radio_metros=args.radio,
        limite=args.limite,
    )

    if resultado.get("error"):
        print(resultado["error"])
        if resultado.get("categorias_disponibles"):
            print("Categorías:", ", ".join(resultado["categorias_disponibles"]))
        if resultado.get("localidades_cubiertas"):
            print("Localidades:", ", ".join(resultado["localidades_cubiertas"]))
        return

    print(f"{resultado['consulta']} — {resultado['cantidad_encontrada']} resultado(s)")
    print(f"Zona: {resultado['zona_interpretada']} [{resultado['localidad']}]")

    for lugar in resultado["lugares"]:
        linea = f"- {lugar['nombre']}"
        if lugar["direccion"]:
            linea += f" ({lugar['direccion']})"
        if lugar["telefono"]:
            linea += f" · {lugar['telefono']}"
        if lugar["abierto_ahora"] is True:
            linea += " [ABIERTO]"
        elif lugar["abierto_ahora"] is False:
            linea += " [CERRADO]"
        print(linea)


if __name__ == "__main__":
    main()