-- Rankings de jugadores para ojeadores: métricas por 90 minutos.
-- Fuentes: StatsBomb (eventos WC2022/Euro/Copa) + Rising Transfers (per90 club 2025-26).
-- API-Football vacío (free plan) → sección api_stats queda sin filas pero no rompe el mart.

-- Nota: StatsBomb no siempre reporta minutos exactos por jugador, se usa
-- aproximación de 90 min/partido para jugadores con >0 eventos en ese partido.

with sb_stats as (
    select
        player_id_sb::text                              as player_key,
        player_id_sb,
        null::bigint                                    as player_id_api,
        player_name,
        team_id_sb::int                                 as team_id_sb,
        null::int                                       as team_id_api,
        team_name,
        competition_slug,
        count(distinct match_id)                        as matches,
        -- Aproximación: 90 min por partido con datos (conservadora)
        count(distinct match_id) * 90                   as approx_minutes,
        sum(goals)                                      as goals,
        sum(assists)                                    as assists,
        sum(xg)                                         as xg_total,
        sum(shots)                                      as shots,
        sum(passes)                                     as passes,
        sum(passes_completed)                           as passes_completed,
        sum(through_balls)                              as through_balls,
        sum(progressive_passes)                         as progressive_passes,
        sum(pressures)                                  as pressures,
        sum(carries)                                    as carries,
        sum(dribbles_completed)                         as dribbles_completed,
        sum(dribbles_attempted)                         as dribbles_attempted,
        sum(interceptions)                              as interceptions,
        sum(blocks)                                     as blocks,
        sum(clearances)                                 as clearances,
        sum(ball_recoveries)                            as ball_recoveries
    from {{ ref('stg_player_stats_sb') }}
    where player_id_sb is not null
    group by player_key, player_id_sb, player_name, team_id_sb, team_name, competition_slug
),

api_stats as (
    select
        'api_' || player_id_api::text                   as player_key,
        null::text                                      as player_id_sb,
        player_id_api,
        player_name,
        null::int                                       as team_id_sb,
        team_id_api,
        team_name,
        competition_slug,
        count(distinct match_id)                        as matches,
        sum(coalesce(minutes_played, 90))               as approx_minutes,
        sum(coalesce(goals, 0))                         as goals,
        sum(coalesce(assists, 0))                       as assists,
        null::float                                     as xg_total,
        sum(coalesce(shots_total, 0))                   as shots,
        sum(coalesce(passes_total, 0))                  as passes,
        null::int                                       as passes_completed,
        null::int                                       as through_balls,
        null::int                                       as progressive_passes,
        null::int                                       as pressures,
        null::int                                       as carries,
        sum(coalesce(dribbles_success, 0))              as dribbles_completed,
        null::int                                       as dribbles_attempted,
        sum(coalesce(interceptions, 0))                 as interceptions,
        null::int                                       as blocks,
        null::int                                       as clearances,
        null::int                                       as ball_recoveries
    from {{ ref('stg_player_stats_wc2026') }}
    where player_id_api is not null
    group by player_key, player_id_api, player_name, team_id_api, team_name, competition_slug
),

all_stats as (
    select * from sb_stats
    union all
    select * from api_stats
),

dim_teams as (
    select canonical_name, statsbomb_id, apifootball_id, fifa_code, confederation
    from {{ ref('dim_teams') }}
),

final as (
    select
        s.player_key,
        s.player_id_sb,
        s.player_id_api,
        s.player_name,
        s.team_name,
        coalesce(dt.canonical_name, s.team_name)    as team_canonical,
        dt.fifa_code,
        dt.confederation,
        s.competition_slug,
        s.matches,
        s.approx_minutes,

        -- Totales
        s.goals,
        s.assists,
        round(s.xg_total::numeric, 3)               as xg_total,
        s.shots,
        s.passes,
        s.pressures,
        s.interceptions,
        s.dribbles_completed,
        s.ball_recoveries,

        -- Métricas por 90 minutos (corazón del scouting)
        round((s.goals::float / nullif(s.approx_minutes, 0) * 90)::numeric, 3)
                                                    as goals_per90,
        round((s.xg_total / nullif(s.approx_minutes, 0) * 90)::numeric, 3)
                                                    as xg_per90,
        round((s.shots::float / nullif(s.approx_minutes, 0) * 90)::numeric, 3)
                                                    as shots_per90,
        round((s.pressures::float / nullif(s.approx_minutes, 0) * 90)::numeric, 3)
                                                    as pressures_per90,
        round((s.progressive_passes::float / nullif(s.approx_minutes, 0) * 90)::numeric, 3)
                                                    as progressive_passes_per90,
        round((s.interceptions::float / nullif(s.approx_minutes, 0) * 90)::numeric, 3)
                                                    as interceptions_per90,
        round((s.ball_recoveries::float / nullif(s.approx_minutes, 0) * 90)::numeric, 3)
                                                    as ball_recoveries_per90,

        -- Eficiencia de pases
        round((s.passes_completed::float / nullif(s.passes, 0) * 100)::numeric, 1)
                                                    as pass_accuracy_pct,

        -- Eficiencia de dribbling
        round((s.dribbles_completed::float / nullif(s.dribbles_attempted, 0) * 100)::numeric, 1)
                                                    as dribble_success_pct

    from all_stats s
    left join dim_teams dt
        on s.team_id_sb = dt.statsbomb_id
        or s.team_id_api = dt.apifootball_id
    -- Solo jugadores con al menos 1 partido completo para métricas estables
    where s.matches >= 1
),

-- Enriquecimiento con datos de temporada de club (Rising Transfers)
rt_squads as (
    select player_id_rt, player_name, team_code, position, club, age, market_value_eur
    from {{ ref('stg_wc2026_squads') }}
),

final_enriched as (
    select
        f.*,
        -- Identidad de jugador WC2026 (desde Rising Transfers)
        rt.team_code                                as rt_team_code,
        rt.position                                 as rt_position,
        rt.club                                     as rt_club,
        rt.age                                      as rt_age,
        rt.market_value_eur                         as rt_market_value_eur
    from final f
    left join rt_squads rt
        on lower(f.player_name) = lower(rt.player_name)
)

select * from final_enriched
order by competition_slug, xg_per90 desc nulls last
