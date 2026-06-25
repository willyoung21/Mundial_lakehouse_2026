"""DAG: Transformaciones dbt — Silver (staging) → test → Gold (marts).

Disparado por dag_ingest_wc2026 vía TriggerDagRunOperator tras cada ingesta diaria.
También puede ejecutarse manualmente desde la UI de Airflow para re-transformar.

Flujo:
  1. dbt run  → modelos staging (Silver)
  2. dbt test → tests de calidad sobre Silver
  3. dbt run  → modelos marts (Gold)
"""

from datetime import datetime, timedelta

from airflow.operators.bash import BashOperator

from airflow import DAG

DBT_DIR = "/opt/airflow/dbt"
DBT_CMD = "dbt"
DBT_FLAGS = f"--project-dir {DBT_DIR} --profiles-dir {DBT_DIR}"

default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="dag_dbt_transform",
    default_args=default_args,
    description="dbt run staging → dbt test → dbt run marts",
    schedule_interval=None,  # solo se dispara desde dag_ingest_wc2026
    start_date=datetime(2026, 6, 11),
    catchup=False,
    tags=["dbt", "transform", "silver", "gold"],
) as dag:
    run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"{DBT_CMD} run --select path:models/staging {DBT_FLAGS}",
    )

    test_staging = BashOperator(
        task_id="dbt_test_staging",
        bash_command=f"{DBT_CMD} test --select path:models/staging {DBT_FLAGS}",
    )

    run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=f"{DBT_CMD} run --select path:models/marts {DBT_FLAGS}",
    )

    run_staging >> test_staging >> run_marts
