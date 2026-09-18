#Sube la agenda cultural a BigQuery, cruda.
#Escribe con WRITE_TRUNCATE: cada corrida reemplaza la tabla entera. 

import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import pandas as pd
from google.cloud import bigquery

PROJECT_ID = "agent-rosario"
DATASET_ID = "rosario_vivo"
TABLA = "raw_agenda"
LOCATION = "southamerica-east1"

ORIGEN = Path("./data/raw/agenda/agenda.csv")

COLUMNAS_FECHA = ["fecha_inicio", "fecha_fin"]
COLUMNAS_BOOL = ["es_gratis", "lugar_eventual", "lugar_heredado",
                 "lugar_deducido", "finalizada", "detalle_ok"]
COLUMNAS_FLOAT = ["lugar_latitud", "lugar_longitud"]


def a_booleano(serie):
    # El CSV trae "True"/"False" como texto, y vacio cuando no habia dato.
    mapa = {"True": True, "true": True, "False": False, "false": False}
    return serie.map(lambda v: mapa.get(str(v).strip(), None)).astype("boolean")


def a_lista(valor):
    if not valor or pd.isna(valor):
        return []
    return [c.strip() for c in str(valor).split(";") if c.strip()]


def preparar(df):
    for columna in COLUMNAS_FECHA:
        df[columna] = pd.to_datetime(df[columna], errors="coerce").dt.date

    for columna in COLUMNAS_BOOL:
        if columna in df.columns:
            df[columna] = a_booleano(df[columna])

    for columna in COLUMNAS_FLOAT:
        df[columna] = pd.to_numeric(df[columna], errors="coerce")

    df["fecha_extraccion"] = pd.to_datetime(df["fecha_extraccion"], errors="coerce", utc=True)

    # "Teatro; Música" -> ["Teatro", "Música"]
    df["categorias"] = df["categorias"].map(a_lista)

    return df


ESQUEMA = [
    bigquery.SchemaField("slug", "STRING"),
    bigquery.SchemaField("titulo", "STRING"),
    bigquery.SchemaField("url", "STRING"),
    bigquery.SchemaField("fecha_inicio", "DATE"),
    bigquery.SchemaField("fecha_fin", "DATE"),
    bigquery.SchemaField("etiqueta_serie", "STRING"),
    bigquery.SchemaField("imagen_descripcion", "STRING"),
    bigquery.SchemaField("lugar_id", "STRING"),
    bigquery.SchemaField("lugar_nombre", "STRING"),
    bigquery.SchemaField("lugar_direccion", "STRING"),
    bigquery.SchemaField("lugar_latitud", "FLOAT"),
    bigquery.SchemaField("lugar_longitud", "FLOAT"),
    bigquery.SchemaField("lugar_eventual", "BOOLEAN"),
    bigquery.SchemaField("lugar_heredado", "BOOLEAN"),
    bigquery.SchemaField("lugar_deducido", "BOOLEAN"),
    bigquery.SchemaField("url_padre", "STRING"),
    bigquery.SchemaField("finalizada", "BOOLEAN"),
    bigquery.SchemaField("dias", "STRING"),
    bigquery.SchemaField("hora_texto", "STRING"),
    bigquery.SchemaField("entrada", "STRING"),
    bigquery.SchemaField("es_gratis", "BOOLEAN"),
    bigquery.SchemaField("categorias", "STRING", mode="REPEATED"),
    bigquery.SchemaField("descripcion", "STRING"),
    bigquery.SchemaField("detalle_ok", "BOOLEAN"),
    bigquery.SchemaField("fecha_extraccion", "TIMESTAMP"),
]


def main():
    if not ORIGEN.exists():
        print(f"No encontré {ORIGEN.resolve()}")
        print("Corré antes: uv run .\\scripts\\agenda\\extraccion_agenda.py")
        return

    df = preparar(pd.read_csv(ORIGEN, dtype=str))
    print(f"{len(df)} filas leídas de {ORIGEN}")

    # Las columnas que el esquema no declara no se suben: mejor avisar que
    # perderlas en silencio.
    declaradas = [campo.name for campo in ESQUEMA]
    sobrantes = [c for c in df.columns if c not in declaradas]
    if sobrantes:
        print(f"[!] columnas del CSV que no están en el esquema: {sobrantes}")
    df = df[[c for c in declaradas if c in df.columns]]

    client = bigquery.Client(project=PROJECT_ID)

    dataset = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
    dataset.location = LOCATION
    client.create_dataset(dataset, exists_ok=True)

    tabla_id = f"{PROJECT_ID}.{DATASET_ID}.{TABLA}"
    job = client.load_table_from_dataframe(
        df,
        tabla_id,
        job_config=bigquery.LoadJobConfig(schema=ESQUEMA, write_disposition="WRITE_TRUNCATE"),
    )
    job.result()

    tabla = client.get_table(tabla_id)
    print(f"\n{tabla_id}: {tabla.num_rows} filas, {len(tabla.schema)} columnas")
    print(f"fecha de extracción de los datos: {df['fecha_extraccion'].max()}")


if __name__ == "__main__":
    main()