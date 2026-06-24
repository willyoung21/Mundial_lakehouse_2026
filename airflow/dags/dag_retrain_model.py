"""DAG: Reentrenamiento semanal del modelo de predicción de partidos.

Trigger: semanal los lunes 07:00 UTC (después del pipeline diario de ingesta).
El DAG toma las features del Gold layer, reentrena el Random Forest y
sobreescribe models/model_winner_predictor.pkl en el volumen compartido.

La FastAPI carga el modelo en arranque — requiere restart del contenedor api
para que tome el modelo nuevo. En producción: reemplazar por hot-reload.
"""

import sys
sys.path.insert(0, '/opt/airflow')

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

MODEL_PATH = "/opt/airflow/models/model_winner_predictor.pkl"

default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="dag_retrain_model",
    default_args=default_args,
    description="Reentrenamiento semanal del modelo RF de predicción WC2026",
    schedule_interval="0 7 * * 1",   # lunes 07:00 UTC
    start_date=datetime(2026, 6, 23),
    catchup=False,
    tags=["ml", "train", "model"],
) as dag:

    def _build_features(**context) -> None:
        """Verifica que el Gold layer tiene suficientes datos para entrenar."""
        import os
        from sqlalchemy import create_engine, text

        url = (
            f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
            f"@{os.environ['POSTGRES_HOST']}/{os.environ['POSTGRES_DB']}?sslmode=require"
        )
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            n = conn.execute(
                text("SELECT COUNT(*) FROM gold.fact_matches WHERE result IS NOT NULL")
            ).scalar()

        if n < 10:
            raise ValueError(f"Solo {n} partidos con resultado en Gold — demasiado poco para entrenar.")

        print(f"Gold layer OK: {n} partidos completados disponibles para entrenamiento.")

    def _train(**context) -> None:
        """Entrena el modelo y guarda el artefacto."""
        from ml.train import train
        Path(MODEL_PATH).parent.mkdir(parents=True, exist_ok=True)
        train()

    def _verify(**context) -> None:
        """Verifica que el modelo guardado se puede cargar y predice correctamente."""
        import pickle
        import numpy as np

        if not Path(MODEL_PATH).exists():
            raise FileNotFoundError(f"Modelo no encontrado en {MODEL_PATH}")

        with open(MODEL_PATH, "rb") as f:
            artifact = pickle.load(f)

        clf = artifact["model"]
        feature_cols = artifact["feature_cols"]

        # Predicción de prueba con valores medios
        X_dummy = np.array([[1.3, 1.3, 1.3, 1.3, 0.33, 0.33, 1.0, 1.0,
                              0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0]])
        pred = clf.predict(X_dummy)
        proba = clf.predict_proba(X_dummy)

        print(f"Modelo verificado — prediccion dummy: {pred[0]}")
        print(f"  CV accuracy: {artifact['cv_accuracy_mean']:.3f}")
        print(f"  Entrenado con: {artifact['train_size']} partidos")

    check_data = PythonOperator(
        task_id="check_gold_data",
        python_callable=_build_features,
    )

    train_model = PythonOperator(
        task_id="train_random_forest",
        python_callable=_train,
    )

    verify_model = PythonOperator(
        task_id="verify_model_artifact",
        python_callable=_verify,
    )

    check_data >> train_model >> verify_model
