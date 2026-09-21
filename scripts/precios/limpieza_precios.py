#Filtra y limpia los precios de SEPA.


import csv
import sys
from pathlib import Path
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun.localidades import LOCALIDADES, localidad_de, normalizar

ORIGEN = Path("./data/raw/precios")
DESTINO = Path("./data/processed/precios")
ARCHIVO_METADATOS = ORIGEN / "extraccion.txt"
SEPARADOR = "|"
PROVINCIA_SANTA_FE = "AR-S"
# utf-8-sig y no utf-8: los CSV de SEPA traen BOM, y sin esto la primera
# columna del encabezado queda con un caracter invisible pegado adelante.
CODIFICACION = "utf-8-sig"
# 200 mil filas por trozo: el archivo mas grande tiene ~4 millones, asi que
# nunca hay mas de ese pedazo en memoria.
FILAS_POR_TROZO = 200_000
LOCALIDADES_NORMALIZADAS = {normalizar(nombre) for nombre in LOCALIDADES}


def leer_fecha_extraccion():
    if not ARCHIVO_METADATOS.exists():
        return None
    for linea in ARCHIVO_METADATOS.read_text(encoding="utf-8").splitlines():
        if linea.startswith("fecha_extraccion="):
            return linea.split("=", 1)[1].strip()
    return None


def a_entero(valor):
    valor = (valor or "").strip()
    return int(valor) if valor.isdigit() else None


# ------------------------------------------------------------- sucursales

def es_del_gran_rosario(fila):
    #True si la sucursal esta en el Gran Rosario.
    #Primero por coordenadas, que es el dato confiable. 
    #Si no las tiene, se cae al nombre de la localidad: SEPA pone barrios ("Fisherton", "Paternal") en vez de ciudades, asi que el nombre solo sirve como ultimo recurso.
    
    latitud = (fila.get("sucursales_latitud") or "").strip()
    longitud = (fila.get("sucursales_longitud") or "").strip()

    if latitud and longitud:
        try:
            return localidad_de(float(latitud), float(longitud)) is not None
        except ValueError:
            pass

    if (fila.get("sucursales_provincia") or "").strip() != PROVINCIA_SANTA_FE:
        return False
    return normalizar(fila.get("sucursales_localidad")) in LOCALIDADES_NORMALIZADAS


def sucursales_del_gran_rosario():
    #Recorre los sucursales.csv y devuelve las que nos interesan.
    elegidas = []
    sin_coordenadas = 0

    for archivo in sorted(ORIGEN.rglob("sucursales.csv")):
        with open(archivo, encoding=CODIFICACION) as f:
            for fila in csv.DictReader(f, delimiter=SEPARADOR):
                if not (fila.get("sucursales_latitud") or "").strip():
                    sin_coordenadas += 1
                if not es_del_gran_rosario(fila):
                    continue

                latitud = (fila.get("sucursales_latitud") or "").strip()
                longitud = (fila.get("sucursales_longitud") or "").strip()

                elegidas.append({
                    "id_comercio": a_entero(fila.get("id_comercio")),
                    "id_bandera": a_entero(fila.get("id_bandera")),
                    "id_sucursal": a_entero(fila.get("id_sucursal")),
                    "sucursales_nombre": (fila.get("sucursales_nombre") or "").strip(),
                    "sucursales_tipo": (fila.get("sucursales_tipo") or "").strip(),
                    "sucursales_calle": (fila.get("sucursales_calle") or "").strip(),
                    "sucursales_numero": (fila.get("sucursales_numero") or "").strip(),
                    "sucursales_localidad": (fila.get("sucursales_localidad") or "").strip(),
                    "sucursales_provincia": (fila.get("sucursales_provincia") or "").strip(),
                    "latitud": float(latitud) if latitud else None,
                    "longitud": float(longitud) if longitud else None,
                    "localidad_gran_rosario": (
                        localidad_de(float(latitud), float(longitud))
                        if latitud and longitud else None
                    ),
                })

    print(f"  {len(elegidas)} sucursal(es) del Gran Rosario")
    print(f"  ({sin_coordenadas} sucursales del país sin coordenadas, resueltas por nombre)")

    por_localidad = {}
    for s in elegidas:
        clave = s["localidad_gran_rosario"] or s["sucursales_localidad"]
        por_localidad[clave] = por_localidad.get(clave, 0) + 1
    for localidad, cantidad in sorted(por_localidad.items(), key=lambda x: -x[1]):
        print(f"      {cantidad:>3}  {localidad}")

    return elegidas


# -------------------------------------------------------------- productos

COLUMNAS_TEXTO = [
    "productos_descripcion", "productos_marca",
    "productos_unidad_medida_presentacion", "productos_unidad_medida_referencia",
    "productos_leyenda_promo1", "productos_leyenda_promo2",
]

COLUMNAS_NUMERO = {
    "precio_lista": "productos_precio_lista",
    "precio_referencia": "productos_precio_referencia",
    "precio_promo1": "productos_precio_unitario_promo1",
    "precio_promo2": "productos_precio_unitario_promo2",
    "cantidad_presentacion": "productos_cantidad_presentacion",
    "cantidad_referencia": "productos_cantidad_referencia",
}


def procesar_productos(claves, fecha_extraccion):
    #Lee los productos.csv de a trozos y se queda con los del Gran Rosario.
    
    claves_gran_rosario = {
        (str(c["id_comercio"]), str(c["id_sucursal"])) for c in claves
    }

    pedazos = []
    total_nacional = 0

    for archivo in sorted(ORIGEN.rglob("productos.csv")):
        for trozo in pd.read_csv(
            archivo,
            sep=SEPARADOR,
            encoding=CODIFICACION,
            dtype=str,
            chunksize=FILAS_POR_TROZO,
            on_bad_lines="skip",
        ):
            total_nacional += len(trozo)

            indice = pd.MultiIndex.from_frame(trozo[["id_comercio", "id_sucursal"]])
            del_gran_rosario = trozo[indice.isin(claves_gran_rosario)]

            if not del_gran_rosario.empty:
                pedazos.append(del_gran_rosario)

    print(f"  {total_nacional:,} filas en el dataset nacional")

    if not pedazos:
        return pd.DataFrame(), total_nacional

    df = pd.concat(pedazos, ignore_index=True)

    for columna in COLUMNAS_TEXTO:
        df[columna] = df[columna].fillna("").str.strip()

    for nueva, original in COLUMNAS_NUMERO.items():
        df[nueva] = pd.to_numeric(df[original], errors="coerce")

    for columna in ("id_comercio", "id_bandera", "id_sucursal"):
        df[columna] = pd.to_numeric(df[columna], errors="coerce").astype("Int64")

    df["id_producto"] = df["id_producto"].fillna("").str.strip()
    df["fecha_extraccion"] = fecha_extraccion

    df = df.rename(columns={
        "productos_descripcion": "descripcion",
        "productos_marca": "marca",
        "productos_unidad_medida_presentacion": "unidad_presentacion",
        "productos_unidad_medida_referencia": "unidad_referencia",
        "productos_leyenda_promo1": "leyenda_promo1",
        "productos_leyenda_promo2": "leyenda_promo2",
    })

    df = df[[
        "id_comercio", "id_bandera", "id_sucursal", "id_producto",
        "descripcion", "marca",
        "cantidad_presentacion", "unidad_presentacion",
        "precio_lista", "precio_referencia",
        "cantidad_referencia", "unidad_referencia",
        "precio_promo1", "leyenda_promo1",
        "precio_promo2", "leyenda_promo2",
        "fecha_extraccion",
    ]]

    return df.drop_duplicates(
        subset=["id_comercio", "id_sucursal", "id_producto"]
    ), total_nacional


# -------------------------------------------------------------- comercios

def procesar_comercios(fecha_extraccion):
    #Los comercio.csv son 47 filas cada uno: se leen enteros sin problema.
    pedazos = []

    for archivo in sorted(ORIGEN.rglob("comercio.csv")):
        pedazos.append(pd.read_csv(archivo, sep=SEPARADOR,
                                   encoding=CODIFICACION, dtype=str))

    df = pd.concat(pedazos, ignore_index=True)

    for columna in ("comercio_razon_social", "comercio_bandera_nombre"):
        df[columna] = df[columna].fillna("").str.strip()

    # Algunas filas traen basura en id_comercio: se descartan avisando.
    validas = df["id_comercio"].fillna("").str.fullmatch(r"\d+")
    if (~validas).any():
        print(f"  [!] {(~validas).sum()} fila(s) con id_comercio inválido, se descartan")
    df = df[validas]

    df["id_comercio"] = df["id_comercio"].astype("Int64")
    df["id_bandera"] = pd.to_numeric(df["id_bandera"], errors="coerce").astype("Int64")
    df["fecha_extraccion"] = fecha_extraccion

    df = df.rename(columns={
        "comercio_cuit": "cuit",
        "comercio_razon_social": "razon_social",
        "comercio_bandera_nombre": "nombre_bandera",
    })

    # La clave real es (id_comercio, id_bandera): el comercio 10 son Carrefour,
    # Maxi, Express y Market. Joinear solo por id_comercio multiplica los precios.
    return df[[
        "id_comercio", "id_bandera", "cuit", "razon_social",
        "nombre_bandera", "fecha_extraccion",
    ]].drop_duplicates(subset=["id_comercio", "id_bandera"])


# --------------------------------------------------------------- escritura

def escribir(df, nombre):
    #Un archivo por tabla, no una carpeta.

    DESTINO.mkdir(parents=True, exist_ok=True)
    archivo = DESTINO / f"{nombre}.parquet"
    df.to_parquet(archivo, index=False)
    return archivo


def main():
    fecha_extraccion = leer_fecha_extraccion()
    if fecha_extraccion is None:
        print("No encontré la fecha de extracción.")
        print("Corré antes: uv run .\\scripts\\precios\\extraccion_precios.py")
        return

    print(f"Fecha de extracción: {fecha_extraccion}\n")

    print("Sucursales")
    claves = sucursales_del_gran_rosario()
    if not claves:
        print("\n[!] No encontré ninguna sucursal del Gran Rosario")
        return

    for s in claves:
        s["fecha_extraccion"] = fecha_extraccion
    escribir(pd.DataFrame(claves), "sucursales")

    print("\nComercios")
    df_comercios = procesar_comercios(fecha_extraccion)
    escribir(df_comercios, "comercios")
    print(f"  {len(df_comercios)} filas")

    print("\nProductos")
    df_productos, total_nacional = procesar_productos(claves, fecha_extraccion)
    if df_productos.empty:
        print("  [!] No quedó ninguna fila del Gran Rosario")
        return

    escribir(df_productos, "productos")

    con_promo = df_productos["precio_promo1"].notna().sum()
    print(f"  {len(df_productos):,} filas del Gran Rosario "
          f"({len(df_productos) / total_nacional:.2%} del nacional)")
    print(f"  {con_promo:,} con promoción")

    print(f"\nParquet en {DESTINO.resolve()}")


if __name__ == "__main__":
    main()