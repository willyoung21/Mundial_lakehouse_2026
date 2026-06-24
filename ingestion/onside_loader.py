"""Loader para predicciones WC2026 desde Onside Arena (CC BY 4.0).

Fuente: https://onsidearena.com/data
Descarga:
  - predictions.csv -- probabilidades win/draw/loss + resultado real (72 partidos jugados)
  - champions.csv   -- probabilidades de campeon por equipo (actualiza cada hora)

Ejecutar periodicamente para mantener las predicciones actualizadas durante el torneo.

  python -m ingestion.onside_loader

Si la descarga falla (cambio de URL), descargar manualmente el CSV del mirror de Kaggle:
  https://www.kaggle.com/datasets/wr0027/world-cup-2026-predictions-onside-model-outputs
y copiar a data/onside/ antes de ejecutar con --local data/onside/
"""

import argparse
import io
import os

import pandas as pd
import requests
from dotenv import load_dotenv

from ingestion.minio_client import write_parquet

PREDICTIONS_URL = "https://onsidearena.com/data/predictions.csv"
CHAMPIONS_URL   = "https://onsidearena.com/data/champions.csv"


def _download_csv(url: str, label: str) -> pd.DataFrame:
    print(f"  GET {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  -> {len(df):,} filas, columnas: {list(df.columns)}")
    return df


def load_from_local(directory: str) -> None:
    """Fallback: carga los CSVs desde una carpeta local (descarga manual de Kaggle)."""
    pred_path = os.path.join(directory, "predictions.csv")
    champ_path = os.path.join(directory, "champions.csv")

    if os.path.exists(pred_path):
        df = pd.read_csv(pred_path)
        write_parquet(df, "raw_onside_predictions/predictions.parquet")
        print(f"  OK {len(df):,} predicciones desde {pred_path}")

    if os.path.exists(champ_path):
        df = pd.read_csv(champ_path)
        write_parquet(df, "raw_onside_predictions/champions.parquet")
        print(f"  OK {len(df):,} probabilidades de campeon desde {champ_path}")


def load_predictions() -> None:
    print("\n[1/2] onside_predictions -- probabilidades por partido")
    df = _download_csv(PREDICTIONS_URL, "predictions")
    write_parquet(df, "raw_onside_predictions/predictions.parquet")
    print("  OK raw_onside_predictions/predictions.parquet")


def load_champions() -> None:
    print("\n[2/2] onside_champions -- probabilidades de campeon")
    df = _download_csv(CHAMPIONS_URL, "champions")
    write_parquet(df, "raw_onside_predictions/champions.parquet")
    print("  OK raw_onside_predictions/champions.parquet")


def run(local_dir: str | None = None) -> None:
    print(f"\n{'='*55}")
    print("  Onside Arena WC2026 Predictions -> Bronze (MinIO)")
    print(f"{'='*55}")

    if local_dir:
        load_from_local(local_dir)
        return

    try:
        load_predictions()
        load_champions()
    except Exception as e:
        print(f"\n  FAIL Error descargando desde Onside Arena: {e}")
        print("  -> Descarga manual: https://kaggle.com/datasets/wr0027/world-cup-2026-predictions-onside-model-outputs")
        print("  -> Luego: python -m ingestion.onside_loader --local <directorio>")
        raise

    print("\nOK Carga completa. Credito: Onside Arena (CC BY 4.0) onsidearena.com")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga predicciones Onside Arena -> MinIO")
    parser.add_argument(
        "--local",
        metavar="DIRECTORIO",
        help="Carga desde CSVs locales en vez de descargar (fallback para descarga manual de Kaggle).",
    )
    args = parser.parse_args()
    load_dotenv()
    run(local_dir=args.local)
