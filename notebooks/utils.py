"""Helpers compartidos para todos los notebooks de análisis WC2026.

Uso en cualquier notebook:
    from utils import query, null_report, get_engine
"""

import os

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv


def get_engine() -> sa.Engine:
    load_dotenv()
    user = os.environ["POSTGRES_USER"]
    pwd  = os.environ["POSTGRES_PASSWORD"]
    host = os.environ["POSTGRES_HOST"]
    db   = os.environ["POSTGRES_DB"]
    return sa.create_engine(
        f"postgresql+psycopg2://{user}:{pwd}@{host}/{db}?sslmode=require",
        pool_pre_ping=True,
    )


_engine: sa.Engine | None = None


def query(sql: str, engine: sa.Engine | None = None) -> pd.DataFrame:
    """Ejecuta SQL contra Neon y retorna DataFrame. Reutiliza la conexión."""
    global _engine
    if engine is None:
        if _engine is None:
            _engine = get_engine()
        engine = _engine
    with engine.connect() as conn:
        return pd.read_sql(sa.text(sql), conn)


def null_report(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla de nulos por columna: count, porcentaje y dtype, ordenado desc."""
    nulls = df.isnull().sum()
    pct   = (nulls / len(df) * 100).round(1)
    report = pd.DataFrame({
        "nulos":  nulls,
        "pct":    pct,
        "dtype":  df.dtypes,
    }).sort_values("pct", ascending=False)
    return report[report["nulos"] > 0]  # solo columnas con al menos 1 nulo
