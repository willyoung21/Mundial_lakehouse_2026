"""Conexión a Neon (Gold/Silver) para el dashboard Streamlit.

Adaptado de notebooks/utils.py con caché de Streamlit para evitar
reconexiones en cada rerun.
"""

import os

import pandas as pd
import sqlalchemy as sa
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


@st.cache_resource
def get_engine() -> sa.Engine:
    user = os.environ["POSTGRES_USER"]
    pwd  = os.environ["POSTGRES_PASSWORD"]
    host = os.environ["POSTGRES_HOST"]
    db   = os.environ["POSTGRES_DB"]
    return sa.create_engine(
        f"postgresql+psycopg2://{user}:{pwd}@{host}/{db}?sslmode=require",
        pool_pre_ping=True,
        pool_size=3,
    )


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    """Ejecuta SQL contra Neon y retorna DataFrame. Cache de 5 minutos."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(sa.text(sql), conn)
