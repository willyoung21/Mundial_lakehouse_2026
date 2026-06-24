"""Bridge: lee Parquets de MinIO (Bronze) y los carga a Neon en esquema bronze_raw.

Ejecutar antes de `dbt run` para que los modelos Silver tengan datos frescos.

  # Carga completa (todas las tablas)
  python -m ingestion.bronze_to_neon

  # Solo una tabla específica
  python -m ingestion.bronze_to_neon --table statsbomb_events

Tablas que crea en bronze_raw:
  - statsbomb_matches   (una fila por partido por competición)
  - statsbomb_events    (eventos aplanados, con columnas _json para campos anidados)
  - statsbomb_lineups   (alineaciones por equipo)
  - api_fixtures        (partidos WC2026 en vivo)
  - api_team_stats      (stats por equipo por partido)
  - api_player_stats    (stats por jugador por partido)
  - wc_history          (resultados históricos Kaggle 1930-2022)
"""

import argparse
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from ingestion.minio_client import list_objects, object_exists, read_parquet

SCHEMA = "bronze_raw"

# Columnas de eventos StatsBomb que contienen dicts/listas (serializadas como JSON string).
# Se renombran con sufijo _json para claridad en SQL y evitar palabras reservadas.
_EVENT_JSON_COLS = {
    "type": "event_type_json",
    "player": "player_json",
    "team": "team_json",
    "position": "position_json",
    "location": "location_json",
    "possession_team": "possession_team_json",
    "play_pattern": "play_pattern_json",
    "shot": "shot_json",
    "pass": "pass_json",
    "carry": "carry_json",
    "dribble": "dribble_json",
    "interception": "interception_json",
    "block": "block_json",
    "duel": "duel_json",
    "goalkeeper": "goalkeeper_json",
    "clearance": "clearance_json",
    "ball_recovery": "ball_recovery_json",
    "pressure": "pressure_json",
    "tactics": "tactics_json",
    "substitution": "substitution_json",
    "foul_committed": "foul_committed_json",
    "foul_won": "foul_won_json",
    "related_events": "related_events_json",
    "50_50": "fifty_fifty_json",
    "miscontrol": "miscontrol_json",
    "bad_behaviour": "bad_behaviour_json",
    "half_start": "half_start_json",
    "half_end": "half_end_json",
    "starting_xi": "starting_xi_json",
    "player_off": "player_off_json",
    "player_on": "player_on_json",
    "error": "error_json",
}


def _get_engine():
    url = (
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}/{os.environ['POSTGRES_DB']}?sslmode=require"
    )
    return create_engine(url, pool_pre_ping=True)


def _ensure_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))


def _write(df: pd.DataFrame, table: str, engine, first: bool = True) -> None:
    df = df.loc[:, ~df.columns.duplicated()]
    if any(len(c) > 63 for c in df.columns):
        df.columns = [c[:63] for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]

    n_cols = len(df.columns)

    if first:
        # DROP CASCADE para eliminar vistas dependientes (Silver/Gold).
        # dbt las recrea en el siguiente `dbt run`. pandas.to_sql(if_exists="replace")
        # usa DROP simple y falla cuando hay views dependientes.
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {SCHEMA}.{table} CASCADE"))

    # Sin method="multi": usa executemany (una fila por vez) → sin límite de parámetros
    df.to_sql(
        table,
        engine,
        schema=SCHEMA,
        if_exists="replace" if first else "append",
        index=False,
        chunksize=500,
    )
    print(f"  -> {SCHEMA}.{table}  ({len(df):,} filas, {n_cols} cols)")


def _detect_statsbomb_slugs() -> list[str]:
    """Detecta qué competiciones StatsBomb están disponibles en MinIO."""
    slugs = []
    # Busca objetos que sigan el patrón raw_statsbomb_{slug}/matches.parquet
    all_objects = list_objects("raw_statsbomb_")
    seen = set()
    for path in all_objects:
        # path = "raw_statsbomb_wc2022/matches.parquet" o "raw_statsbomb_wc2022/events/..."
        parts = path.split("/")
        prefix = parts[0]  # e.g. "raw_statsbomb_wc2022"
        slug = prefix.replace("raw_statsbomb_", "")
        if slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


# ── Loaders individuales ───────────────────────────────────────────────────────

def load_statsbomb_matches(engine) -> None:
    print("\n[1/7] statsbomb_matches")
    slugs = _detect_statsbomb_slugs()
    if not slugs:
        print("  ℹ No hay datos StatsBomb en MinIO — corre statsbomb_loader primero.")
        return

    frames = []
    for slug in slugs:
        path = f"raw_statsbomb_{slug}/matches.parquet"
        if object_exists(path):
            df = read_parquet(path)
            df["competition_slug"] = slug
            frames.append(df)
            print(f"  ↑ {slug}: {len(df)} partidos")

    if frames:
        _write(pd.concat(frames, ignore_index=True), "statsbomb_matches", engine)


def load_statsbomb_events(engine) -> None:
    print("\n[2/7] statsbomb_events (cargando todos en memoria para alinear columnas)")
    slugs = _detect_statsbomb_slugs()
    if not slugs:
        print("  ℹ No hay datos StatsBomb en MinIO.")
        return

    all_frames: list[pd.DataFrame] = []

    for slug in slugs:
        paths = list_objects(f"raw_statsbomb_{slug}/events/")
        if not paths:
            continue
        for i, path in enumerate(paths, 1):
            df = read_parquet(path)
            df["competition_slug"] = slug
            rename_map = {k: v for k, v in _EVENT_JSON_COLS.items() if k in df.columns}
            df = df.rename(columns=rename_map)
            all_frames.append(df)
            if i % 20 == 0:
                print(f"  ... {slug}: {i}/{len(paths)} archivos leídos")
        print(f"  ✓ {slug}: {len(paths)} archivos")

    if not all_frames:
        print("  ℹ No se encontraron eventos.")
        return

    # pd.concat alinea columnas automáticamente (NaN para cols ausentes en un partido)
    combined = pd.concat(all_frames, ignore_index=True)
    print(f"  → Consolidado: {len(combined):,} eventos, {len(combined.columns)} columnas")
    _write(combined, "statsbomb_events", engine)


def load_statsbomb_lineups(engine) -> None:
    print("\n[3/7] statsbomb_lineups (streaming)")
    slugs = _detect_statsbomb_slugs()
    if not slugs:
        return

    first = True
    for slug in slugs:
        paths = list_objects(f"raw_statsbomb_{slug}/lineups/")
        if not paths:
            continue
        for path in paths:
            df = read_parquet(path)
            df["competition_slug"] = slug
            # cards y positions son listas → JSON strings desde el loader
            _write(df, "statsbomb_lineups", engine, first=first)
            first = False
        print(f"  ✓ {slug}: {len(paths)} alineaciones")


def load_api_fixtures(engine) -> None:
    print("\n[4/7] api_fixtures (WC2026)")
    paths = list_objects("raw_fixtures_2026/")
    fixture_paths = [p for p in paths if p.endswith("fixtures.parquet")]
    if not fixture_paths:
        print("  ℹ No hay fixtures WC2026 en MinIO todavía.")
        return

    frames = [read_parquet(p) for p in fixture_paths]
    _write(pd.concat(frames, ignore_index=True), "api_fixtures", engine)


def load_api_team_stats(engine) -> None:
    print("\n[5/7] api_team_stats")
    paths = list_objects("raw_stats_2026/")
    stat_paths = [p for p in paths if p.endswith("team_stats.parquet")]
    if not stat_paths:
        print("  ℹ No hay team stats WC2026 en MinIO todavía.")
        return

    frames = [read_parquet(p) for p in stat_paths]
    _write(pd.concat(frames, ignore_index=True), "api_team_stats", engine)


def load_api_player_stats(engine) -> None:
    print("\n[6/7] api_player_stats")
    paths = list_objects("raw_player_stats_2026/")
    player_paths = [p for p in paths if p.endswith("player_stats.parquet")]
    if not player_paths:
        print("  ℹ No hay player stats WC2026 en MinIO todavía.")
        return

    frames = [read_parquet(p) for p in player_paths]
    _write(pd.concat(frames, ignore_index=True), "api_player_stats", engine)


def load_wc_history(engine) -> None:
    print("\n[7/9] wc_history")
    path = "raw_wc_history/world_cups.parquet"
    if not object_exists(path):
        print("  ℹ No hay histórico Kaggle en MinIO — corre kaggle_loader primero.")
        return
    _write(read_parquet(path), "wc_history", engine)


def load_wc_goalscorers(engine) -> None:
    print("\n[8/9] wc_goalscorers")
    path = "raw_wc_goalscorers/goalscorers.parquet"
    if not object_exists(path):
        print("  ℹ No hay goleadores Kaggle en MinIO — corre kaggle_loader primero.")
        return
    _write(read_parquet(path), "wc_goalscorers", engine)


def load_wc_shootouts(engine) -> None:
    print("\n[9/9] wc_shootouts")
    path = "raw_wc_shootouts/shootouts.parquet"
    if not object_exists(path):
        print("  ℹ No hay shootouts Kaggle en MinIO — corre kaggle_loader primero.")
        return
    _write(read_parquet(path), "wc_shootouts", engine)


def load_wc2026_squads(engine) -> None:
    print("\n[extra] wc2026_squads — planteles WC2026 (Rising Transfers)")
    path = "raw_wc2026_squads/squads.parquet"
    if not object_exists(path):
        print("  ℹ No hay datos en MinIO — corre: python -m ingestion.rising_transfers_loader")
        return
    _write(read_parquet(path), "wc2026_squads", engine)


def load_wc2026_per90(engine) -> None:
    print("\n[extra] wc2026_per90 — stats por 90 min temporada 2025-26 (Rising Transfers)")
    path = "raw_wc2026_per90/per90_stats.parquet"
    if not object_exists(path):
        print("  ℹ No hay datos en MinIO — corre: python -m ingestion.rising_transfers_loader")
        return
    _write(read_parquet(path), "wc2026_per90", engine)


def load_onside_predictions(engine) -> None:
    print("\n[extra] onside_predictions — predicciones Monte Carlo WC2026 (Onside Arena)")
    path = "raw_onside_predictions/predictions.parquet"
    if not object_exists(path):
        print("  ℹ No hay datos en MinIO — corre: python -m ingestion.onside_loader")
        return
    _write(read_parquet(path), "onside_predictions", engine)


def load_onside_champions(engine) -> None:
    print("\n[extra] onside_champions — probabilidades de campeón por equipo (Onside Arena)")
    path = "raw_onside_predictions/champions.parquet"
    if not object_exists(path):
        print("  ℹ No hay datos en MinIO — corre: python -m ingestion.onside_loader")
        return
    _write(read_parquet(path), "onside_champions", engine)


# ── Orquestador ───────────────────────────────────────────────────────────────

LOADERS = {
    "statsbomb_matches": load_statsbomb_matches,
    "statsbomb_events": load_statsbomb_events,
    "statsbomb_lineups": load_statsbomb_lineups,
    "api_fixtures": load_api_fixtures,
    "api_team_stats": load_api_team_stats,
    "api_player_stats": load_api_player_stats,
    "wc_history": load_wc_history,
    "wc_goalscorers": load_wc_goalscorers,
    "wc_shootouts": load_wc_shootouts,
    "wc2026_squads": load_wc2026_squads,
    "wc2026_per90": load_wc2026_per90,
    "onside_predictions": load_onside_predictions,
    "onside_champions": load_onside_champions,
}


def run(table: str | None = None) -> None:
    load_dotenv()
    engine = _get_engine()
    _ensure_schema(engine)

    print(f"\n{'='*55}")
    print(f"  Bronze → Neon ({SCHEMA})")
    print(f"{'='*55}")

    if table:
        if table not in LOADERS:
            raise ValueError(f"Tabla desconocida: {table}. Opciones: {list(LOADERS)}")
        LOADERS[table](engine)
    else:
        for loader in LOADERS.values():
            loader(engine)

    print(f"\n✓ Carga a {SCHEMA} completa. Ahora corre: cd dbt && dbt run")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga Bronze (MinIO) → Neon (bronze_raw)")
    parser.add_argument(
        "--table",
        choices=list(LOADERS.keys()),
        help="Cargar solo una tabla específica. Sin este flag carga todo.",
    )
    args = parser.parse_args()
    run(args.table)
