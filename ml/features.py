"""Feature engineering for the WC2026 match outcome predictor.

Builds a match-level feature matrix from the Gold layer in Neon:
  - Team attack / defense ratings (StatsBomb xG preferred; goals/match as fallback)
  - Win rate, points per match (form)
  - Differential features (home - away)
  - Stage indicator (group stage vs knockout)
  - Onside Arena Monte Carlo probabilities (WC2026 matches only)

Usage:
    from ml.features import build_features
    X, y, meta = build_features(conn)
"""

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

LAMBDA_GLOBAL = 1.30  # WC historical mean goals/team/match
FEATURE_COLS = [
    "home_attack",
    "away_attack",
    "home_defense",
    "away_defense",
    "home_win_rate",
    "away_win_rate",
    "home_pts_per_match",
    "away_pts_per_match",
    "attack_diff",
    "defense_diff",
    "win_rate_diff",
    "is_knockout",
    "onside_home_win_pct",
    "onside_draw_pct",
    "onside_away_win_pct",
    "has_onside",
]


def _load_team_stats(conn: Connection) -> pd.DataFrame:
    """Aggregate team stats across all competitions.

    Prefers StatsBomb xG for attack; falls back to goals/match.
    Returns one row per team.
    """
    sql = text("""
        SELECT
            team_canonical,
            SUM(goals_scored)::float / NULLIF(SUM(matches_played), 0)   AS goals_per_match,
            SUM(goals_conceded)::float / NULLIF(SUM(matches_played), 0) AS defense,
            -- Average of per-competition xG averages (weighted by matches implicitly)
            SUM(COALESCE(avg_xg_per_match, 0) * matches_played)::float
                / NULLIF(SUM(
                    CASE WHEN avg_xg_per_match IS NOT NULL THEN matches_played ELSE 0 END
                ), 0)                                                    AS avg_xg,
            SUM(wins)::float / NULLIF(SUM(matches_played), 0)           AS win_rate,
            (SUM(wins) * 3 + SUM(draws))::float
                / NULLIF(SUM(matches_played), 0)                        AS pts_per_match
        FROM gold.mart_performance
        WHERE matches_played > 0
        GROUP BY team_canonical
    """)
    df = pd.read_sql(sql, conn)
    df["attack"] = df["avg_xg"].fillna(df["goals_per_match"]).fillna(LAMBDA_GLOBAL)
    df["defense"] = df["defense"].fillna(LAMBDA_GLOBAL)
    df["win_rate"] = df["win_rate"].fillna(1 / 3)
    df["pts_per_match"] = df["pts_per_match"].fillna(1.0)
    return df.set_index("team_canonical")


def _load_onside(conn: Connection) -> pd.DataFrame:
    """Load Onside Arena probabilities (WC2026 only)."""
    sql = text("""
        SELECT
            home_team,
            away_team,
            home_win_pct,
            draw_pct,
            away_win_pct
        FROM gold.mart_predictions
    """)
    try:
        return pd.read_sql(sql, conn)
    except Exception:
        return pd.DataFrame(
            columns=["home_team", "away_team", "home_win_pct", "draw_pct", "away_win_pct"]
        )


def _is_knockout(stage: str) -> int:
    if isinstance(stage, str) and stage.lower().startswith("group"):
        return 0
    return 1


def build_features(conn: Connection) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Build feature matrix for all completed matches.

    Returns:
        X    — DataFrame of FEATURE_COLS (float64, no nulls)
        y    — Series with target: 'home_win' | 'draw' | 'away_win'
        meta — match metadata (match_id, match_date, teams, competition)
    """
    matches_sql = text("""
        SELECT
            match_id,
            match_date,
            competition_slug,
            stage,
            home_team_canonical,
            away_team_canonical,
            result
        FROM gold.fact_matches
        WHERE result IS NOT NULL
          AND home_team_canonical IS NOT NULL
          AND away_team_canonical IS NOT NULL
        ORDER BY match_date
    """)
    matches = pd.read_sql(matches_sql, conn)

    team_stats = _load_team_stats(conn)
    onside = _load_onside(conn)

    rows = []
    for _, m in matches.iterrows():
        ht = m["home_team_canonical"]
        at = m["away_team_canonical"]

        hs = team_stats.loc[ht] if ht in team_stats.index else None
        as_ = team_stats.loc[at] if at in team_stats.index else None

        home_attack = float(hs["attack"]) if hs is not None else LAMBDA_GLOBAL
        away_attack = float(as_["attack"]) if as_ is not None else LAMBDA_GLOBAL
        home_defense = float(hs["defense"]) if hs is not None else LAMBDA_GLOBAL
        away_defense = float(as_["defense"]) if as_ is not None else LAMBDA_GLOBAL
        home_win_rate = float(hs["win_rate"]) if hs is not None else 1 / 3
        away_win_rate = float(as_["win_rate"]) if as_ is not None else 1 / 3
        home_pts = float(hs["pts_per_match"]) if hs is not None else 1.0
        away_pts = float(as_["pts_per_match"]) if as_ is not None else 1.0

        # Onside lookup (fuzzy: match on home_team substring)
        onside_row = onside[
            (onside["home_team"].str.lower() == ht.lower())
            & (onside["away_team"].str.lower() == at.lower())
        ]
        has_onside = len(onside_row) > 0
        o_home = float(onside_row["home_win_pct"].iloc[0]) if has_onside else 0.0
        o_draw = float(onside_row["draw_pct"].iloc[0]) if has_onside else 0.0
        o_away = float(onside_row["away_win_pct"].iloc[0]) if has_onside else 0.0

        rows.append(
            {
                "home_attack": home_attack,
                "away_attack": away_attack,
                "home_defense": home_defense,
                "away_defense": away_defense,
                "home_win_rate": home_win_rate,
                "away_win_rate": away_win_rate,
                "home_pts_per_match": home_pts,
                "away_pts_per_match": away_pts,
                "attack_diff": home_attack - away_attack,
                "defense_diff": home_defense - away_defense,
                "win_rate_diff": home_win_rate - away_win_rate,
                "is_knockout": _is_knockout(m["stage"]),
                "onside_home_win_pct": o_home,
                "onside_draw_pct": o_draw,
                "onside_away_win_pct": o_away,
                "has_onside": int(has_onside),
            }
        )

    X = pd.DataFrame(rows, columns=FEATURE_COLS).astype(np.float64)
    y = matches["result"].reset_index(drop=True)
    meta = matches[
        [
            "match_id",
            "match_date",
            "competition_slug",
            "stage",
            "home_team_canonical",
            "away_team_canonical",
        ]
    ].reset_index(drop=True)

    return X, y, meta
