#Agenda cultural de Rosario. Todos los dias a las 7.

from datetime import datetime, timedelta
import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

ZONA = pendulum.timezone("America/Argentina/Buenos_Aires")
PROYECTO = "/opt/proyecto"

ARGUMENTOS = {
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


with DAG(
    dag_id="agenda",
    description="Agenda cultural de Rosario",
    schedule="0 7 * * *",
    start_date=datetime(2026, 9, 1, tzinfo=ZONA),
    catchup=False,
    default_args=ARGUMENTOS,
    tags=["rosario", "agenda"],
) as dag:

    extraer = BashOperator(
        task_id="extraer",
        bash_command=f"cd {PROYECTO} && python scripts/agenda/extraccion_agenda.py",
        execution_timeout=timedelta(minutes=30),
    )

    subir = BashOperator(
        task_id="subir_a_bigquery",
        bash_command=f"cd {PROYECTO} && python scripts/agenda/subir_agenda_bigquery.py",
        execution_timeout=timedelta(minutes=15),
    )

    transformar = BashOperator(
        task_id="dbt",
        bash_command=(
            f"cd {PROYECTO}/agent_rosario_dbt && "
            "dbt build --profiles-dir . --select stg_agenda eventos_agenda"
        ),
        execution_timeout=timedelta(minutes=15),
    )

    extraer >> subir >> transformar