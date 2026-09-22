"""
Consulta la agenda cultural en BigQuery.

Va en scripts/agenda/consulta_agenda.py

Todo lo que se puede decidir sin la base (interpretar "el finde", parsear
"Miercoles a Sabado", armar el patron de busqueda) se resuelve en Python y se
testea offline. A BigQuery solo se va a buscar filas.
"""

import sys
import os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from google.cloud import bigquery

PROJECT_ID = "agent-rosario"
DATASET = "rosario_vivo"
TABLA = f"`{PROJECT_ID}.{DATASET}.eventos_agenda`"
ZONA_ROSARIO = ZoneInfo("America/Argentina/Buenos_Aires")

LIMITE_POR_DEFECTO = 12
DIAS_ALERTA_DATOS_VIEJOS = 2

_cliente = None
_categorias_cache = None


def obtener_cliente():
    # Perezoso: si el cliente se crea al importar, el agente entero no arranca
    # cuando faltan las credenciales.
    global _cliente
    if _cliente is None:
        _cliente = bigquery.Client(project=PROJECT_ID)
    return _cliente


def normalizar(texto):
    sin_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sin_acentos.lower().strip()


def hoy_en_rosario():
    # CURRENT_DATE() de BigQuery es UTC: despues de las 21 de Rosario ya devuelve
    # el dia siguiente. La fecha se calcula aca y se manda como parametro.
    return datetime.now(ZONA_ROSARIO).date()


def error(mensaje, instruccion, **extra):
    resultado = {"error": mensaje, "instruccion_para_el_agente": instruccion}
    resultado.update(extra)
    return resultado


# ---------------------------------------------------------------- fechas

def interpretar_fecha(texto, hoy=None):
    """
    Devuelve (desde, hasta, descripcion) o None si no se entiende.
    Funcion pura: no toca BigQuery.
    """
    hoy = hoy or hoy_en_rosario()
    t = normalizar(texto) or "hoy"

    if t in ("hoy", "ahora", "hoy mismo", "esta noche", "hoy a la noche", "el dia de hoy"):
        return hoy, hoy, "hoy"

    if t in ("manana", "manana mismo", "el dia de manana"):
        d = hoy + timedelta(days=1)
        return d, d, "mañana"

    if t == "pasado manana":
        d = hoy + timedelta(days=2)
        return d, d, "pasado mañana"

    if t in ("finde", "el finde", "este finde", "fin de semana", "el fin de semana",
             "este fin de semana", "weekend"):
        dia_semana = hoy.weekday()          # lunes=0 ... sabado=5, domingo=6
        if dia_semana == 5:
            return hoy, hoy + timedelta(days=1), "este finde"
        if dia_semana == 6:
            return hoy, hoy, "hoy domingo"
        sabado = hoy + timedelta(days=(5 - dia_semana))
        return sabado, sabado + timedelta(days=1), "el finde que viene"

    if t in ("semana", "esta semana", "la semana", "los proximos dias"):
        return hoy, hoy + timedelta(days=6), "los próximos 7 días"

    if t in ("mes", "este mes", "proximo mes", "el mes"):
        return hoy, hoy + timedelta(days=30), "los próximos 30 días"

    try:
        fecha = date.fromisoformat(t)
        return fecha, fecha, fecha.isoformat()
    except ValueError:
        pass

    partes = [p for p in t.replace("-", "/").split("/") if p.strip()]
    if len(partes) in (2, 3):
        try:
            numeros = [int(p) for p in partes]
        except ValueError:
            return None
        dia, mes = numeros[0], numeros[1]
        anio = (numeros[2] + 2000 if numeros[2] < 100 else numeros[2]) if len(numeros) == 3 else hoy.year
        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            return None
        if len(numeros) == 2 and fecha < hoy:
            fecha = date(anio + 1, mes, dia)
        return fecha, fecha, fecha.isoformat()

    return None


# ----------------------------------------------------- dias de la semana

DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}

NOMBRES_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def texto_cuando(fechas):
    # Una linea de texto en vez de una lista de fechas ISO: el modelo copia lo
    # que le damos, asi que le damos ya escrito lo que tiene que mostrar.
    if len(fechas) == 1:
        f = fechas[0]
        return f"{NOMBRES_DIAS[f.weekday()]} {f.day}"
    return f"del {fechas[0].day}/{fechas[0].month} al {fechas[-1].day}/{fechas[-1].month}"

def interpretar_dias(texto):
   
    t = normalizar(texto)
    if not t:
        return None

    if "todos los dias" in t:
        return set(range(7))

    if " a " in t:
        extremos = [p.strip() for p in t.split(" a ")]
        if len(extremos) != 2 or any(e not in DIAS_SEMANA for e in extremos):
            return None
        desde, hasta = DIAS_SEMANA[extremos[0]], DIAS_SEMANA[extremos[1]]
        # Modulo 7: un 'Sabado a Martes' da la vuelta a la semana.
        return {(desde + i) % 7 for i in range((hasta - desde) % 7 + 1)}

    tokens = [p.strip() for p in t.replace(" y ", ",").split(",") if p.strip()]
    if not tokens or any(tk not in DIAS_SEMANA for tk in tokens):
        return None
    return {DIAS_SEMANA[tk] for tk in tokens}


def fechas_en_rango(fecha_inicio, fecha_fin, dias_texto, desde, hasta):
    """
    Devuelve (dia_confirmado, [fechas concretas en las que cae el evento]).

    Sin este filtro, "que hay hoy" devuelve casi toda la agenda: las muestras y
    los talleres duran meses y solapan con cualquier dia.

    dia_confirmado=False significa que el evento no trae el campo 'dias': solapa
    por rango pero no sabemos si efectivamente hay funcion ese dia.
    """
    inicio = max(fecha_inicio, desde)
    fin = min(fecha_fin, hasta)
    if inicio > fin:
        return True, []

    todas = [inicio + timedelta(days=i) for i in range((fin - inicio).days + 1)]

    dias = interpretar_dias(dias_texto)
    if dias is None:
        return False, todas

    return True, [f for f in todas if f.weekday() in dias]


# ------------------------------------------------------------ categorias

def obtener_categorias(forzar_recarga=False):
    """
    Lista real de categorias, leida una vez por proceso.

    No se hardcodea: mezclan tipo (Musica, Teatro) con distrito (Centro, Sur) y
    aparecen nuevas cuando entran eventos.
    """
    global _categorias_cache
    if _categorias_cache is None or forzar_recarga:
        sql = f"SELECT DISTINCT c AS categoria FROM {TABLA}, UNNEST(categorias) AS c ORDER BY categoria"
        _categorias_cache = [fila.categoria for fila in obtener_cliente().query(sql).result()]
    return _categorias_cache


def resolver_categoria(texto):
    """Devuelve la categoria canonica, o None si no matchea o es ambigua."""
    objetivo = normalizar(texto)
    if not objetivo:
        return None

    categorias = obtener_categorias()

    for c in categorias:
        if normalizar(c) == objetivo:
            return c

    parciales = [c for c in categorias if objetivo in normalizar(c)]
    return parciales[0] if len(parciales) == 1 else None


# -------------------------------------------------------------- busqueda

VOCALES_CON_TILDE = {
    "a": "[aáAÁ]", "e": "[eéEÉ]", "i": "[iíIÍ]",
    "o": "[oóOÓ]", "u": "[uúüUÚÜ]", "n": "[nñNÑ]",
}


def patron_de_busqueda(texto):
    """
    Arma un patron que ignora acentos: "musica" encuentra "Música".

    BigQuery no tiene una funcion para sacar acentos, asi que se hace al reves:
    cada vocal del texto buscado matchea tambien su version con tilde.
    """
    partes = []
    for caracter in normalizar(texto):
        if caracter in VOCALES_CON_TILDE:
            partes.append(VOCALES_CON_TILDE[caracter])
        elif caracter.isalnum():
            partes.append(re.escape(caracter))
        elif caracter.isspace():
            partes.append(r"\s+")
    return "".join(partes)


# --------------------------------------------------------------- consulta

SQL_EVENTOS = f"""
SELECT
    id_evento, titulo, url, descripcion,
    fecha_inicio, fecha_fin, duracion_dias, dias, hora_texto,
    lugar_nombre, lugar_direccion, lugar_latitud, lugar_longitud,
    origen_lugar, tiene_coordenadas,
    entrada, es_gratis, categorias, etiqueta_serie,
    fecha_extraccion, dias_desde_la_extraccion
FROM {TABLA}
WHERE fecha_inicio <= @hasta
  AND fecha_fin >= @desde
  AND (@categoria IS NULL OR @categoria IN UNNEST(categorias))
  AND (@solo_gratis IS FALSE OR es_gratis IS TRUE)
  AND (
    @patron IS NULL
    OR REGEXP_CONTAINS(LOWER(titulo), @patron)
    OR REGEXP_CONTAINS(LOWER(IFNULL(descripcion, '')), @patron)
    OR REGEXP_CONTAINS(LOWER(IFNULL(lugar_nombre, '')), @patron)
  )
"""


def consultar_agenda(fecha="hoy", categoria=None, busqueda=None,
                     solo_gratis=False, limite=LIMITE_POR_DEFECTO):
    rango = interpretar_fecha(fecha)
    if rango is None:
        return error(
            f"No entendí la fecha '{fecha}'.",
            "Pedile al usuario que aclare la fecha. NO inventes eventos ni asumas que era hoy.",
            valores_aceptados=["hoy", "mañana", "pasado mañana", "finde", "esta semana",
                               "este mes", "una fecha tipo 2026-09-20 o 20/09"],
        )
    desde, hasta, descripcion_rango = rango

    categoria_canonica = None
    if categoria:
        try:
            categoria_canonica = resolver_categoria(categoria)
        except Exception as e:
            return error(f"No pude leer las categorías: {e}",
                         "Decile al usuario que la agenda no está disponible en este momento.")
        if categoria_canonica is None:
            return error(
                f"La categoría '{categoria}' no existe en la agenda.",
                "Mostrale al usuario las categorías disponibles y pedile que elija una. "
                "NO uses otra categoría como si fuera la que pidió.",
                categorias_disponibles=obtener_categorias(),
            )

    parametros = [
        bigquery.ScalarQueryParameter("desde", "DATE", desde),
        bigquery.ScalarQueryParameter("hasta", "DATE", hasta),
        bigquery.ScalarQueryParameter("categoria", "STRING", categoria_canonica),
        bigquery.ScalarQueryParameter("solo_gratis", "BOOL", bool(solo_gratis)),
        bigquery.ScalarQueryParameter("patron", "STRING",
                                      patron_de_busqueda(busqueda) if busqueda else None),
    ]

    try:
        filas = list(
            obtener_cliente()
            .query(SQL_EVENTOS, job_config=bigquery.QueryJobConfig(query_parameters=parametros))
            .result()
        )
    except Exception as e:
        return error(f"Falló la consulta a BigQuery: {e}",
                     "Decile al usuario que la agenda no está disponible en este momento. "
                     "NO inventes eventos.")

    candidatos = []
    descartados_por_dia = 0

    for fila in filas:
        confirmado, fechas = fechas_en_rango(
            fila.fecha_inicio, fila.fecha_fin, fila.dias, desde, hasta
        )
        if not fechas:
            descartados_por_dia += 1
            continue

        evento = {
            "titulo": fila.titulo,
            "url": fila.url,
            "cuando": texto_cuando(fechas),
            "hora": fila.hora_texto,
            "entrada": "Gratis" if fila.es_gratis else fila.entrada,
            "lugar": fila.lugar_nombre or fila.lugar_direccion,
            # True: el campo 'dias' confirma que cae en el rango pedido.
            # False: el evento no trae dias, solo solapa por rango de fechas.
            "dia_confirmado": confirmado,
            "_orden_primera_fecha": fechas[0],
            "_orden_fin": fila.fecha_fin,
        }
        # Solo cuando hay algo que aclarar: "municipio" es dato oficial y no se menciona.
        if fila.origen_lugar != "municipio":
            evento["origen_lugar"] = fila.origen_lugar
        candidatos.append(evento)

    # Primero lo confirmado, despues lo que empieza antes, despues lo que esta
    # por terminar.
    candidatos.sort(key=lambda e: (not e["dia_confirmado"], e["_orden_primera_fecha"],
                                   e["_orden_fin"], e["titulo"]))
    for e in candidatos:
        del e["_orden_primera_fecha"]
        del e["_orden_fin"]

    eventos = candidatos[:max(1, int(limite))]

    resultado = {
        "rango_consultado": {"desde": desde.isoformat(), "hasta": hasta.isoformat(),
                             "descripcion": descripcion_rango},
        "categoria": categoria_canonica,
        "busqueda": busqueda,
        "solo_gratis": bool(solo_gratis),
        "total": len(candidatos),
        "mostrados": len(eventos),
        "hay_mas": len(candidatos) > len(eventos),
        "sin_dia_confirmado": sum(1 for e in candidatos if not e["dia_confirmado"]),
        "descartados_por_dia_de_semana": descartados_por_dia,
        "eventos": eventos,
        "como_responder": (
            "UNA línea por evento, con este formato exacto: "
            "[titulo](url) — cuando, hora — entrada. "
            "Nada más: ni lugar, ni dirección, ni viñetas debajo. "
            "El usuario abre el link si quiere el detalle."
        ),
    }

    if filas:
        dias_viejos = filas[0].dias_desde_la_extraccion
        resultado["fecha_datos"] = filas[0].fecha_extraccion.isoformat()
        if dias_viejos is not None and dias_viejos > DIAS_ALERTA_DATOS_VIEJOS:
            resultado["aviso_datos_viejos"] = (
                f"Los datos se extrajeron hace {dias_viejos} días: puede haber eventos "
                "nuevos que no aparecen."
            )

    return resultado


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Consultar la agenda cultural de Rosario")
    parser.add_argument("--fecha", default="hoy")
    parser.add_argument("--categoria", default=None)
    parser.add_argument("--busqueda", default=None)
    parser.add_argument("--solo-gratis", action="store_true")
    parser.add_argument("--limite", type=int, default=LIMITE_POR_DEFECTO)

    args = parser.parse_args()
    r = consultar_agenda(fecha=args.fecha, categoria=args.categoria,
                         busqueda=args.busqueda, solo_gratis=args.solo_gratis,
                         limite=args.limite)

    if r.get("error"):
        print(r["error"])
        if r.get("categorias_disponibles"):
            print("Categorías:", ", ".join(r["categorias_disponibles"]))
        return

    rango = r["rango_consultado"]
    print(f"{rango['desde']} a {rango['hasta']} ({rango['descripcion']})"
          f" | categoría: {r['categoria'] or '-'} | búsqueda: {r['busqueda'] or '-'}")
    print(f"{r['total']} evento(s), mostrando {r['mostrados']}"
          f" | sin día confirmado: {r['sin_dia_confirmado']}"
          f" | descartados por día: {r['descartados_por_dia_de_semana']}")

    if r.get("aviso_datos_viejos"):
        print(f"[!] {r['aviso_datos_viejos']}")

    for e in r["eventos"]:
        marca = "" if e["dia_confirmado"] else "  [día sin confirmar]"
        print(f"- {e['titulo']}{marca}")
        print(f"    {e['cuando']} | {e['hora'] or '-'} | {e['entrada'] or '-'} | {e['lugar'] or 'sin lugar'}")


if __name__ == "__main__":
    main()