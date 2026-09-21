#Precios de SEPA para el Gran Rosario. Todos los dias a las 15.


from datetime import datetime, timedelta
import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

ZONA = pendulum.timezone("America/Argentina/Buenos_Aires")
PROYECTO = "/opt/proyecto"

ARGUMENTOS = {
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
}


with DAG(
    dag_id="precios",
    description="Precios de supermercados del Gran Rosario (SEPA)",
    schedule="0 15 * * *",
    start_date=datetime(2026, 9, 1, tzinfo=ZONA),
    # Sin catchup: SEPA publica una foto del dia. Correr los dias que
    # pasaron bajaria el archivo de hoy una y otra vez.
    catchup=False,
    default_args=ARGUMENTOS,
    tags=["rosario", "precios"],
) as dag:

    extraer = BashOperator(
        task_id="extraer_sepa",
        bash_command=f"cd {PROYECTO} && python scripts/precios/extraccion_precios.py",
        execution_timeout=timedelta(hours=1),
    )

    limpiar = BashOperator(
        task_id="limpiar",
        bash_command=f"cd {PROYECTO} && python scripts/precios/limpieza_precios.py",
        execution_timeout=timedelta(minutes=45),
    )

    subir = BashOperator(
        task_id="subir_a_bigquery",
        bash_command=f"cd {PROYECTO} && python scripts/precios/subir_precios_bigquery.py",
        execution_timeout=timedelta(minutes=30),
    )

    transformar = BashOperator(
        task_id="dbt",
        bash_command=(
            f"cd {PROYECTO}/agent_rosario_dbt && "
            "dbt build --profiles-dir . --select "
            "stg_precios_productos stg_precios_sucursales stg_precios_comercios "
            "precios_gran_rosario"
        ),
        execution_timeout=timedelta(minutes=20),
    )

    extraer >> limpiar >> subir >> transformar