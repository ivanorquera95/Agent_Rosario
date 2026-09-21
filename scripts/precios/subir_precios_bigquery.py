#Sube los parquet de precios a BigQuery, tal cual salen de la limpieza.


import sys
from pathlib import Path
import pandas as pd
from google.cloud import bigquery
sys.stdout.reconfigure(encoding="utf-8")

PROYECTO = "agent-rosario"
DATASET = "rosario_vivo"
ORIGEN = Path("./data/processed/precios")
TABLAS = {
    "raw_precios_productos": "productos.parquet",
    "raw_precios_sucursales": "sucursales.parquet",
    "raw_precios_comercios": "comercios.parquet",
}


def subir(cliente, nombre_tabla, archivo):
    if not archivo.exists():
        print(f"  [!] falta {archivo}, se saltea")
        return

    df = pd.read_parquet(archivo)
    tabla_id = f"{PROYECTO}.{DATASET}.{nombre_tabla}"

    trabajo = cliente.load_table_from_dataframe(
        df, tabla_id,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    )
    trabajo.result()

    print(f"  {nombre_tabla}: {len(df):,} filas")


def main():
    cliente = bigquery.Client(project=PROYECTO)

    print(f"Subiendo a {PROYECTO}.{DATASET}\n")
    for nombre_tabla, archivo in TABLAS.items():
        subir(cliente, nombre_tabla, ORIGEN / archivo)

    print("\nListo. La transformación a dim_* y fact_* la hace dbt.")


if __name__ == "__main__":
    main()