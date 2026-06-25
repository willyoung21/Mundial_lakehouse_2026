"""Carga de datos históricos desde StatsBomb Open Data hacia Bronze (MinIO).

Competiciones objetivo:
  - FIFA World Cup 2022 (Qatar)
  - Copa América 2021
  - UEFA Euro 2020
  - UEFA Nations League (si está disponible en open data)

Ejecutar una sola vez al iniciar el proyecto:
  python -m ingestion.statsbomb_loader
"""

import json

import pandas as pd
from dotenv import load_dotenv
from statsbombpy import sb

from ingestion.minio_client import object_exists, write_parquet

# IDs verificados con sb.competitions() — ajustar si cambian en futuras versiones
COMPETITIONS = {
    "wc2022": {"competition_id": 43, "season_id": 106},
    "copa_america_2024": {"competition_id": 223, "season_id": 282},
    "euro_2020": {"competition_id": 55, "season_id": 43},
    "euro_2024": {"competition_id": 55, "season_id": 282},
}

# Tipos de evento relevantes para análisis táctico y modelo ML
RELEVANT_EVENT_TYPES = {
    "Shot",
    "Pass",
    "Pressure",
    "Carry",
    "Dribble",
    "Interception",
    "Block",
    "Duel",
    "Ball Recovery",
    "Clearance",
    "Goal Keeper",
}


def list_available_competitions() -> pd.DataFrame:
    """Imprime y retorna todas las competiciones disponibles en StatsBomb open data."""
    comps = sb.competitions()
    print("\n── Competiciones disponibles en StatsBomb Open Data ──")
    print(
        comps[["competition_id", "season_id", "competition_name", "season_name"]]
        .sort_values(["competition_name", "season_name"])
        .to_string(index=False)
    )
    return comps


def _serialize_lists(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte columnas con listas o dicts a JSON string para compatibilidad Parquet.

    StatsBomb usa listas para coordenadas [x, y] y dicts anidados en algunos campos.
    En Bronze guardamos el raw; Silver/dbt se encarga de parsear.
    """
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
            if isinstance(sample, (list, dict)):
                df[col] = df[col].apply(
                    lambda v: json.dumps(v) if isinstance(v, (list, dict)) else v
                )
    return df


def load_competition(slug: str, competition_id: int, season_id: int) -> None:
    """Carga matches + events + lineups de una competición en Bronze (MinIO).

    Usa skip-if-exists para que sea seguro re-ejecutar sin duplicar carga.
    """
    prefix = f"raw_statsbomb_{slug}"
    matches_path = f"{prefix}/matches.parquet"

    print(f"\n{'=' * 55}")
    print(f"  Competición: {slug}  (id={competition_id}, season={season_id})")

    # ── Matches ───────────────────────────────────────────────────────────────
    if not object_exists(matches_path):
        matches = sb.matches(competition_id=competition_id, season_id=season_id)
        matches = _serialize_lists(matches)
        write_parquet(matches, matches_path)
    else:
        print(f"  ↷ {matches_path} ya existe, cargando IDs...")
        from ingestion.minio_client import read_parquet

        matches = read_parquet(matches_path)

    match_ids = matches["match_id"].tolist()
    print(f"  {len(match_ids)} partidos a procesar")

    # ── Events + Lineups por partido ──────────────────────────────────────────
    for i, match_id in enumerate(match_ids, 1):
        events_path = f"{prefix}/events/match_{match_id}.parquet"
        lineups_path = f"{prefix}/lineups/match_{match_id}.parquet"

        # Events
        if not object_exists(events_path):
            events = sb.events(match_id=match_id)
            events = events[events["type"].isin(RELEVANT_EVENT_TYPES)].copy()
            events = _serialize_lists(events)
            write_parquet(events, events_path)
        else:
            print(f"  ↷ [{i}/{len(match_ids)}] events match {match_id} ya existe")

        # Lineups
        if not object_exists(lineups_path):
            raw_lineups = sb.lineups(match_id=match_id)
            # sb.lineups retorna dict {team_name: DataFrame}
            lineup_df = pd.concat(
                [df.assign(team_name=team) for team, df in raw_lineups.items()],
                ignore_index=True,
            )
            lineup_df = _serialize_lists(lineup_df)
            write_parquet(lineup_df, lineups_path)
        else:
            print(f"  ↷ [{i}/{len(match_ids)}] lineups match {match_id} ya existe")

    print(f"  ✓ {slug} completo")


def load_all() -> None:
    """Carga todas las competiciones configuradas.

    Primero imprime las competiciones disponibles para que puedas verificar
    los IDs de season si StatsBomb actualiza su open data.
    """
    comps = list_available_competitions()

    # Verificar Nations League
    nl = comps[comps["competition_name"].str.contains("Nations League", na=False)]
    if not nl.empty:
        print("\n  ℹ Nations League disponible — agregando a la carga:")
        print(nl[["competition_id", "season_id", "season_name"]].to_string(index=False))
        for _, row in nl.iterrows():
            slug = (
                f"nations_league_{row['season_name'].replace('/', '_').replace(' ', '_').lower()}"
            )
            COMPETITIONS[slug] = {
                "competition_id": int(row["competition_id"]),
                "season_id": int(row["season_id"]),
            }

    for slug, params in COMPETITIONS.items():
        load_competition(slug, **params)

    print("\n✓ Carga StatsBomb completa. Verifica los archivos en MinIO: http://localhost:9001")


if __name__ == "__main__":
    load_dotenv()
    load_all()
