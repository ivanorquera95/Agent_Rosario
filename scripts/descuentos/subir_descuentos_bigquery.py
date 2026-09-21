#Sube la tabla de descuentos a BigQuery.

import sys
from pathlib import Path
from google.cloud import bigquery
sys.stdout.reconfigure(encoding="utf-8")

PROYECTO = "agent-rosario"
DATASET = "rosario_vivo"
ORIGEN = Path("./data/processed/descuentos/descuentos.parquet")
TABLA = "raw_descuentos"

def main():
    if not ORIGEN.exists():
        raise SystemExit(f"Falta {ORIGEN}. Corre primero limpieza_descuentos.py")

    cliente = bigquery.Client(project=PROYECTO)
    tabla_id = f"{PROYECTO}.{DATASET}.{TABLA}"

    print(f"Subiendo a {tabla_id}\n")

    # Parquet guarda las listas como una estructura anidada de tres
    # niveles (list -> element). Sin enable_list_inference, BigQuery la
    # copia tal cual y queda un STRUCT sobre el que no se puede hacer
    # unnest; con esta opcion la lee como ARRAY<STRING>, que es lo que
    # necesita la consulta del agente.
    opciones_parquet = bigquery.ParquetOptions()
    opciones_parquet.enable_list_inference = True

    with ORIGEN.open("rb") as archivo:
        trabajo = cliente.load_table_from_file(
            archivo,
            tabla_id,
            job_config=bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.PARQUET,
                write_disposition="WRITE_TRUNCATE",
                parquet_options=opciones_parquet,
            ),
        )
    trabajo.result()

    tabla = cliente.get_table(tabla_id)
    print(f"  {TABLA}: {tabla.num_rows:,} filas, {len(tabla.schema)} columnas")

    # Chequeo de que los arrays viajaron como arrays y no como texto.
    consulta = f"""
        select
            cadena,
            count(*) as promos,
            countif(array_length(dias) > 0) as con_dias,
            countif(array_length(entidades) > 0) as con_entidad
        from `{tabla_id}`
        group by cadena
        order by promos desc
    """
    print()
    for fila in cliente.query(consulta).result():
        print(
            f"  {fila.cadena:<12} {fila.promos:>4} promos   "
            f"{fila.con_dias:>4} con dias   {fila.con_entidad:>4} con entidad"
        )

    print("\nListo. Los modelos de dbt van despues.")


if __name__ == "__main__":
    main()