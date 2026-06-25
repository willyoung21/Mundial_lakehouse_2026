"""Utilidades para leer y escribir Parquet en MinIO (Bronze layer)."""

import io
import os

import pandas as pd
from minio import Minio
from minio.error import S3Error


def get_client() -> Minio:
    return Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,  # MinIO local sin TLS
    )


def write_parquet(df: pd.DataFrame, path: str, bucket: str | None = None) -> None:
    """Escribe un DataFrame como Parquet en MinIO.

    Args:
        df: DataFrame a persistir.
        path: Ruta del objeto dentro del bucket (ej. "raw_fixtures_2026/date=2026-06-15/fixtures.parquet").
        bucket: Nombre del bucket. Si es None usa MINIO_BUCKET del entorno.
    """
    bucket = bucket or os.environ["MINIO_BUCKET"]
    client = get_client()

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)
    size = buffer.getbuffer().nbytes

    client.put_object(
        bucket_name=bucket,
        object_name=path,
        data=buffer,
        length=size,
        content_type="application/octet-stream",
    )
    print(f"  OK {path}  ({size / 1024:.1f} KB, {len(df):,} filas)")


def read_parquet(path: str, bucket: str | None = None) -> pd.DataFrame:
    """Lee un Parquet de MinIO y lo retorna como DataFrame."""
    bucket = bucket or os.environ["MINIO_BUCKET"]
    client = get_client()
    response = client.get_object(bucket, path)
    return pd.read_parquet(io.BytesIO(response.read()))


def list_objects(prefix: str, bucket: str | None = None) -> list[str]:
    """Lista las rutas de todos los objetos bajo un prefijo dado."""
    bucket = bucket or os.environ["MINIO_BUCKET"]
    client = get_client()
    return [obj.object_name for obj in client.list_objects(bucket, prefix=prefix, recursive=True)]


def object_exists(path: str, bucket: str | None = None) -> bool:
    """Devuelve True si el objeto ya existe en MinIO."""
    bucket = bucket or os.environ["MINIO_BUCKET"]
    client = get_client()
    try:
        client.stat_object(bucket, path)
        return True
    except S3Error:
        return False
