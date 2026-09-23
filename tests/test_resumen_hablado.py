# El resumen hablado se arma de los campos de la herramienta: se testea sin red.
from comun.resumen_hablado import resumen_hablado


def test_viaje_dice_linea_parada_y_minutos():
    r = resumen_hablado("planificar_viaje", {
        "directos": [
            {"linea": "142 NEGRO", "parada_subida": "San Martín y Deán Funes",
             "cuadras_a_pie_total": 1, "minutos_espera": [3], "arribos_no_disponibles": False},
            {"linea": "140", "parada_subida": "Otra", "cuadras_a_pie_total": 2,
             "minutos_espera": [], "arribos_no_disponibles": False},
        ],
    })
    assert "142 NEGRO" in r
    assert "San Martín y Deán Funes" in r
    assert "3 minutos" in r
    assert "demás opciones" in r


def test_una_sola_opcion_no_ofrece_mas():
    r = resumen_hablado("planificar_viaje", {
        "directos": [{"linea": "120", "parada_subida": "Mitre y Córdoba",
                      "cuadras_a_pie_total": 0, "minutos_espera": [5]}],
    })
    assert "demás opciones" not in r


def test_precio_redondea_los_centavos():
    r = resumen_hablado("buscar_precios", {
        "mas_barato_por_unidad": {
            "producto": "LECHE ENTERA", "precio_envase": 1507.5, "precio_por_unidad": 1507.5,
            "unidad": "l", "supermercado": "La Anonima", "direccion": "Blvd. Oroño 6000",
        },
        "por_supermercado": [{"supermercado": "La Anonima", "productos": [{}, {}]}],
    })
    assert "1.508 pesos" in r
    assert "Blvd. Oroño 6000" in r


def test_agenda_menciona_solo_el_primero():
    r = resumen_hablado("consultar_agenda", {
        "eventos": [
            {"titulo": "Curso sobre aromáticas", "cuando": "martes 22",
             "hora": "de 15 a 16:30", "entrada": "Gratis"},
            {"titulo": "Otro taller", "cuando": "martes 22"},
        ],
    })
    assert "Curso sobre aromáticas" in r
    assert "Otro taller" not in r


def test_error_no_se_habla():
    assert resumen_hablado("buscar_precios", {"error": "no hay datos"}) is None


def test_herramienta_sin_armador():
    assert resumen_hablado("obtener_clima", {"actual": {}}) is None


def test_campo_que_cambio_de_nombre_no_rompe():
    assert resumen_hablado("planificar_viaje", {"directos": [{"otra_cosa": 1}]}) is None