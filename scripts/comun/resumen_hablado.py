# Arma en codigo lo que Rosario DICE, que no es lo mismo que lo que se lee.
# La pantalla muestra la lista completa; la voz cuenta el primer resultado en una
# oracion y avisa que el resto esta a la vista. Se arma de los campos de la
# herramienta y no del texto del modelo: asi la voz nunca inventa un dato.

CIERRE_CON_MAS = "Te dejo las demás opciones a mano."


def _minutos(opcion):
    minutos = opcion.get("minutos_espera") or opcion.get("minutos_espera_en_vivo") or []
    if minutos:
        return f", y el próximo pasa en {minutos[0]} minutos"
    if opcion.get("arribos_no_disponibles"):
        return ", aunque ahora no tengo los minutos en vivo"
    return ""


def _caminata(cuadras):
    if not cuadras:
        return "justo ahí"
    if cuadras == 1:
        return "a una cuadra"
    return f"a {cuadras} cuadras"


def _viaje(resultado):
    opciones = resultado.get("directos") or resultado.get("con_transbordo") or resultado.get("opciones")
    if not opciones:
        return None

    o = opciones[0]
    cuadras = o.get("cuadras_a_pie_total", o.get("cuadras_caminando_hasta_parada"))
    parada = o.get("parada_subida") or o.get("parada_abordaje_nombre")

    frase = f"Te conviene el {o['linea']}. Lo tomás en {parada}, {_caminata(cuadras)}{_minutos(o)}."
    if o.get("cantidad_transbordos"):
        siguiente = o["tramos"][1]
        frase += f" Después transbordás al {siguiente['linea']}."
    if len(opciones) > 1:
        frase += " " + CIERRE_CON_MAS
    return frase


def _paradas(resultado):
    paradas = resultado.get("paradas_con_arribos")
    if not paradas:
        return None

    p = paradas[0]
    lineas = p.get("lineas") or []
    if not lineas:
        return None

    l = lineas[0]
    minutos = l.get("proximos_arribos_minutos") or []
    cuando = f"pasa en {minutos[0]} minutos" if minutos else "no tiene arribos en vivo ahora"
    frase = f"En {p['parada_nombre']}, a {p['distancia_metros']} metros, el {l['linea']} {cuando}."
    if len(lineas) > 1 or len(paradas) > 1:
        frase += " " + CIERRE_CON_MAS
    return frase


def _precios(resultado):
    barato = resultado.get("mas_conviene")
    if not barato:
        return None

    frase = f"Lo que más conviene es {barato['producto']}"
    if barato.get("contenido"):
        frase += f", de {barato['contenido']}"
    frase += f", a {_pesos(barato['precio'])}, en {barato['supermercado']}"
    if barato.get("direccion"):
        frase += f", {barato['direccion']}"
    frase += "."

    if sum(len(g["productos"]) for g in resultado.get("por_supermercado", [])) > 1:
        frase += " " + CIERRE_CON_MAS
    return frase

def _comparar(resultado):
    comercios = resultado.get("por_comercio")
    if not comercios:
        return None

    c = comercios[0]
    frase = f"Lo más barato es {_pesos(c['precio'])} en {c['comercio']}"
    if c.get("tiene_promo"):
        frase += ", con promoción"
    frase += "."
    if len(comercios) > 1:
        diferencia = resultado.get("diferencia_maxima")
        if diferencia:
            frase += f" Entre la más cara y la más barata hay {_pesos(diferencia)} de diferencia."
        frase += " " + CIERRE_CON_MAS
    return frase

def _pesos(valor):
    # Con el simbolo $, el TTS lee "dolares": la palabra va escrita. Y los
    # centavos se leen como si fueran pesos, asi que se redondea.
    return f"{round(valor):,} pesos".replace(",", ".")


def _agenda(resultado):
    eventos = resultado.get("eventos")
    if not eventos:
        return None

    e = eventos[0]
    frase = f"Hay varias cosas. Por ejemplo {e['titulo']}, {e['cuando']}"
    if e.get("hora"):
        frase += f", {e['hora']}"
    if e.get("entrada"):
        frase += f", {e['entrada']}"
    frase += "."
    if len(eventos) > 1:
        frase += " " + CIERRE_CON_MAS
    return frase


def _descuentos(resultado):
    promos = resultado.get("promociones") or resultado.get("descuentos")
    if not promos:
        return None

    p = promos[0]
    partes = [str(p.get(campo)) for campo in ("descuento", "cadena", "entidad") if p.get(campo)]
    if not partes:
        return None
    frase = "La mejor ahora es " + ", ".join(partes) + "."
    if len(promos) > 1:
        frase += " " + CIERRE_CON_MAS
    return frase


# Una herramienta por armador. Las que no estan (clima, cotizaciones) ya
# responden corto: se lee el texto del modelo tal cual.
ARMADORES = {
    "planificar_viaje": _viaje,
    "proximos_colectivos": _paradas,
    "buscar_precios": _precios,
    "consultar_agenda": _agenda,
    "consultar_descuentos": _descuentos,
    "comparar_producto": _comparar,
}


def resumen_hablado(nombre_herramienta, resultado):
    # Devuelve None cuando no hay nada que resumir: ahi se habla el texto del modelo.
    armador = ARMADORES.get(nombre_herramienta)
    if armador is None or not isinstance(resultado, dict) or resultado.get("error"):
        return None
    try:
        return armador(resultado)
    except (KeyError, TypeError, IndexError):
        # Un campo que cambio de nombre no puede romper el turno.
        return None