#Chequeos de la logica pura del resolver: nada de red, nada de archivos.
#Se corren con: uv run pytest

import pytest


from comun.localidades import detectar_localidad, nombra_otra_ciudad
from colectivos.resolver_ubicacion import (
    hay_ambiguedad,
    limpiar_direccion,
    parece_direccion,
    rankear_lugares,
    registrar_conocida,
    set_mensaje_usuario,
    viene_del_usuario,
    planificar_viaje_resuelto,
    proximos_colectivos_resuelto,
)


# --------------------------------------------------- detector de direcciones

@pytest.mark.parametrize("texto, esperado", [
    ("Uruguay 1050", True),
    ("Bv. Oroño 1200", True),
    ("Pellegrini y Ovidio Lagos", True),
    ("San Martín esq. Córdoba", True),
    ("Mendoza / Alvear", True),
    ("3 de Febrero 950", True),
    # El ancla al final es lo que evita que estos pasen: tienen digitos, pero no al final.
    ("Alto Rosario", False),
    ("Shopping Alto Rosario", False),
    ("Plaza 25 de Mayo", False),
    ("Parque Independencia", False),
    ("Rosario Central", False),
    ("el Monumento a la Bandera", False),
])
def test_parece_direccion(texto, esperado):
    assert parece_direccion(texto) is esperado

# ----------------------------------------------------- limpieza de direcciones

@pytest.mark.parametrize("entrada, esperado", [
    ("Junín 501, S2000 Rosario, Santa Fe, Argentina", "Junín 501"),
    ("Alto Rosario Shopping, Junín 551, S2013DJK Rosario, Santa Fe, Argentina", "Junín 551"),
    ("Nansen 323, S2013APG Rosario", "Nansen 323"),
])
def test_limpiar_direccion(entrada, esperado):
    assert limpiar_direccion(entrada) == esperado

# ------------------------------------------- ranking por consenso geografico

ALTO_ROSARIO = [
    {"nombre": "Alto Rosario Shopping", "direccion": "Junín 501, S2000 Rosario, Santa Fe, Argentina",
     "latitud": -32.9274658, "longitud": -60.6690017},
    {"nombre": "Portal Rosario Shopping", "direccion": "Nansen 323, S2013APG Rosario, Santa Fe, Argentina",
     "latitud": -32.9094055, "longitud": -60.6835548},
    {"nombre": "Alto rosario", "direccion": "Damianovich 6004, S2000 Rosario, Santa Fe, Argentina",
     "latitud": -32.9261587, "longitud": -60.7052574},
    {"nombre": "Rock&Feller's Alto Rosario", "direccion": "Junín 501, S2013DJK, S2013 Rosario, Santa Fe, Argentina",
     "latitud": -32.9285872, "longitud": -60.6678775},
    {"nombre": "Shopping del Siglo", "direccion": "Córdoba 1643, S2000 AWY, Santa Fe, Argentina",
     "latitud": -32.9452409, "longitud": -60.645715},
    {"nombre": "Alto Rosario Shopping", "direccion": "Alto Rosario Shopping, Junín 551, S2013DJK Rosario, Santa Fe, Argentina",
     "latitud": -32.926769, "longitud": -60.668494},
    {"nombre": "VER", "direccion": "Alto Rosario Shopping, Junín 501, S2013DJK Rosario, Santa Fe, Argentina",
     "latitud": -32.9277296, "longitud": -60.6670693},
    {"nombre": "Alto Rosario shopping", "direccion": "Alto Rosario shopping, Junín 501, S2013DJK Rosario, Santa Fe, Argentina",
     "latitud": -32.9270634, "longitud": -60.668225},
]

# Cuatro sucursales de Coto en zonas distintas: el caso ambiguo.
COTO = [
    {"nombre": "COTO", "direccion": "3 de Febrero 1602, S2000 Rosario, Santa Fe, Argentina",
     "latitud": -32.9525, "longitud": -60.6465},
    {"nombre": "COTO", "direccion": "Urquiza 1644, S2000 Rosario, Santa Fe, Argentina",
     "latitud": -32.9385, "longitud": -60.6520},
    {"nombre": "Hipermercado COTO", "direccion": "Avda. Junin Y Thedy Alto Rosario Shopping",
     "latitud": -32.9271, "longitud": -60.6685},
    {"nombre": "COTO", "direccion": "Mendoza 3901, S2000 Rosario, Santa Fe, Argentina",
     "latitud": -32.9430, "longitud": -60.6790},
]


def test_alto_rosario_gana_el_shopping():
    # Entre ocho resultados, el grupo con mas peso es el del shopping, y el
    # representante es el que coincide por nombre (no "VER", que esta adentro).
    r = rankear_lugares("Alto Rosario", ALTO_ROSARIO)
    assert limpiar_direccion(r["ganador"]["direccion"]) == "Junín 501"


def test_alto_rosario_no_es_ambiguo():
    assert not hay_ambiguedad(rankear_lugares("Alto Rosario", ALTO_ROSARIO))


def test_coto_es_ambiguo():
    # Cuatro sucursales lejos entre si: el agente tiene que preguntar.
    r = rankear_lugares("Coto", COTO)
    assert hay_ambiguedad(r)
    assert len(r["grupos"]) == 4


def test_el_articulo_no_desempata():
    # "el" matchea adentro de "Del": sin sacar las palabras vacias, el seminario
    # equivocado ganaba por una coincidencia de tres letras.
    lugares = [
        {"nombre": 'Seminario Arquidiocesano "San Carlos Borromeo"',
         "direccion": "S2154 Cap. Bermúdez", "latitud": -32.8111, "longitud": -60.7088},
        {"nombre": "Seminario Cruzada Del Espiritu Santo",
         "direccion": "C. 1329, S2000 Rosario", "latitud": -32.9500, "longitud": -60.6600},
    ]
    r = rankear_lugares("el seminario", lugares)
    assert r["ganador"] is not None
    assert hay_ambiguedad(r)


# ------------------------------------------- localidades del Gran Rosario

@pytest.mark.parametrize("texto, esperado", [
    ("Urquiza 1000, Funes", "funes"),
    ("Urquiza 1000 Funes", "funes"),
    ("Funes", "funes"),
    ("San Martin 500, Roldan", "roldan"),
    # Antes de la altura o sin coma: es la calle, no la localidad.
    ("Dean Funes 862", None),
    ("Deán Funes y Sarmiento", None),
    ("Pedro Lino Funes 1200", None),
    ("Alvear 1500", None),
    ("Uruguay 1050", None),
    ("Pellegrini y Corrientes", None),
])
def test_detectar_localidad(texto, esperado):
    assert detectar_localidad(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [
    ("Cordoba capital", True),
    ("Buenos Aires capital", True),
    ("provincia de Cordoba", True),
    ("capital federal", True),
    # Las mismas palabras, pero son calles de Rosario.
    ("Cordoba 1015", False),
    ("Mendoza y Alvear", False),
    ("Ciudad de Rosario", False),
    ("Urquiza 1000, Funes", False),
])
def test_nombra_otra_ciudad(texto, esperado):
    assert nombra_otra_ciudad(texto) is esperado


# --------------------------------------- guardia anti-direccion-inventada


def test_pasa_lo_que_escribio_el_usuario():
    set_mensaje_usuario("quiero ir al Alto Rosario desde Uruguay 1050")
    assert viene_del_usuario("Uruguay 1050")
    assert viene_del_usuario("Alto Rosario")


def test_bloquea_direcciones_inventadas():
    set_mensaje_usuario("quiero ir al Alto Rosario desde Uruguay 1050")
    assert not viene_del_usuario("La Paz 1400")
    assert not viene_del_usuario("Estatua de la Libertad")


def test_pasa_la_direccion_de_google_recortada():
    # El modelo copia el resultado de buscar_lugares a media asta.
    set_mensaje_usuario("quiero ir al Portal")
    registrar_conocida("Nansen 323, S2013APG Rosario, Santa Fe, Argentina")
    registrar_conocida("Nansen 323")
    assert viene_del_usuario("Nansen 323, S2013APG Rosario")


def test_falla_abierta_sin_mensaje_registrado():
    # A proposito: un olvido de set_mensaje_usuario no tiene que romper el agente.
    assert viene_del_usuario("La Paz 1400")

def test_sin_origen_pide_preguntar():
    # Devuelve antes de tocar la red.
    assert "origen" in planificar_viaje_resuelto(destino="Monumento")["error"]


def test_sin_lugar_pide_preguntar():
    assert "lugar" in proximos_colectivos_resuelto()["error"]