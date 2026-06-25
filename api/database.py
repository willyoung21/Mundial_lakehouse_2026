import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = (
            f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
            f"@{os.environ['POSTGRES_HOST']}/{os.environ['POSTGRES_DB']}?sslmode=require"
        )
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return _engine


def get_db():
    engine = get_engine()
    with engine.connect() as conn:
        yield conn
