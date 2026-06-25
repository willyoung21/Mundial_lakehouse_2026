"""Carga del dataset histórico de Mundiales (Kaggle) hacia Bronze (MinIO).

Dataset: Mart Jürisoo — International Football Results
  https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017

Archivos que carga desde data/archive/:
  results.csv     → raw_wc_history/world_cups.parquet         (resultados WC 1930-2022)
  goalscorers.csv → raw_wc_goalscorers/goalscorers.parquet    (goleadores, sin filtro de torneo)
  shootouts.csv   → raw_wc_shootouts/shootouts.parquet        (penales, sin filtro de torneo)

El filtrado a partidos de Mundiales se hace en Silver (dbt) via JOIN con stg_wc_history.

Carga única — ejecutar una sola vez:
  python -m ingestion.kaggle_loader --archive-dir data/archive
"""

import argparse
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from ingestion.minio_client import write_parquet


def load_wc_history(archive_dir: str) -> None:
    """Lee results.csv, filtra Mundiales FIFA y escribe a MinIO Bronze."""
    path = Path(archive_dir) / "results.csv"
    print(f"\nCargando resultados históricos: {path}")
    df = pd.read_csv(path)
    print(f"  Total filas en CSV: {len(df):,}")

    df = df[df["tournament"] == "FIFA World Cup"].copy()
    print(f"  Filas de Mundiales FIFA: {len(df):,}")

    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    write_parquet(df, "raw_wc_history/world_cups.parquet")


def load_wc_goalscorers(archive_dir: str) -> None:
    """Lee goalscorers.csv y escribe todo a MinIO Bronze (sin filtro — Silver filtra).

    Columnas: date, home_team, away_team, team, scorer, minute, own_goal, penalty
    """
    path = Path(archive_dir) / "goalscorers.csv"
    print(f"\nCargando goleadores históricos: {path}")
    df = pd.read_csv(path)
    print(f"  Total filas: {len(df):,}")

    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["own_goal"] = df["own_goal"].astype(bool)
    df["penalty"] = df["penalty"].astype(bool)

    write_parquet(df, "raw_wc_goalscorers/goalscorers.parquet")


def load_wc_shootouts(archive_dir: str) -> None:
    """Lee shootouts.csv y escribe todo a MinIO Bronze (sin filtro — Silver filtra).

    Columnas: date, home_team, away_team, winner, first_shooter
    """
    path = Path(archive_dir) / "shootouts.csv"
    print(f"\nCargando penales históricos: {path}")
    df = pd.read_csv(path)
    print(f"  Total filas: {len(df):,}")

    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    write_parquet(df, "raw_wc_shootouts/shootouts.parquet")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Carga CSVs históricos de Mundiales (Kaggle) a Bronze"
    )
    parser.add_argument(
        "--archive-dir",
        default="data/archive",
        help="Carpeta con los CSVs descargados de Kaggle. Default: data/archive",
    )
    args = parser.parse_args()

    load_dotenv()
    load_wc_history(args.archive_dir)
    load_wc_goalscorers(args.archive_dir)
    load_wc_shootouts(args.archive_dir)
    print("\n✓ Carga Kaggle completa. Verifica en MinIO: http://localhost:9001")
