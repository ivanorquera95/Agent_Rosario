#Consulta de descuentos del Gran Rosario para el agente.

import sys
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
from google.cloud import bigquery
sys.stdout.reconfigure(encoding="utf-8")

PROYECTO = "agent-rosario"
DATASET = "rosario_vivo"
TABLA = f"`{PROYECTO}.{DATASET}.descuentos_vigentes`"
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
LIMITE_POR_DEFECTO = 15
MAX_LIMITE = 50

_cliente = None


def obtener_cliente():
    global _cliente
    if _cliente is None:
        _cliente = bigquery.Client(project=PROYECTO)
    return _cliente


def normalizar(texto):
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    limpio = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return limpio.upper().strip()


def palabras_de(texto):
    return [p for p in normalizar(texto).split() if p]


def error(mensaje, instruccion, **extra):
    resultado = {"error": mensaje, "instruccion_para_el_agente": instruccion}
    resultado.update(extra)
    return resultado


def dia_de_hoy():
    return DIAS[datetime.now(ZONA).weekday()]


def resolver_dia(dia):
    #Acepta 'hoy', 'miércoles', 'sabados'. Devuelve el dia tal como esta escrito en la tabla, o None si no se entiende.

    if not dia:
        return None

    limpio = normalizar(dia)
    if limpio in ("HOY", "AHORA"):
        return dia_de_hoy()
    if limpio == "MANANA":
        return DIAS[(datetime.now(ZONA).weekday() + 1) % 7]

    for nombre in DIAS:
        if normalizar(nombre) in (limpio, limpio.rstrip("S")):
            return nombre
    return None


SQL = f"""
select * except(puesto) from (
    select *,
           -- Ordenar solo por porcentaje hace que una cadena con
           -- descuentos altos tape a todas las demas: "que conviene hoy"
           -- devolvia cinco promos de Coto. Numerando dentro de cada
           -- cadena, primero sale la mejor de cada una y recien despues
           -- la segunda de cada una.
           row_number() over (
               partition by cadena order by porcentaje desc nulls last
           ) as puesto
    from {{TABLA}}
    where (@sin_texto or {{filtro}})
      and (@cadena is null or upper(cadena) like concat('%', @cadena, '%'))
      and (@dia is null or @dia in unnest(dias_efectivos))
      and (@incluir_cuotas or coalesce(tipo_beneficio, '') != 'cuotas')
)
order by puesto, porcentaje desc nulls last, cadena
limit @limite
""".replace("{TABLA}", TABLA).replace(
    "{filtro}",
    """
        (select logical_and(busqueda like concat('%', palabra, '%'))
         from unnest(@palabras) as palabra)
    """,
)


def consultar_descuentos(entidad=None, cadena=None, dia=None, incluir_cuotas=False, limite=LIMITE_POR_DEFECTO):
    
    dia_resuelto = resolver_dia(dia)
    if dia and not dia_resuelto:
        return error(
            f"No entendí el día '{dia}'.",
            "Preguntale al usuario qué día de la semana quiere consultar.",
        )

    palabras = palabras_de(entidad)

    parametros = [
        bigquery.ArrayQueryParameter("palabras", "STRING", palabras),
        bigquery.ScalarQueryParameter("sin_texto", "BOOL", not palabras),
        bigquery.ScalarQueryParameter("cadena", "STRING",
                                      normalizar(cadena) if cadena else None),
        bigquery.ScalarQueryParameter("dia", "STRING", dia_resuelto),
        bigquery.ScalarQueryParameter("incluir_cuotas", "BOOL", bool(incluir_cuotas)),
        bigquery.ScalarQueryParameter("limite", "INT64",
                                      max(1, min(int(limite), MAX_LIMITE))),
    ]

    try:
        trabajo = obtener_cliente().query(
            SQL, job_config=bigquery.QueryJobConfig(query_parameters=parametros)
        )
        filas = list(trabajo.result())
    except Exception as e:
        return error(
            f"Falló la consulta de descuentos: {e}",
            "Decile al usuario que los descuentos no están disponibles en este "
            "momento. NO inventes descuentos ni porcentajes.",
        )

    # La query alterna cadenas para que entren todas en el limite, pero al
    # agente le llegan mas claras agrupadas: si las recibe salteadas
    # tiende a mostrar solo la primera de cada cadena.
    filas = sorted(filas, key=lambda f: (f.cadena, -(f.porcentaje or 0)))
    
    # Sin entidad ni cadena la pregunta es demasiado general ("que conviene
    # hoy") y cualquier lista es adivinanza: casi todos los descuentos
    # dependen del medio de pago. En vez de las promos se devuelve con que
    # se puede pagar, para que el agente pregunte antes de recomendar.
    if not entidad and not cadena:
        return {
            "pregunta_demasiado_general": True,
            "entidades_disponibles": sorted({e for f in filas for e in f.entidades}),
            "cadenas_con_descuento": sorted({f.cadena for f in filas}),
            "instruccion_para_el_agente": (
                "NO listes promociones todavía. La pregunta es muy general y casi "
                "todos los descuentos dependen del medio de pago, así que una lista "
                "sería adivinar. Hacé UNA pregunta corta: con qué paga (banco, "
                "tarjeta o billetera), mencionando algunas de 'entidades_disponibles' "
                "como ejemplo. Cuando te conteste, volvé a llamarme SOLO con "
                "'entidad'. NO agregues 'cadena': sin ese filtro ya te devuelvo "
                "todas las cadenas de una sola vez."
            ),
        }

    if not filas:
        return error(
            "No encontré descuentos con esos filtros.",
            "Decile al usuario que no encontraste nada con esos datos. Aclarale "
            "que sólo cubrís seis cadenas del Gran Rosario (Carrefour, Coto, "
            "DIA, Jumbo, La Gallega y La Reina) y que puede haber descuentos en "
            "otras que no seguís. NO inventes un descuento.",
            cadenas_que_cubro=["Carrefour", "Coto", "DIA", "Jumbo",
                               "La Gallega", "La Reina"],
        )

    sin_porcentaje = sum(1 for f in filas if f.porcentaje is None)

    resultado = {
        "filtros": {
            "entidad": entidad,
            "cadena": cadena,
            "dia": dia_resuelto,
            "incluye_cuotas": bool(incluir_cuotas),
        },
        "encontrados": len(filas),
        "sin_porcentaje": sin_porcentaje,
        "como_responder": (
            "Cuando 'porcentaje' viene en null, la cadena publica el número "
            "dentro de una imagen y no en el texto: contá la promoción con el "
            "tope y el medio de pago, y aclará que el porcentaje no figura. "
            "NUNCA lo estimes ni lo deduzcas de otra promoción. Si "
            "'vigencia_hasta' tiene fecha, mencionala. Si 'dias' viene vacío, "
            "la cadena no publica el día: no afirmes ninguno."
            " SIEMPRE decí con qué medio de pago aplica cada promoción: está en "
            "'con_que'. Si ese campo viene vacío, decí que la cadena no aclara "
            "con qué tarjeta, en vez de dejarlo sin mencionar."
            " Mostrá TODAS las promociones que te devuelvo, agrupadas por cadena. "
            "NO elijas una por cadena ni recortes la lista."
            " Una promo puede aparecer porque el banco que buscás figura entre los "
            "participantes de una billetera (MODO, Cuenta DNI). Fijate en 'texto': "
            "si el banco está ahí, decilo explícito ('con MODO usando tu tarjeta de "
            "Nación'), no la presentes como si fuera de otra entidad."
        ),
        "resultados": [
            {
                "cadena": fila.cadena,
                "porcentaje": fila.porcentaje,
                "cuotas": fila.cuotas,
                "tipo": fila.tipo_beneficio,
                "dias": list(fila.dias),
                "tope": fila.tope,
                "sin_tope": fila.sin_tope,
                "donde": fila.donde,
                "entidades": list(fila.entidades),
                "medios_pago": list(fila.medios_pago),
                # Las cadenas con API traen el medio de pago escrito en
                # prosa; las webs propias solo dejan deducir la entidad.
                # Se unifican en un campo para que el agente no tenga que
                # elegir y termine omitiendo con que se paga.
                "con_que": list(fila.medios_pago) or list(fila.entidades),
                "vigencia_hasta": (fila.vigencia_hasta.isoformat()
                                   if fila.vigencia_hasta else None),
                "texto": fila.texto,
                "url": fila.url,
            }
            for fila in filas
        ],
    }
    
    return resultado


# ------------------------------------------------------------------ pruebas

def mostrar(resultado):
    if resultado.get("error"):
        print(f"  ERROR: {resultado['error']}")
        return

    print(f"  {resultado['encontrados']} promo(s)"
          f"   sin porcentaje: {resultado['sin_porcentaje']}")
    for r in resultado["resultados"]:
        if r["porcentaje"] is not None:
            beneficio = f"{r['porcentaje']:>3}%"
        elif r["cuotas"] is not None:
            beneficio = f"{r['cuotas']:>3}c"
        else:
            beneficio = "  ?"
        entidades = ", ".join(r["entidades"]) or "-"
        print(f"    {beneficio}  {r['cadena']:<12} {entidades[:30]:<30} "
              f"{','.join(r['dias'])[:35]}")


if __name__ == "__main__":
    print("=" * 78)
    print(f"[1] ¿qué descuentos tengo con Personal Pay?")
    mostrar(consultar_descuentos(entidad="personal pay"))

    print("\n[2] ¿los jubilados tienen descuento?")
    mostrar(consultar_descuentos(entidad="jubilados"))

    print("\n[3] ¿qué hay hoy?")
    mostrar(consultar_descuentos(dia="hoy"))

    print("\n[4] La Gallega los sábados")
    mostrar(consultar_descuentos(cadena="La Gallega", dia="sabado"))

    print("\n[5] Credicoop")
    mostrar(consultar_descuentos(entidad="credicoop"))

    print("\n[6] algo que no existe")
    mostrar(consultar_descuentos(entidad="banco falso"))