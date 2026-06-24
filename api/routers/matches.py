from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.engine import Connection

from api.database import get_db

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("")
def list_matches(
    group: Optional[str] = Query(None, description="Filter by group (e.g. 'Group A')"),
    date: Optional[str] = Query(None, description="Filter by date YYYY-MM-DD"),
    status: Optional[str] = Query(None, description="Filter by status: finished | scheduled"),
    limit: int = Query(50, ge=1, le=200),
    conn: Connection = Depends(get_db),
):
    """WC2026 matches from the Gold layer. By default returns the 50 most recent."""
    filters = ["data_source = 'api_football'"]
    params: dict = {"limit": limit}

    if group:
        filters.append("stage = :group")
        params["group"] = group
    if date:
        filters.append("match_date::date = :date")
        params["date"] = date
    if status == "finished":
        filters.append("home_score IS NOT NULL")
    elif status == "scheduled":
        filters.append("home_score IS NULL")

    where = " AND ".join(filters)
    sql = text(f"""
        SELECT
            match_id,
            match_date,
            stage,
            home_team_name,
            away_team_name,
            home_team_code,
            away_team_code,
            home_confederation,
            away_confederation,
            home_score,
            away_score,
            result,
            stadium_name
        FROM gold.fact_matches
        WHERE {where}
        ORDER BY match_date DESC
        LIMIT :limit
    """)
    rows = conn.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/standings")
def get_standings(
    group: Optional[str] = Query(None, description="Filter by specific group (e.g. 'Group A')"),
    conn: Connection = Depends(get_db),
):
    """Group stage standings calculated from completed WC2026 matches."""
    group_filter = "AND stage = :group" if group else ""
    params = {"group": group} if group else {}

    sql = text(f"""
        WITH all_matches AS (
            SELECT
                stage,
                home_team_name  AS team,
                home_team_code  AS code,
                home_score      AS gf,
                away_score      AS ga,
                CASE
                    WHEN home_score > away_score THEN 3
                    WHEN home_score = away_score THEN 1
                    ELSE 0
                END AS pts,
                CASE WHEN home_score > away_score THEN 1 ELSE 0 END AS wins,
                CASE WHEN home_score = away_score THEN 1 ELSE 0 END AS draws,
                CASE WHEN home_score < away_score THEN 1 ELSE 0 END AS losses
            FROM gold.fact_matches
            WHERE data_source = 'api_football'
              AND home_score IS NOT NULL
              AND stage LIKE 'Group%'
              {group_filter}

            UNION ALL

            SELECT
                stage,
                away_team_name  AS team,
                away_team_code  AS code,
                away_score      AS gf,
                home_score      AS ga,
                CASE
                    WHEN away_score > home_score THEN 3
                    WHEN away_score = home_score THEN 1
                    ELSE 0
                END AS pts,
                CASE WHEN away_score > home_score THEN 1 ELSE 0 END AS wins,
                CASE WHEN away_score = home_score THEN 1 ELSE 0 END AS draws,
                CASE WHEN away_score < home_score THEN 1 ELSE 0 END AS losses
            FROM gold.fact_matches
            WHERE data_source = 'api_football'
              AND away_score IS NOT NULL
              AND stage LIKE 'Group%'
              {group_filter}
        )
        SELECT
            stage                   AS "group",
            team,
            code,
            COUNT(*)                AS played,
            SUM(wins)               AS wins,
            SUM(draws)              AS draws,
            SUM(losses)             AS losses,
            SUM(gf)                 AS gf,
            SUM(ga)                 AS ga,
            SUM(gf) - SUM(ga)       AS gd,
            SUM(pts)                AS points
        FROM all_matches
        GROUP BY stage, team, code
        ORDER BY stage, points DESC, gd DESC, gf DESC
    """)
    rows = conn.execute(sql, params).mappings().all()

    result: dict = {}
    for r in rows:
        grp = r["group"]
        if grp not in result:
            result[grp] = []
        result[grp].append(dict(r))
    return result
