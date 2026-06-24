import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.database import get_db

router = APIRouter(prefix="/predict", tags=["predict"])

LAMBDA_GLOBAL = 1.30   # WC historical mean goals/team/match
N_SIMULATIONS = 10_000


class MatchupRequest(BaseModel):
    home: str
    away: str
    n: int = N_SIMULATIONS

    model_config = {"json_schema_extra": {"example": {"home": "Spain", "away": "Brazil"}}}


def _build_team_ratings(conn: Connection) -> dict:
    """Build attack/defense ratings per team from mart_performance.

    Prefers StatsBomb xG data (richer signal) over WC2026-only goals.
    Returns dict keyed by lowercase team name OR lowercase FIFA code.
    """
    # Step 1: best stats per team (prefer StatsBomb competitions)
    sql_stats = text("""
        WITH ranked AS (
            SELECT
                LOWER(team_canonical)                   AS team,
                avg_xg_per_match,
                CASE WHEN matches_played > 0
                    THEN goals_conceded::float / matches_played
                END                                     AS defense,
                ROW_NUMBER() OVER (
                    PARTITION BY LOWER(team_canonical)
                    ORDER BY
                        CASE WHEN competition_slug IN (
                            'wc2022','copa_america_2024','euro_2020','euro_2024')
                            THEN 0 ELSE 1 END,
                        matches_played DESC
                ) AS rn
            FROM gold.mart_performance
            WHERE matches_played > 0
        )
        SELECT team, avg_xg_per_match, defense
        FROM ranked
        WHERE rn = 1
    """)

    # Step 2: code→team mapping from any row that has a valid FIFA code
    sql_codes = text("""
        SELECT DISTINCT LOWER(team_canonical) AS team, LOWER(fifa_code) AS code
        FROM gold.mart_performance
        WHERE fifa_code IS NOT NULL AND fifa_code <> ''
    """)

    ratings: dict = {}
    for r in conn.execute(sql_stats).mappings().all():
        attack = float(r["avg_xg_per_match"]) if r["avg_xg_per_match"] else LAMBDA_GLOBAL
        defense = float(r["defense"]) if r["defense"] else LAMBDA_GLOBAL
        ratings[r["team"]] = {"attack": attack, "defense": defense}

    # Index by FIFA code as well (separate pass avoids missing codes from stats rows)
    for r in conn.execute(sql_codes).mappings().all():
        team_key = r["team"]
        code_key = r["code"]
        if team_key in ratings and code_key:
            ratings[code_key] = ratings[team_key]

    return ratings


def _resolve_team(name: str, ratings: dict) -> tuple[str, dict]:
    """Case-insensitive lookup by name or FIFA code."""
    key = name.strip().lower()
    if key in ratings:
        return name, ratings[key]
    raise KeyError(key)


def _simulate(lambda_home: float, lambda_away: float, n: int) -> dict:
    rng = np.random.default_rng()
    goals_h = rng.poisson(lambda_home, n)
    goals_a = rng.poisson(lambda_away, n)

    home_wins = int((goals_h > goals_a).sum())
    draws     = int((goals_h == goals_a).sum())
    away_wins = int((goals_h < goals_a).sum())

    avg_h = float(np.mean(goals_h))
    avg_a = float(np.mean(goals_a))

    return {
        "home_win_pct": round(home_wins / n * 100, 1),
        "draw_pct":     round(draws     / n * 100, 1),
        "away_win_pct": round(away_wins / n * 100, 1),
        "avg_goals_home": round(avg_h, 2),
        "avg_goals_away": round(avg_a, 2),
        "simulations": n,
    }


@router.post("/winner")
def predict_winner(req: MatchupRequest, conn: Connection = Depends(get_db)):
    """Monte Carlo Poisson simulation for a hypothetical or upcoming match.

    Uses xG attack/defense ratings from mart_performance (StatsBomb preferred).
    Teams without StatsBomb data fall back to WC2026 stats or the global mean (1.30).

    λ_home = attack_home × (LAMBDA_GLOBAL / defense_away)
    λ_away = attack_away × (LAMBDA_GLOBAL / defense_home)
    """
    ratings = _build_team_ratings(conn)

    try:
        home_name, home_r = _resolve_team(req.home, ratings)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Team '{req.home}' not found. Try the canonical name or FIFA code (e.g. 'Spain' or 'ESP').",
        )

    try:
        away_name, away_r = _resolve_team(req.away, ratings)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Team '{req.away}' not found. Try the canonical name or FIFA code (e.g. 'Brazil' or 'BRA').",
        )

    # λ = attack_own × (defense_opponent / global_mean)
    # Good defense (low GA/match) reduces expected goals; poor defense inflates them.
    lambda_home = home_r["attack"] * (away_r["defense"] / LAMBDA_GLOBAL)
    lambda_away = away_r["attack"] * (home_r["defense"] / LAMBDA_GLOBAL)

    result = _simulate(lambda_home, lambda_away, req.n)

    return {
        "home": req.home,
        "away": req.away,
        "lambda_home": round(lambda_home, 3),
        "lambda_away": round(lambda_away, 3),
        "home_attack_xg": round(home_r["attack"], 3),
        "away_attack_xg": round(away_r["attack"], 3),
        "home_defense_ga_per_match": round(home_r["defense"], 3),
        "away_defense_ga_per_match": round(away_r["defense"], 3),
        **result,
        "note": "Poisson model based on xG/goals from StatsBomb + WC2026 data. "
                "Teams missing xG data use global mean (lambda=1.30).",
    }
