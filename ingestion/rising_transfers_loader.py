"""Loader para datos de planteles WC2026 desde Rising Transfers (CC BY 4.0).

Fuente: https://github.com/risingtransfers/world-cup-2026-data
Descarga:
  - squads.csv       -- 1,363 jugadores de los 48 planteles (posicion, club, valor)
  - per90_stats.csv  -- metricas por 90 min de la temporada 2025-26 (>=450 min)

Carga unica (one-shot). Re-ejecutar para refrescar si el repo actualiza los datos.

  python -m ingestion.rising_transfers_loader
"""

import io

import pandas as pd
import requests
from dotenv import load_dotenv

from ingestion.minio_client import write_parquet

_REPO_BASE = "https://raw.githubusercontent.com/risingtransfers/world-cup-2026-data/main"

SQUADS_URLS = [
    f"{_REPO_BASE}/data/squads.csv",
    f"{_REPO_BASE}/squads.csv",
]
PER90_URLS = [
    f"{_REPO_BASE}/data/per90_stats.csv",
    f"{_REPO_BASE}/per90_stats.csv",
]


def _download_csv(urls: list[str]) -> pd.DataFrame:
    """Intenta descargar el CSV desde cada URL hasta que una funcione."""
    for url in urls:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            print(f"  OK Descargado desde {url}")
            return pd.read_csv(io.StringIO(resp.text))
        print(f"  FAIL {url} -> {resp.status_code}")
    raise RuntimeError(f"No se pudo descargar el CSV. URLs intentadas: {urls}")


def load_squads() -> None:
    print("\n[1/2] wc2026_squads -- planteles de los 48 equipos")
    df = _download_csv(SQUADS_URLS)
    print(f"  -> {len(df):,} jugadores, columnas: {list(df.columns)}")
    write_parquet(df, "raw_wc2026_squads/squads.parquet")
    print("  OK raw_wc2026_squads/squads.parquet")


def load_per90() -> None:
    print("\n[2/2] wc2026_per90 -- estadisticas por 90 min (temporada 2025-26)")
    df = _download_csv(PER90_URLS)
    print(f"  -> {len(df):,} jugadores, columnas: {list(df.columns)}")
    write_parquet(df, "raw_wc2026_per90/per90_stats.parquet")
    print("  OK raw_wc2026_per90/per90_stats.parquet")


def run() -> None:
    print(f"\n{'=' * 55}")
    print("  Rising Transfers WC2026 -> Bronze (MinIO)")
    print(f"{'=' * 55}")
    load_squads()
    load_per90()
    print("\nOK Carga completa. Credito: Rising Transfers (CC BY 4.0) risingtransfers.com")


if __name__ == "__main__":
    load_dotenv()
    run()
