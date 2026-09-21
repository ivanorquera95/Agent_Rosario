"""
Sube los recorridos de colectivos a BigQuery.

Mismo criterio que precios: las tablas van con prefijo raw_ y sin
transformar. Los recorridos casi no cambian, por eso el DAG corre una vez
por semana; WRITE_TRUNCATE deja la carga idempotente igual, para que un
reintento no duplique nada.

Todo se lee como texto a proposito. Los ids de linea tienen letras y las
coordenadas se castean en dbt: dejar que pandas infiera hacia que el tipo
dependiera de la version instalada en cada entorno, y eso ya rompio una
vez cuando la misma limpieza corrio adentro del contenedor de Airflow y
BigQuery leyo las fechas como enteros.
"""

import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

sys.stdout.reconfigure(encoding="utf-8")

PROYECTO = "agent-rosario"
DATASET = "rosario_vivo"
ORIGEN = Path("./data/raw/colectivos")

TABLAS = {
    "raw_colectivos_lineas": "lineas.csv",
    "raw_colectivos_paradas": "paradas_por_linea.csv",
    "raw_colectivos_trazados": "trazados.csv",
}


def subir(cliente, nombre_tabla, archivo):
    if not archivo.exists():
        print(f"  [!] falta {archivo}, se saltea")
        return

    df = pd.read_csv(archivo, dtype=str, encoding="utf-8")
    tabla_id = f"{PROYECTO}.{DATASET}.{nombre_tabla}"

    trabajo = cliente.load_table_from_dataframe(
        df,
        tabla_id,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    )
    trabajo.result()

    print(f"  {nombre_tabla}: {len(df):,} filas, {len(df.columns)} columnas")


def main():
    cliente = bigquery.Client(project=PROYECTO)

    print(f"Subiendo a {PROYECTO}.{DATASET}\n")
    for nombre_tabla, archivo in TABLAS.items():
        subir(cliente, nombre_tabla, ORIGEN / archivo)

    print("\nListo.")


if __name__ == "__main__":
    main()