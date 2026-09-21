#Recorridos de colectivos del Gran Rosario. Domingos a las 3.

from datetime import datetime, timedelta
import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

ZONA = pendulum.timezone("America/Argentina/Buenos_Aires")
PROYECTO = "/opt/proyecto"

ARGUMENTOS = {
    "retries": 2,
    "retry_delay": timedelta(minutes=30),
}


with DAG(
    dag_id="colectivos",
    description="Recorridos y paradas de colectivos del Gran Rosario",
    schedule="0 3 * * 0",
    start_date=datetime(2026, 9, 1, tzinfo=ZONA),
    catchup=False,
    default_args=ARGUMENTOS,
    tags=["rosario", "colectivos"],
) as dag:

    extraer = BashOperator(
        task_id="extraer_recorridos",
        bash_command=f"cd {PROYECTO} && python scripts/colectivos/extraccion_recorridos.py",
        execution_timeout=timedelta(hours=2),
    )

    subir = BashOperator(
        task_id="subir_a_bigquery",
        bash_command=f"cd {PROYECTO} && python scripts/colectivos/subir_recorridos_bigquery.py",
        execution_timeout=timedelta(minutes=30),
    )

    extraer >> subir