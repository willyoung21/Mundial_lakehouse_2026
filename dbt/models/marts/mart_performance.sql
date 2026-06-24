-- Rendimiento de equipos por competición: forma, goles, xG promedio.
-- Combinación de métricas de partido (fact_matches) y xG de eventos StatsBomb.
-- Diseñado para el dashboard principal de Looker Studio.

with matches as (
    select * from {{ ref('fact_matches') }}
),

-- xG por equipo por partido (solo StatsBomb)
team_xg as (
    select
        match_id,
        competition_slug,
        team_id_sb::int                                         as team_id_sb,
        team_name,
        sum(shot_xg)                                            as xg_total,
        count(*) filter (where event_type = 'Shot')             as shots_total,
        count(*) filter (where event_type = 'Shot'
                         and shot_outcome = 'Goal')             as goals_from_events
    from {{ ref('stg_events_sb') }}
    where event_type = 'Shot'
    group by match_id, competition_slug, team_id_sb, team_name
),

dim_teams as (
    select canonical_name, statsbomb_id, apifootball_id, fifa_code, confederation
    from {{ ref('dim_teams') }}
),

-- Resultados desde perspectiva de cada equipo
team_results as (
    -- Como local
    select
        match_id,
        match_date,
        competition_slug,
        home_team_canonical                 as team_canonical,
        home_team_code                      as fifa_code,
        home_confederation                  as confederation,
        home_score                          as goals_scored,
        away_score                          as goals_conceded,
        case result when 'home_win' then 1 else 0 end   as won,
        case result when 'draw'     then 1 else 0 end   as drawn,
        case result when 'away_win' then 1 else 0 end   as lost,
        data_source
    from matches
    where home_score is not null

    union all

    -- Como visitante
    select
        match_id,
        match_date,
        competition_slug,
        away_team_canonical                 as team_canonical,
        away_team_code                      as fifa_code,
        away_confederation                  as confederation,
        away_score                          as goals_scored,
        home_score                          as goals_conceded,
        case result when 'away_win' then 1 else 0 end   as won,
        case result when 'draw'     then 1 else 0 end   as drawn,
        case result when 'home_win' then 1 else 0 end   as lost,
        data_source
    from matches
    where away_score is not null
),

-- Agregar por equipo y competición
team_summary as (
    select
        team_canonical,
        fifa_code,
        confederation,
        competition_slug,
        count(*)                                    as matches_played,
        sum(won)                                    as wins,
        sum(drawn)                                  as draws,
        sum(lost)                                   as losses,
        sum(goals_scored)                           as goals_scored,
        sum(goals_conceded)                         as goals_conceded,
        sum(goals_scored) - sum(goals_conceded)     as goal_diff,
        -- Puntos estilo liga
        sum(won) * 3 + sum(drawn)                   as points,
        -- Win rate
        round(sum(won)::numeric / nullif(count(*), 0) * 100, 1)
                                                    as win_pct,
        max(match_date)                             as last_match_date
    from team_results
    group by team_canonical, fifa_code, confederation, competition_slug
),

-- Agregar xG desde StatsBomb
team_xg_summary as (
    select
        dt.canonical_name                           as team_canonical,
        tx.competition_slug,
        round(avg(tx.xg_total)::numeric, 3)         as avg_xg_per_match,
        round(sum(tx.xg_total)::numeric, 3)         as total_xg,
        sum(tx.shots_total)                         as total_shots
    from team_xg tx
    join dim_teams dt on lower(tx.team_name) = lower(dt.canonical_name)
    group by dt.canonical_name, tx.competition_slug
),

final as (
    select
        ts.*,
        txs.avg_xg_per_match,
        txs.total_xg,
        txs.total_shots,
        -- xG diff = xG generated vs goals scored (shooting efficiency)
        round((txs.total_xg - ts.goals_scored)::numeric, 3) as xg_overperformance
    from team_summary ts
    left join team_xg_summary txs
        on ts.team_canonical = txs.team_canonical
        and ts.competition_slug = txs.competition_slug
)

select * from final
order by competition_slug, points desc, goal_diff desc
