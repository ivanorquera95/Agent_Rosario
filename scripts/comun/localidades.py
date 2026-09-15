import math
import re
import unicodedata

RADIO_TIERRA_METROS = 6_371_000
MARGEN_GRADOS = 0.05


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


def normalizar(texto):
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


# Las 16 de afuera de Rosario, normalizadas. Se derivan del diccionario de
# arriba para no tener una segunda lista que mantener.
# Los alias son variantes que escribe la gente o que usa OpenStreetMap.
ALIAS_LOCALIDADES = {"vgg": "villa gobernador galvez", "ybarlucea": "ibarlucea"}

LOCALIDADES_SIN_ROSARIO = {
    normalizar(nombre) for nombre in LOCALIDADES if nombre != "Rosario"
} | set(ALIAS_LOCALIDADES)

# Calificativos que indican que el texto habla de una CIUDAD y no de una calle.
# Muchas ciudades comparten nombre con calles de Rosario (Córdoba, Mendoza,
# Buenos Aires): sin esto, "Córdoba capital" resuelve a la peatonal Córdoba y
# devuelve un viaje de 19 minutos como si fuera real. Son calificativos, no una
# lista de ciudades: el mundo no se puede enumerar.
CALIFICATIVOS_DE_CIUDAD = (
    "capital", "provincia de", "provincia", "ciudad de", "caba", "capital federal",
)


def distancia_metros(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * RADIO_TIERRA_METROS * math.asin(math.sqrt(a))


def localidad_de(latitud, longitud):
    # La MAS CERCANA de las que contienen el punto, no la primera que matchea:
    # Rosario tiene 12 km de radio y se comeria a todos los vecinos.
    candidatas = [
        (distancia_metros(latitud, longitud, lat, lon), nombre)
        for nombre, (lat, lon, radio) in LOCALIDADES.items()
        if distancia_metros(latitud, longitud, lat, lon) <= radio
    ]
    if not candidatas:
        return None
    return min(candidatas)[1]


def dentro_del_gran_rosario(latitud, longitud):
    return localidad_de(latitud, longitud) is not None


def limites_gran_rosario():
    latitudes = [lat for lat, _, _ in LOCALIDADES.values()]
    longitudes = [lon for _, lon, _ in LOCALIDADES.values()]
    return {
        "sur": min(latitudes) - MARGEN_GRADOS,
        "norte": max(latitudes) + MARGEN_GRADOS,
        "oeste": min(longitudes) - MARGEN_GRADOS,
        "este": max(longitudes) + MARGEN_GRADOS,
    }


def detectar_localidad(texto):
    """
    Detecta si el texto nombra una localidad del Gran Rosario COMO LOCALIDAD,
    no como calle. Varias comparten nombre con calles de Rosario (Deán Funes,
    Pedro Lino Funes, Alvear), asi que no alcanza con buscar la palabra.

    La regla: la localidad va DESPUES de la altura o de una coma.

        "Urquiza 1000, Funes"    -> funes
        "Urquiza 1000 Funes"     -> funes
        "Funes"                  -> funes
        "Deán Funes 862"         -> None   (antes de la altura: es la calle)
        "Deán Funes y Sarmiento" -> None   (no hay altura ni coma)
    """
    t = normalizar(texto)

    if "," in t:
        cola = t.split(",", 1)[1]
    else:
        numeros = list(re.finditer(r"\d{1,5}", t))
        if numeros:
            cola = t[numeros[-1].end():]
        else:
            cola = t if t in LOCALIDADES_SIN_ROSARIO else ""

    for loc in LOCALIDADES_SIN_ROSARIO:
        if loc in cola:
            return ALIAS_LOCALIDADES.get(loc, loc)
    return None


def nombra_otra_ciudad(texto):
    """
    True si el texto se refiere a una ciudad de fuera del area, no a una calle.

        "Córdoba capital"       -> True
        "provincia de Santa Fe" -> True
        "Córdoba 1015"          -> False  (es la calle con altura)
        "Ciudad de Rosario"     -> False  (es aca)
        "Funes"                 -> False  (localidad del Gran Rosario)
    """
    t = normalizar(texto)
    if detectar_localidad(t) or "rosario" in t:
        return False
    return any(c in t for c in CALIFICATIVOS_DE_CIUDAD)