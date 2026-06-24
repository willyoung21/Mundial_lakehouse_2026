"""DAG: Ingesta diaria WC2026 desde worldcup26.ir → Bronze (MinIO) → Neon.

Trigger: diario 06:00 UTC (partidos del día anterior ya terminaron).
El DAG corre el cliente de worldcup26.ir para la fecha de ayer, luego
carga el Parquet resultante a Neon y dispara el DAG de transformaciones dbt.
"""

import sys
sys.path.insert(0, '/opt/airflow')

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner": "airflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dag_ingest_wc2026",
    default_args=default_args,
    description="Ingesta diaria WC2026 desde worldcup26.ir → Bronze → Neon",
    schedule_interval="0 6 * * *",
    start_date=datetime(2026, 6, 11),
    catchup=False,
    tags=["ingestion", "wc2026", "bronze"],
) as dag:

    def _ingest_fixtures(**context) -> None:
        from datetime import date
        from ingestion.worldcup26_client import run_daily_ingestion, WC2026_END_DATE

        exec_date = context["data_interval_end"].date()

        # Ayer (resultado real del día anterior)
        yesterday = (exec_date - timedelta(days=1)).isoformat()
        run_daily_ingestion(yesterday)

        # Próximos 14 días (fixtures futuros con home_score=NULL)
        for i in range(14):
            future = exec_date + timedelta(days=i)
            if future > WC2026_END_DATE:
                break
            run_daily_ingestion(future.isoformat())

    def _load_to_neon(**context) -> None:
        from ingestion.bronze_to_neon import run
        run(table="api_fixtures")

    ingest = PythonOperator(
        task_id="fetch_fixtures",
        python_callable=_ingest_fixtures,
    )

    load_neon = PythonOperator(
        task_id="load_to_neon",
        python_callable=_load_to_neon,
    )

    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt_transform",
        trigger_dag_id="dag_dbt_transform",
        wait_for_completion=False,
    )

    ingest >> load_neon >> trigger_dbt
