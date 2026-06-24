"""Cliente para API-Football (RapidAPI) — datos en vivo del WC2026.

Extrae por cada día de partido:
  - Fixtures (resultados, fases, árbitros)
  - Statistics por equipo (posesión, tiros, xG, corners, tarjetas)
  - Players stats por partido (goles, asistencias, rating, minutos)

Límite free tier: 100 req/día.
Uso estimado: ~3 fixtures/día × 3 endpoints = ~9-12 req/día.

Ejecutar diariamente desde Airflow (dag_ingest_wc2026) o manualmente:
  python -m ingestion.api_football_client --date 2026-06-15
"""

import argparse
import os
import time
from datetime import date, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

from ingestion.minio_client import write_parquet

# ── Constantes ────────────────────────────────────────────────────────────────
# FIFA World Cup 2026 en API-Football.
# Verificar en https://dashboard.api-football.com si el ID cambia.
WC2026_LEAGUE_ID = 1
WC2026_SEASON = 2026

# Pausa entre requests para no saturar el rate limiter
REQUEST_DELAY_SECONDS = 1.5

_requests_made = 0


def _get_headers() -> dict:
    return {
        "x-apisports-key": os.environ["API_FOOTBALL_KEY"],
        "x-rapidapi-host": "v3.football.api-sports.io",
    }


def _get(endpoint: str, params: dict) -> dict:
    """Realiza un GET a la API y retorna el JSON. Lleva cuenta de requests usados."""
    global _requests_made
    base_url = os.environ.get("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")
    url = f"{base_url}/{endpoint}"

    response = requests.get(url, headers=_get_headers(), params=params, timeout=30)
    response.raise_for_status()

    _requests_made += 1
    data = response.json()

    remaining = data.get("paging", {}).get("remaining", "?")
    print(f"  [{_requests_made} req] GET /{endpoint} — {len(data.get('response', []))} items  "
          f"(remaining today: {remaining})")

    time.sleep(REQUEST_DELAY_SECONDS)
    return data


def fetch_fixtures(target_date: str) -> pd.DataFrame:
    """Obtiene todos los partidos del WC2026 jugados en una fecha dada.

    Args:
        target_date: Fecha en formato YYYY-MM-DD.

    Returns:
        DataFrame con metadata de fixtures: equipos, resultado, fase, venue.
    """
    data = _get("fixtures", {
        "league": WC2026_LEAGUE_ID,
        "season": WC2026_SEASON,
        "date": target_date,
    })

    if not data.get("response"):
        print(f"  ℹ Sin partidos para {target_date}")
        return pd.DataFrame()

    rows = []
    for item in data["response"]:
        fixture = item["fixture"]
        league = item["league"]
        teams = item["teams"]
        goals = item["goals"]
        score = item["score"]

        rows.append({
            "fixture_id": fixture["id"],
            "date": fixture["date"],
            "status": fixture["status"]["long"],
            "elapsed": fixture["status"]["elapsed"],
            "venue_name": fixture.get("venue", {}).get("name"),
            "venue_city": fixture.get("venue", {}).get("city"),
            "referee": fixture.get("referee"),
            "league_round": league["round"],
            "home_team_id": teams["home"]["id"],
            "home_team_name": teams["home"]["name"],
            "home_winner": teams["home"]["winner"],
            "away_team_id": teams["away"]["id"],
            "away_team_name": teams["away"]["name"],
            "away_winner": teams["away"]["winner"],
            "goals_home": goals["home"],
            "goals_away": goals["away"],
            "score_ht_home": score["halftime"]["home"],
            "score_ht_away": score["halftime"]["away"],
        })

    return pd.DataFrame(rows)


def fetch_fixture_stats(fixture_id: int) -> pd.DataFrame:
    """Stats por equipo de un partido: posesión, tiros, xG, corners, tarjetas."""
    data = _get("fixtures/statistics", {"fixture": fixture_id})

    if not data.get("response"):
        return pd.DataFrame()

    rows = []
    for team_data in data["response"]:
        row = {
            "fixture_id": fixture_id,
            "team_id": team_data["team"]["id"],
            "team_name": team_data["team"]["name"],
        }
        for stat in team_data.get("statistics", []):
            key = stat["type"].lower().replace(" ", "_").replace("%", "pct")
            row[key] = stat["value"]
        rows.append(row)

    return pd.DataFrame(rows)


def fetch_fixture_players(fixture_id: int) -> pd.DataFrame:
    """Stats por jugador de un partido: minutos, goles, asistencias, rating."""
    data = _get("fixtures/players", {"fixture": fixture_id})

    if not data.get("response"):
        return pd.DataFrame()

    rows = []
    for team_data in data["response"]:
        team_id = team_data["team"]["id"]
        team_name = team_data["team"]["name"]
        for player_entry in team_data.get("players", []):
            p = player_entry["player"]
            stats = player_entry["statistics"][0] if player_entry.get("statistics") else {}

            rows.append({
                "fixture_id": fixture_id,
                "team_id": team_id,
                "team_name": team_name,
                "player_id": p["id"],
                "player_name": p["name"],
                "photo": p.get("photo"),
                "minutes_played": stats.get("games", {}).get("minutes"),
                "rating": stats.get("games", {}).get("rating"),
                "goals": stats.get("goals", {}).get("total"),
                "assists": stats.get("goals", {}).get("assists"),
                "shots_total": stats.get("shots", {}).get("total"),
                "shots_on_target": stats.get("shots", {}).get("on"),
                "passes_total": stats.get("passes", {}).get("total"),
                "passes_key": stats.get("passes", {}).get("key"),
                "passes_accuracy": stats.get("passes", {}).get("accuracy"),
                "tackles": stats.get("tackles", {}).get("total"),
                "interceptions": stats.get("tackles", {}).get("interceptions"),
                "duels_won": stats.get("duels", {}).get("won"),
                "dribbles_success": stats.get("dribbles", {}).get("success"),
                "yellow_cards": stats.get("cards", {}).get("yellow"),
                "red_cards": stats.get("cards", {}).get("red"),
            })

    return pd.DataFrame(rows)


def run_daily_ingestion(target_date: str) -> None:
    """Orquesta la ingesta completa de un día: fixtures → stats → players → MinIO.

    Diseñado para ser llamado desde el DAG de Airflow o manualmente.
    """
    print(f"\n{'='*55}")
    print(f"  Ingesta WC2026 — {target_date}")

    # 1. Fixtures del día
    fixtures = fetch_fixtures(target_date)
    if fixtures.empty:
        print("  Sin partidos hoy. Nada que ingestar.")
        return

    date_partition = f"date={target_date}"
    write_parquet(fixtures, f"raw_fixtures_2026/{date_partition}/fixtures.parquet")

    # 2. Stats + Players por cada fixture
    fixture_ids = fixtures["fixture_id"].tolist()
    print(f"\n  Procesando {len(fixture_ids)} partidos...")

    all_stats = []
    all_players = []

    for fixture_id in fixture_ids:
        stats_df = fetch_fixture_stats(fixture_id)
        if not stats_df.empty:
            all_stats.append(stats_df)

        players_df = fetch_fixture_players(fixture_id)
        if not players_df.empty:
            all_players.append(players_df)

    if all_stats:
        write_parquet(
            pd.concat(all_stats, ignore_index=True),
            f"raw_stats_2026/{date_partition}/team_stats.parquet",
        )

    if all_players:
        write_parquet(
            pd.concat(all_players, ignore_index=True),
            f"raw_player_stats_2026/{date_partition}/player_stats.parquet",
        )

    print(f"\n  ✓ Ingesta {target_date} completa — {_requests_made} requests usados hoy")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta diaria WC2026 desde API-Football")
    parser.add_argument(
        "--date",
        default=str(date.today() - timedelta(days=1)),
        help="Fecha a ingestar (YYYY-MM-DD). Default: ayer.",
    )
    args = parser.parse_args()

    load_dotenv()
    run_daily_ingestion(args.date)
