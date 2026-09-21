#Unifica los descuentos de todas las fuentes en una sola tabla.
#Fuentes: descuentito-data (Carrefour, DIA, Jumbo), la API propia de Coto y las webs de La Gallega y La Reina.


from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
import pandas as pd

ORIGEN = Path("data/raw/descuentos")
DESTINO = Path("data/processed/descuentos")
# Coto queda afuera a proposito: ver decision 4.
CADENAS_DESCUENTITO = {
    "carrefour.json": "Carrefour",
    "dia.json": "DIA",
    "jumbo.json": "Jumbo",
}
DIAS_SEMANA = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]


# ------------------------------------------------------------------

def leer_json(archivo: Path) -> list[dict]:
    with archivo.open(encoding="utf-8") as f:
        datos = json.load(f)
    if isinstance(datos, dict):
        datos = datos.get("promotions", [])
    return datos


def sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def normalizar_dia(dia: str) -> str:
    return sin_acentos(dia.strip()).capitalize()


def normalizar_donde(donde: list[str] | None) -> str | None:
    
    if not donde:
        return None
    hay_online = any(d.lower() == "online" for d in donde)
    hay_sucursal = any(d.lower() != "online" for d in donde)
    if hay_online and hay_sucursal:
        return "ambos"
    return "online" if hay_online else "sucursal"


def hash_corto(*partes) -> str:
    crudo = "|".join(str(p) for p in partes)
    return hashlib.md5(crudo.encode("utf-8")).hexdigest()[:12]


def tope_del_texto(texto: str) -> tuple[int | None, bool]:
    
    limpio = sin_acentos(texto or "").lower()
    sin_tope = "sin tope" in limpio or "sin limite" in limpio

    encontrado = re.search(r"\$\s*(\d[\d.\s]*)", texto or "")
    if not encontrado:
        return None, sin_tope
    numero = encontrado.group(1).replace(".", "").replace(" ", "")
    return (int(numero) if numero.isdigit() else None), sin_tope


def fechas_del_texto(texto: str, hoy: date) -> list[date]:
    fechas = []
    for dia, mes, anio in re.findall(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", texto or ""):
        año = int(anio) if anio else hoy.year
        if año < 100:
            año += 2000
        try:
            fechas.append(date(año, int(mes), int(dia)))
        except ValueError:
            continue
    return fechas


# ------------------------------------------------------------------
# descuentito-data: Carrefour, DIA, Jumbo
# ------------------------------------------------------------------

def filas_de_descuentito(archivo: Path, cadena: str, hoy: date) -> list[dict]:
    filas = []
    descartadas = 0

    for promo in leer_json(archivo):
        hasta = promo.get("validUntil")
        if hasta and hasta < hoy.isoformat():
            descartadas += 1
            continue

        descuento = promo.get("discount") or {}
        tipo = (descuento.get("type") or "").lower()
        valor = descuento.get("value")

        # El tipo viene escrito de varias formas ("porcentaje",
        # "cuotas sin intereses"), asi que se mira por contenido y no por
        # igualdad exacta.
        if "porcentaje" in tipo:
            tipo_beneficio, porcentaje, cuotas = "descuento", valor, None
        elif "cuota" in tipo:
            tipo_beneficio, porcentaje, cuotas = "cuotas", None, valor
        else:
            tipo_beneficio, porcentaje, cuotas = (tipo or None), None, None
            print(f"    tipo de beneficio desconocido: {tipo!r}")

        # Sin dias declarados, la promo corre todos los dias.
        dias = [normalizar_dia(d) for d in (promo.get("weekdays") or ["Todos"])]

        combinaciones = promo.get("paymentMethods") or []
        if not combinaciones:
            desconocidos = promo.get("unknownPaymentMethods") or []
            combinaciones = [desconocidos] if desconocidos else []

        medios_pago = [" + ".join(c) for c in combinaciones if c]
        # El primer elemento de cada combinacion es el banco o la
        # billetera y el resto la tarjeta. Es una heuristica: descuentito
        # no marca cual es cual.
        entidades = list(dict.fromkeys(c[0] for c in combinaciones if c))

        limites = promo.get("limits") or {}
        donde = normalizar_donde(promo.get("where"))
        texto = " ".join(promo.get("restrictions") or []) or None

        # Cuando no hay medio de pago bancario, el requisito es un
        # segmento: jubilados, ANSES, PAMI, socios de un club, empleados
        # publicos. Eso esta escrito en las restricciones, asi que lo
        # buscamos ahi con el mismo diccionario de entidades.
        if not entidades:
            entidades = entidades_del_texto(texto or "")

        # El id es el hash de la promo entera. Elegir campos a mano deja
        # siempre alguno afuera y dos promos distintas terminan con el
        # mismo id; asi, dos promos identicas byte por byte son la misma
        # promo y cualquier diferencia genera un id distinto.
        id_promo = hash_corto(cadena, json.dumps(promo, sort_keys=True, ensure_ascii=False))

        filas.append(
            {
                "cadena": cadena,
                "fuente": "descuentito",
                "id_promo": id_promo,
                "clave_descuento": hash_corto(id_promo, donde),
                "tipo_beneficio": tipo_beneficio,
                "porcentaje": porcentaje,
                "cuotas": cuotas,
                "entidades": entidades,
                "medios_pago": medios_pago,
                "dias": dias,
                "vigencia_desde": promo.get("validFrom"),
                "vigencia_hasta": hasta,
                "tope": limites.get("maxDiscount"),
                "sin_tope": bool(limites.get("explicitlyHasNoLimit")),
                "donde": donde,
                "texto": texto,
                "texto_imagen": None,
                "excluye": promo.get("excludesProducts"),
                "url": promo.get("url"),
                "fecha_extraccion": hoy.isoformat(),
            }
        )

    print(f"  {cadena:<12} {len(filas):>4} promos   ({descartadas} vencidas)")
    return filas


# ------------------------------------------------------------------
# Coto: API propia
# ------------------------------------------------------------------

# El campo "banco" es un numero interno que no dice nada. La unica pista
# de que entidad se trata esta en el nombre del archivo del logo, y esos
# nombres no siguen ningun patron (logo_icbc_1.png, bbva2.png,
# logo_macro_bma3.png), asi que el mapa va explicito. Un icono que no
# este aca se avisa por pantalla en vez de inventarle un nombre.
ENTIDAD_POR_ICONO = {
    "logo_credicoop.png": "Credicoop",
    "logo_icbc_1.png": "ICBC",
    "logo_galicia.png": "Banco Galicia",
    "logo_naranjax2.png": "Naranja X",
    "logo_supervielle2.png": "Banco Supervielle",
    "logo_patagonia2.png": "Banco Patagonia",
    "logo_macro_bma3.png": "Banco Macro",
    "logo_amex1.png": "American Express",
    "logo_comafi.png": "Banco Comafi",
    "logo_ciudad1.png": "Banco Ciudad",
    "logo_columbia_1.png": "Banco Columbia",
    "logo_tci.png": "Tarjeta TCI",
    "logo_nacion_d.png": "Banco Nacion",
    "bbva2.png": "BBVA",
    "logo_modo.png": "MODO",
    "logo_mercadopago.png": "Mercado Pago",
    "logo_visa1.png": "VISA",
    "logo_comunidad.png": "Comunidad Coto",
    "logo_beneficios_anses.png": "ANSES",
    "logo_jubiladosypensionados.png": "Jubilados y pensionados",
    "logo_ciudadania_portena.png": "Ciudadania Porteña",
    "logo_tarjetascredito2.png": "Tarjetas de credito",
}


def dias_de_coto(texto: str | None) -> list[str]:
    
    limpio = sin_acentos(texto or "").strip()
    if not limpio:
        return ["Todos"]

    rango = re.match(r"(?i)^de\s+(\w+)\s+a\s+(\w+)$", limpio)
    if rango:
        desde, hasta = rango.group(1).capitalize(), rango.group(2).capitalize()
        if desde in DIAS_SEMANA and hasta in DIAS_SEMANA:
            i, j = DIAS_SEMANA.index(desde), DIAS_SEMANA.index(hasta)
            return DIAS_SEMANA[i : j + 1] if i <= j else DIAS_SEMANA[i:] + DIAS_SEMANA[: j + 1]

    partes = [p.strip().capitalize() for p in re.split(r",|\sy\s", limpio)]
    reconocidos = [p for p in partes if p in DIAS_SEMANA]
    if reconocidos:
        return reconocidos

    print(f"    dias sin interpretar: {texto!r}")
    return [limpio]


def beneficio_de_coto(texto: str | None) -> tuple[str | None, int | None, int | None]:
   
    crudo = sin_acentos(texto or "").upper()
    numeros = re.findall(r"\d+", crudo)
    if not numeros:
        return None, None, None
    numero = int(numeros[0])
    if "CUOTA" in crudo:
        return "cuotas", None, numero
    return "descuento", numero, None


def vigencia_de_coto(observacion: str, hoy: date) -> tuple[date | None, date | None]:

    fechas = fechas_del_texto(observacion, hoy)
    return (min(fechas), max(fechas)) if fechas else (None, None)


def filas_de_coto(archivo: Path, hoy: date) -> list[dict]:
    with archivo.open(encoding="utf-8") as f:
        datos = json.load(f)

    resultado = (datos or {}).get("result") or {}
    grupos = {
        "online": resultado.get("promocionesDigitales") or [],
        "sucursal": resultado.get("promocionesSucursalesFisicas") or [],
    }

    filas = []
    vencidas = 0
    iconos_desconocidos = set()

    for donde, promos in grupos.items():
        for promo in promos:
            icono = promo.get("icono") or ""
            entidad = ENTIDAD_POR_ICONO.get(icono)
            if entidad is None and icono:
                iconos_desconocidos.add(icono)

            observacion = promo.get("observacion") or ""
            tipo_beneficio, porcentaje, cuotas = beneficio_de_coto(promo.get("textoDescuento"))
            tope, sin_tope = tope_del_texto(observacion)
            desde, hasta = vigencia_de_coto(observacion, hoy)

            if hasta and hasta < hoy:
                vencidas += 1
                continue

            id_promo = f"coto-{promo.get('id')}"
            descripcion = promo.get("descripcion")

            filas.append(
                {
                    "cadena": "Coto",
                    "fuente": "coto_api",
                    "id_promo": id_promo,
                    "clave_descuento": hash_corto(id_promo, donde),
                    "tipo_beneficio": tipo_beneficio,
                    "porcentaje": porcentaje,
                    "cuotas": cuotas,
                    "entidades": [entidad] if entidad else [],
                    # La descripcion es el medio de pago escrito en prosa.
                    # No se puede estructurar sin inventar, asi que va tal
                    # cual y el agente la lee.
                    "medios_pago": [descripcion] if descripcion else [],
                    "dias": dias_de_coto(promo.get("diasVigencia")),
                    "vigencia_desde": desde.isoformat() if desde else None,
                    "vigencia_hasta": hasta.isoformat() if hasta else None,
                    "tope": tope,
                    "sin_tope": sin_tope,
                    "donde": donde,
                    "texto": " ".join(filter(None, [descripcion, observacion])) or None,
                    "texto_imagen": None,
                    "excluye": None,
                    "url": "https://www.coto.com.ar/descuentos/index.asp",
                    "fecha_extraccion": hoy.isoformat(),
                }
            )

    if iconos_desconocidos:
        print("    iconos sin mapear:", ", ".join(sorted(iconos_desconocidos)))

    print(f"  {'Coto':<12} {len(filas):>4} promos   ({vencidas} vencidas)")
    return filas


# ------------------------------------------------------------------
# La Gallega y La Reina: texto libre
# ------------------------------------------------------------------

# Estas dos publican cada promo como un parrafo escrito a mano: el
# porcentaje, el tope, los dias y la vigencia estan todos dentro de la
# misma frase. Todo lo que no se pueda leer con certeza queda en nulo, y
# el texto original viaja entero para que el agente lo pueda citar.

ENTIDADES_CONOCIDAS = {
    "billetera santa fe": "Billetera Santa Fe",
    "credicoop": "Credicoop",
    "cabal": "Cabal",
    "modo": "MODO",
    "mercado pago": "Mercado Pago",
    "personal pay": "Personal Pay",
    "naranja": "Naranja X",
    "galicia": "Banco Galicia",
    "plus pagos": "Plus Pagos",
    "santa fe": "Banco Santa Fe",
    "coinag": "Banco Coinag",
    "supervielle": "Banco Supervielle",
    "municipal": "Banco Municipal",
    "hipotecario": "Banco Hipotecario",
    "macro": "Banco Macro",
    "bbva": "BBVA",
    "santander": "Santander",
    "icbc": "ICBC",
    "jubilado": "Jubilados y pensionados",
    "anses": "ANSES",
    "jubilados y pensionados": "Jubilados y pensionados",
    "pami": "PAMI",
    "mayores de 60": "Mayores de 60",
    "60 años": "Mayores de 60",
    "club la nacion": "Club La Nacion",
    "mi carrefour": "Mi Carrefour",
    "empleadas/os publicos": "Empleados publicos",
    "empleados publicos": "Empleados publicos",
    "cuenta dni": "Cuenta DNI",
    "tarjeta carrefour": "Tarjeta Carrefour",
}


def entidades_del_texto(texto: str) -> list[str]:

    limpio = sin_acentos(texto or "").lower()
    encontradas = sorted(
        (limpio.find(clave), nombre)
        for clave, nombre in ENTIDADES_CONOCIDAS.items()
        if clave in limpio
    )
    return list(dict.fromkeys(nombre for _, nombre in encontradas))


def dias_del_texto(texto: str) -> list[str]:

    limpio = sin_acentos(texto or "").lower()
    return [d for d in DIAS_SEMANA if d.lower() in limpio]


def beneficio_del_texto(texto: str) -> tuple[str | None, int | None, int | None]:

    limpio = sin_acentos(texto or "")
    porcentaje = re.search(r"(\d{1,2})\s*%", limpio)
    if porcentaje:
        return "descuento", int(porcentaje.group(1)), None
    cuotas = re.search(r"(\d{1,2})\s*cuotas", limpio, re.IGNORECASE)
    if cuotas:
        return "cuotas", None, int(cuotas.group(1))
    return None, None, None


def vigencia_del_texto(texto: str, hoy: date) -> tuple[date | None, date | None]:

    fechas = fechas_del_texto(texto, hoy)
    if not fechas:
        return None, None

    limpio = sin_acentos(texto or "").lower()
    if "del " in limpio and " al " in limpio:
        return min(fechas), max(fechas)
    if "hasta" in limpio or "vigencia" in limpio:
        return None, max(fechas)
    return min(fechas), max(fechas)


def filas_de_web(carpeta: Path, cadena: str, hoy: date, juntar_dias: bool) -> list[dict]:

    archivos = sorted(carpeta.glob("*.json"))
    if not archivos:
        print(f"  {cadena:<12} sin archivos en {carpeta}")
        return []
    if not juntar_dias:
        archivos = archivos[-1:]

    por_promo: dict[str, dict] = {}
    vencidas = 0

    for archivo in archivos:
        with archivo.open(encoding="utf-8") as f:
            datos = json.load(f)

        dia_del_archivo = datos.get("dia")
        extraccion = datos.get("fecha_extraccion") or hoy.isoformat()

        for promo in datos.get("promos", []):
            completo = " ".join(
                filter(None, [promo.get("texto"), promo.get("letra_chica")])
            )

            # Lo que dice el cartel se guarda aparte del texto de la web.
            # No se mezclan, porque el texto de la web es el que el agente
            # cita, pero los dos entran en el campo de busqueda: hay
            # promos cuyo unico "jubilados" esta dibujado en la imagen.
            texto_imagen = promo.get("ocr_texto")
            para_buscar = " ".join(filter(None, [completo, texto_imagen]))

            desde, hasta = vigencia_del_texto(completo, hoy)
            if hasta and hasta < hoy:
                vencidas += 1
                continue

            tipo_beneficio, porcentaje, cuotas = beneficio_del_texto(completo)
            tope, sin_tope = tope_del_texto(completo)

            # Lo leido de la imagen completa lo que el texto no dice, y
            # nunca lo pisa: si el porcentaje estaba escrito, ese manda.
            de_imagen = False
            if porcentaje is None and cuotas is None and promo.get("ocr_porcentaje"):
                tipo_beneficio = "descuento"
                porcentaje = promo["ocr_porcentaje"]
                de_imagen = True

            if dia_del_archivo:
                normalizado = normalizar_dia(dia_del_archivo)
                dias = ["Todos"] if normalizado.lower().startswith("todos") else [normalizado]
            else:
                dias = dias_del_texto(completo) or [
                    normalizar_dia(d) for d in (promo.get("ocr_dias") or [])
                ]

            id_promo = f"{cadena.lower().replace(' ', '')}-{promo.get('id_promo')}"

            if id_promo in por_promo:
                # Misma promo vista en otro dia: sumamos el dia nuevo.
                ya = por_promo[id_promo]["dias"]
                por_promo[id_promo]["dias"] = list(dict.fromkeys(ya + dias))
                continue

            por_promo[id_promo] = {
                "cadena": cadena,
                "fuente": "web_propia",
                "id_promo": id_promo,
                "clave_descuento": hash_corto(id_promo, None),
                "tipo_beneficio": tipo_beneficio,
                "porcentaje": porcentaje,
                "cuotas": cuotas,
                "porcentaje_de_imagen": de_imagen,
                "entidades": entidades_del_texto(para_buscar),
                "medios_pago": [],
                "dias": dias,
                "vigencia_desde": desde.isoformat() if desde else None,
                "vigencia_hasta": hasta.isoformat() if hasta else None,
                "tope": tope,
                "sin_tope": sin_tope,
                "donde": None,
                "texto": completo or None,
                "texto_imagen": texto_imagen,
                "excluye": None,
                "url": None,
                "fecha_extraccion": extraccion,
            }

    filas = list(por_promo.values())
    print(
        f"  {cadena:<12} {len(filas):>4} promos   "
        f"({vencidas} vencidas, {len(archivos)} archivo(s))"
    )
    return filas

# ------------------------------------------------------------------

def main() -> None:
    hoy = date.today()
    todas = []

    print("descuentito-data:")
    for nombre, cadena in CADENAS_DESCUENTITO.items():
        archivo = ORIGEN / nombre
        if not archivo.exists():
            print(f"  {cadena:<12} FALTA el archivo {archivo}")
            continue
        todas.extend(filas_de_descuentito(archivo, cadena, hoy))

    print()
    print("API propia:")
    archivo_coto = ORIGEN / "coto_api.json"
    if archivo_coto.exists():
        todas.extend(filas_de_coto(archivo_coto, hoy))
    else:
        print(f"  Coto         FALTA el archivo {archivo_coto}")

    print()
    print("webs propias:")
    todas.extend(filas_de_web(ORIGEN / "lagallega", "La Gallega", hoy, juntar_dias=True))
    todas.extend(filas_de_web(ORIGEN / "lareina", "La Reina", hoy, juntar_dias=False))

    if not todas:
        raise SystemExit("No se genero ninguna fila. Reviso los archivos de origen.")

    df = pd.DataFrame(todas)

    # Si dos filas comparten clave es porque la fuente lista la misma
    # promo mas de una vez: nos quedamos con una.
    antes = len(df)
    df = df.drop_duplicates(subset="clave_descuento").reset_index(drop=True)
    repetidas = antes - len(df)

    df["porcentaje"] = df["porcentaje"].astype("Int64")
    df["cuotas"] = df["cuotas"].astype("Int64")
    df["tope"] = df["tope"].astype("Int64")
    # Las fechas viajan como texto ISO y se convierten en dbt. Dejarlas
    # como datetime hacia que el tipo dependiera de que version de pandas
    # y pyarrow escribiera el parquet: corriendo la limpieza dentro del
    # contenedor de Airflow, BigQuery las leyo como INT64 y dbt no pudo
    # castearlas. Con texto el resultado es identico en todos lados.
    for columna in ("vigencia_desde", "vigencia_hasta", "fecha_extraccion"):
        df[columna] = (
            pd.to_datetime(df[columna], errors="coerce").dt.strftime("%Y-%m-%d")
        )

    df["porcentaje_de_imagen"] = df["porcentaje_de_imagen"].fillna(False).astype(bool)

    DESTINO.mkdir(parents=True, exist_ok=True)
    archivo = DESTINO / "descuentos.parquet"
    df.to_parquet(archivo, index=False)

    print()
    print(f"total:   {len(df)} promos")
    print(f"archivo: {archivo}")
    print()
    print("por cadena y tipo:")
    print(df.groupby(["cadena", "tipo_beneficio"], dropna=False).size().to_string())
    print()
    print("promos repetidas en las fuentes:", repetidas)
    print("sin beneficio reconocido:      ", int(df["tipo_beneficio"].isna().sum()))
    print("sin entidad reconocida:        ", int((df["entidades"].str.len() == 0).sum()))
    
    problemas = df[df["tipo_beneficio"].isna() | (df["entidades"].str.len() == 0)]
    if not problemas.empty:
        print()
        print("casos a revisar:")
        for _, fila in problemas.head(20).iterrows():
            print(f"  [{fila['cadena']:<10}] {str(fila['texto'])[:95]}")


if __name__ == "__main__":
    main()