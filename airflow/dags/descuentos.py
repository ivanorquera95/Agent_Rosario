#Descuentos de supermercados del Gran Rosario. Todos los dias a las 7.


from datetime import datetime, timedelta
import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

ZONA = pendulum.timezone("America/Argentina/Buenos_Aires")
PROYECTO = "/opt/proyecto"

ARGUMENTOS = {
    # Las webs de las cadenas se caen sin aviso: dos reintentos espaciados
    # resuelven casi todos los fallos sin intervenir.
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def paso(nombre: str, script: str) -> BashOperator:
    # Los scripts usan rutas relativas (data/raw/...), asi que todos
    # corren parados en la raiz del proyecto.
    return BashOperator(
        task_id=nombre,
        bash_command=f"cd {PROYECTO} && python scripts/descuentos/{script}",
    )


with DAG(
    dag_id="descuentos",
    description="Descuentos de las seis cadenas del Gran Rosario",
    schedule="0 7 * * *",
    start_date=datetime(2026, 9, 1, tzinfo=ZONA),
    # Sin catchup: los descuentos son el estado de hoy, no una serie
    # historica. Correr los dias que pasaron no aportaria nada.
    catchup=False,
    default_args=ARGUMENTOS,
    tags=["rosario", "descuentos"],
) as dag:

    descuentito = paso("extraer_descuentito", "extraccion_descuentos.py")
    gallega = paso("extraer_la_gallega", "extraccion_lagallega.py")
    reina = paso("extraer_la_reina", "extraccion_lareina.py")

    limpiar = paso("limpiar", "limpieza_descuentos.py")
    subir = paso("subir_a_bigquery", "subir_descuentos_bigquery.py")

    transformar = BashOperator(
        task_id="dbt",
        bash_command=(
            f"cd {PROYECTO}/agent_rosario_dbt && "
            "dbt build --profiles-dir . --select stg_descuentos descuentos_vigentes"
        ),
    )

    [descuentito, gallega, reina] >> limpiar >> subir >> transformar