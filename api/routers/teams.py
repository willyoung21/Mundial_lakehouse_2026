from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.database import get_db

router = APIRouter(prefix="/team", tags=["teams"])


@router.get("/{code}/stats")
def team_stats(code: str, conn: Connection = Depends(get_db)):
    """Performance stats for a team across all competitions in the Gold layer.

    `code` is the FIFA 3-letter code (e.g. ESP, BRA, ARG).
    """
    sql = text("""
        SELECT
            team_canonical,
            fifa_code,
            confederation,
            competition_slug,
            competition_slug AS competition,
            matches_played,
            wins,
            draws,
            losses,
            goals_scored,
            goals_conceded,
            goal_diff,
            points,
            ROUND(win_pct::numeric, 1)              AS win_pct,
            ROUND(avg_xg_per_match::numeric, 3)     AS avg_xg_per_match,
            ROUND(total_xg::numeric, 2)             AS total_xg,
            total_shots,
            ROUND(xg_overperformance::numeric, 3)   AS xg_overperformance,
            last_match_date
        FROM gold.mart_performance
        WHERE UPPER(fifa_code) = UPPER(:code)
        ORDER BY competition_slug
    """)
    rows = conn.execute(sql, {"code": code.upper()}).mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Team '{code}' not found in mart_performance")

    return {
        "team": rows[0]["team_canonical"],
        "code": rows[0]["fifa_code"],
        "confederation": rows[0]["confederation"],
        "stats_by_competition": [dict(r) for r in rows],
    }


@router.get("")
def list_teams(conn: Connection = Depends(get_db)):
    """List all teams with their WC2026 aggregated stats (or best available if no WC2026 data yet)."""
    sql = text("""
        WITH ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY team_canonical
                       ORDER BY
                           CASE WHEN competition_slug = 'wc2026' THEN 0 ELSE 1 END,
                           matches_played DESC
                   ) AS rn
            FROM gold.mart_performance
        )
        SELECT
            team_canonical,
            fifa_code,
            confederation,
            competition_slug,
            matches_played,
            wins,
            draws,
            losses,
            goals_scored,
            goals_conceded,
            goal_diff,
            points,
            ROUND(win_pct::numeric, 1)          AS win_pct,
            ROUND(avg_xg_per_match::numeric, 3) AS avg_xg_per_match
        FROM ranked
        WHERE rn = 1
        ORDER BY team_canonical
    """)
    rows = conn.execute(sql).mappings().all()
    return [dict(r) for r in rows]
