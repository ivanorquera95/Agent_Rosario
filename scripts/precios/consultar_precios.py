#Consulta de precios del Gran Rosario para el agente.

import sys
import unicodedata
from pathlib import Path
from google.cloud import bigquery
sys.stdout.reconfigure(encoding="utf-8")

PROYECTO = "agent-rosario"
DATASET = "rosario_vivo"
TABLA = f"`{PROYECTO}.{DATASET}.precios_gran_rosario`"
LIMITE_POR_DEFECTO = 12
MAX_LIMITE = 50

_cliente = None

def obtener_cliente():
    # Perezoso: si el cliente se crea al importar, el agente entero no arranca
    # cuando faltan las credenciales.
    global _cliente
    if _cliente is None:
        _cliente = bigquery.Client(project=PROYECTO)
    return _cliente


def normalizar(texto):
    #Misma normalizacion que la columna 'busqueda' del mart: mayusculas y sin acentos.
    sin_acentos = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return sin_acentos.upper().strip()


def palabras_de(texto):
    #Se buscan las palabras por separado y con AND, no la frase entera
    return [p for p in normalizar(texto).split() if p]


def error(mensaje, instruccion, **extra):
    resultado = {"error": mensaje, "instruccion_para_el_agente": instruccion}
    resultado.update(extra)
    return resultado


def filtro_de_palabras(nombre_parametro):
    #Cada palabra tiene que estar en 'busqueda'. Se arma como SQL, no como string.
    return f"""
        (select logical_and(busqueda like concat('%', palabra, '%'))
         from unnest(@{nombre_parametro}) as palabra)
    """


def ejecutar(sql, parametros):
    try:
        trabajo = obtener_cliente().query(
            sql, job_config=bigquery.QueryJobConfig(query_parameters=parametros)
        )
        return list(trabajo.result()), None
    except Exception as e:
        return None, error(
            f"Falló la consulta de precios: {e}",
            "Decile al usuario que los precios no están disponibles en este momento. "
            "NO inventes precios ni comercios.",
        )

# Los datos son de la ultima corrida del DAG (el dia anterior): una promo que
# vencio ayer ya no vale hoy. Si vencio o todavia no empezo, el precio vuelve al
# de lista. Sin fecha en la leyenda ("hasta agotar stock") se asume vigente.
# Va en la consulta y no en dbt porque "hoy" cambia todos los dias.
PRECIOS_HOY = f"""
precios_hoy as (
    select * replace(
        promo_vigente as tiene_promo,
        if(promo_vigente, leyenda_promo1, null) as leyenda_promo1,
        if(tiene_promo and not promo_vigente, precio_lista, precio_efectivo) as precio_efectivo,
        -- El precio por unidad es proporcional al del envase: se escala igual.
        if(tiene_promo and not promo_vigente,
           precio_por_unidad * safe_divide(precio_lista, precio_efectivo),
           precio_por_unidad) as precio_por_unidad
    )
    from (
        select *,
            coalesce(tiene_promo, false)
            and coalesce(promo_desde <= current_date('America/Argentina/Buenos_Aires'), true)
            and coalesce(promo_hasta >= current_date('America/Argentina/Buenos_Aires'), true)
            as promo_vigente
        from {TABLA}
    )
)
"""

# --------------------------------------------------------- buscar precios

SQL_BUSCAR = f"""
  with {PRECIOS_HOY},
  filtrados as (
      select *
      from precios_hoy
    where {filtro_de_palabras('palabras')}
      and (@comercio is null or upper(comercio) like concat('%', @comercio, '%'))
      and (@localidad is null or localidad = @localidad)
      and (not @solo_promos or tiene_promo)
),
mejor_de_cada_comercio as (
    -- Un mismo producto esta en varias sucursales de la misma cadena, muchas
    -- veces al mismo precio. Se deja la sucursal mas barata de cada cadena
    -- para que el agente no repita la misma linea diez veces.
    select *,
           row_number() over (
               partition by id_producto, comercio
               order by precio_efectivo asc
           ) as puesto,
           count(*) over () as total_filas,
           -- Relevancia antes que precio: buscar "leche" y ordenar solo por
           -- precio devuelve chocolatines de dulce de leche, porque son mas
           -- baratos que cualquier sachet. La palabra pesa mas si abre la
           -- descripcion, que es donde va el sustantivo del producto.
           case
               when busqueda like concat(@principal, '%') then 3
               when regexp_contains(busqueda, concat(r'\b', @principal, r'\b')) then 2
               else 1
           end as relevancia
    from filtrados
)
select * except(puesto, relevancia)
from mejor_de_cada_comercio
where puesto = 1
order by relevancia desc, precio_por_unidad asc nulls last, precio_efectivo asc
limit @limite
"""


def buscar_precios(producto, comercio=None, localidad=None, solo_promos=False, limite=LIMITE_POR_DEFECTO):
    #¿donde esta mas barata la leche?" -> buscar_precios("leche")
    #"¿que promos hay en Coto?" -> buscar_precios("", comercio="Coto", solo_promos=True)
    
    palabras = palabras_de(producto)
    if not palabras and not comercio and not solo_promos:
        return error(
            "No me dijiste qué producto buscar.",
            "Preguntale al usuario qué producto quiere comparar.",
        )

    parametros = [
        bigquery.ArrayQueryParameter("palabras", "STRING", palabras),
        # La primera palabra es la que manda: la gente escribe el sustantivo
        # adelante ("leche descremada", "fideos guiseros").
        bigquery.ScalarQueryParameter("principal", "STRING",
                                      palabras[0] if palabras else ""),
        bigquery.ScalarQueryParameter("comercio", "STRING",
                                      normalizar(comercio) if comercio else None),
        bigquery.ScalarQueryParameter("localidad", "STRING", localidad),
        bigquery.ScalarQueryParameter("solo_promos", "BOOL", bool(solo_promos)),
        bigquery.ScalarQueryParameter("limite", "INT64",
                                      max(1, min(int(limite), MAX_LIMITE))),
    ]

    filas, fallo = ejecutar(SQL_BUSCAR, parametros)
    if fallo:
        return fallo

    if not filas:
        return error(
            f"No encontré ningún producto que coincida con '{producto}'.",
            "Decile al usuario que no está en los datos. Puede ser que el "
            "supermercado no lo publique o que se escriba distinto. NO "
            "inventes un precio ni ofrezcas otro producto como si fuera ese.",
        )
    # El modelo compara mal: con una lista de precios de envases distintos elige
    # el numero mas chico y se olvida del precio por litro. Se le da masticado
    # quien gana, en vez de esperar que lo deduzca.
    comparables = [f for f in filas if f.precio_por_unidad is not None]
    ganador = min(comparables, key=lambda f: f.precio_por_unidad) if comparables else None
    # El modelo agrupaba por marca ("Casanto", "Ilolay") como si fueran
    # supermercados. Se entrega ya agrupado. El orden de los grupos es el de la
    # consulta: primero el supermercado con el mejor resultado.
    por_supermercado = {}
    for fila in filas:
        por_supermercado.setdefault(fila.comercio, []).append({
            "producto": fila.descripcion,
            "marca": fila.marca,
            "presentacion": f"{fila.cantidad_presentacion} {fila.unidad_presentacion}",
            "precio": fila.precio_efectivo,
            "precio_por_unidad": fila.precio_por_unidad,
            "unidad": fila.unidad_comparable,
            "unidad_referencia": fila.unidad_referencia,
            "precio_lista": fila.precio_lista,
            "tiene_promo": fila.tiene_promo,
            "promo": fila.leyenda_promo1,
            "sucursal": fila.sucursal,
            "direccion": fila.sucursal_direccion,
            "localidad": fila.localidad,
            "codigo_barras": fila.id_producto,
        })
        
    return {
        "busqueda": producto,
        "filtros": {"comercio": comercio, "localidad": localidad,
                    "solo_promos": solo_promos},
        "total_coincidencias": filas[0].total_filas,
        "mostrados": len(filas),
        "fecha_datos": filas[0].fecha_extraccion.isoformat(),
        "ordenado_por": "precio por unidad de medida (litro o kilo), no por "
                        "precio del envase",
        "aviso": "Precios de la última publicación de SEPA, puede no coincidir "
                 "con la góndola de hoy.",
        "mas_barato_por_unidad": {
            "producto": ganador.descripcion,
            "supermercado": ganador.comercio,
            "precio_por_unidad": ganador.precio_por_unidad,
            "unidad": ganador.unidad_comparable,
            "precio_envase": ganador.precio_efectivo,
            "sucursal": ganador.sucursal,
        } if ganador else None,
        "como_responder": (
            "El más barato es el de 'mas_barato_por_unidad', que es el de menor "
            "precio por kilo o litro. NO elijas el del número más chico en "
            "'precio': ese es el precio del envase, y un envase más chico "
            "siempre cuesta menos sin ser más barato."
        ),
        "por_supermercado": [
              {"supermercado": nombre, "productos": productos}
              for nombre, productos in por_supermercado.items()
          ],
    }


# ------------------------------------------------------ comparar un producto

SQL_ELEGIR_PRODUCTO = f"""
select
    id_producto,
    any_value(descripcion) as descripcion,
    count(distinct comercio) as cantidad_comercios,
    min(precio_efectivo) as precio_minimo
from {TABLA}
where {filtro_de_palabras('palabras')}
group by id_producto
-- El que esta en mas cadenas primero: es el que sirve para comparar.
order by cantidad_comercios desc, precio_minimo asc
limit 1
"""

SQL_COMPARAR = f"""
select * except(puesto) from (
    select *,
           row_number() over (
               partition by comercio order by precio_efectivo asc
           ) as puesto
    from {TABLA}
    where id_producto = @id_producto
)
where puesto = 1
order by precio_efectivo asc
"""


def comparar_producto(producto):
    #"¿conviene Coto o La Reina para la coca?" -> comparar_producto("coca cola 2.25")
    #Compara por codigo de barras, no por nombre: el mismo articulo se llama distinto en cada cadena, pero el EAN es el mismo.
    
    palabras = palabras_de(producto)
    if not palabras:
        return error(
            "No me dijiste qué producto comparar.",
            "Preguntale al usuario qué producto quiere comparar entre cadenas.",
        )

    parametros = [bigquery.ArrayQueryParameter("palabras", "STRING", palabras)]
    elegido, fallo = ejecutar(SQL_ELEGIR_PRODUCTO, parametros)
    if fallo:
        return fallo

    if not elegido:
        return error(
            f"No encontré ningún producto que coincida con '{producto}'.",
            "Decile al usuario que no está en los datos. NO inventes un precio.",
        )

    producto_elegido = elegido[0]

    filas, fallo = ejecutar(
        SQL_COMPARAR,
        [bigquery.ScalarQueryParameter("id_producto", "STRING",
                                       producto_elegido.id_producto)],
    )
    if fallo:
        return fallo

    precios = [fila.precio_efectivo for fila in filas]
    diferencia = round(max(precios) - min(precios), 2) if len(precios) > 1 else 0

    return {
        "producto": producto_elegido.descripcion,
        "codigo_barras": producto_elegido.id_producto,
        "comercios_que_lo_tienen": len(filas),
        "diferencia_maxima": diferencia,
        "fecha_datos": filas[0].fecha_extraccion.isoformat(),
        "aviso": "Precios de la última publicación de SEPA, puede no coincidir "
                 "con la góndola de hoy.",
        "por_comercio": [
            {
                "comercio": fila.comercio,
                "precio": fila.precio_efectivo,
                "precio_lista": fila.precio_lista,
                "tiene_promo": fila.tiene_promo,
                "promo": fila.leyenda_promo1,
                "sucursal": fila.sucursal,
                "localidad": fila.localidad,
            }
            for fila in filas
        ],
    }

# ------------------------------------------------------------------ pruebas

def mostrar(resultado):
    if resultado.get("error"):
        print(f"  ERROR: {resultado['error']}")
        return

    if "por_comercio" in resultado:
        print(f"  {resultado['producto']}  [{resultado['codigo_barras']}]")
        print(f"  en {resultado['comercios_que_lo_tienen']} cadena(s), "
              f"diferencia de ${resultado['diferencia_maxima']}")
        for c in resultado["por_comercio"]:
            promo = f"  (promo: {c['promo']})" if c["tiene_promo"] else ""
            print(f"    ${c['precio']:>10,.2f}  {c['comercio']:<22} {c['sucursal']}{promo}")
        return

    print(f"  {resultado['total_coincidencias']} coincidencia(s), "
          f"mostrando {resultado['mostrados']}  (ordenado por precio por unidad)")
    for grupo in resultado["por_supermercado"]:
        print(f"  {grupo['supermercado']}")
        for r in grupo["productos"]:
            promo = "  [promo]" if r["tiene_promo"] else ""
            unidad = (f"${r['precio_por_unidad']:>9,.2f}/{r['unidad']}"
                      if r["precio_por_unidad"] else "        s/d")
            print(f"    {unidad}   ${r['precio']:>9,.2f}  {r['producto'][:50]}{promo}")


if __name__ == "__main__":
    print("=" * 70)
    print("[1] ¿dónde está más barata la leche?")
    mostrar(buscar_precios("leche"))

    print("\n[2] fideos, solo con promoción")
    mostrar(buscar_precios("fideos", solo_promos=True))

    print("\n[3] yerba en Funes")
    mostrar(buscar_precios("yerba", localidad="Funes"))

    print("\n[4] comparar coca cola entre cadenas")
    mostrar(comparar_producto("coca cola 2.25"))

    print("\n[5] un producto que no existe")
    mostrar(buscar_precios("caviar iraní"))

