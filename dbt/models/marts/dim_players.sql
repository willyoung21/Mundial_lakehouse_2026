-- Dimensión de jugadores: perfil único por jugador con su equipo y confederación.
-- Fuentes: StatsBomb (histórico WC2022/Euro/Copa) + Rising Transfers (planteles WC2026).
-- API-Football vacío (free plan bloqueado) → stg_player_stats_wc2026 sin filas.

with sb_players as (
    select distinct
        player_id_sb::bigint                as player_id_sb,
        player_name,
        team_id_sb::int                     as team_id_sb,
        team_name                           as team_name_sb,
        competition_slug
    from {{ ref('stg_player_stats_sb') }}
    where player_id_sb is not null
),

-- Jugadores convocados al WC2026 (Rising Transfers)
rt_squads as (
    select distinct
        player_id_rt,
        player_name,
        team_name,
        team_code,
        position,
        club,
        age,
        market_value_eur
    from {{ ref('stg_wc2026_squads') }}
),

dim_teams as (
    select canonical_name, statsbomb_id, apifootball_id, confederation, fifa_code
    from {{ ref('dim_teams') }}
),

sb_deduped as (
    select distinct on (player_id_sb)
        player_id_sb,
        player_name,
        team_id_sb,
        team_name_sb
    from sb_players
    order by player_id_sb, competition_slug desc
),

final as (
    select
        coalesce(sb.player_id_sb::text, 'rt_' || rt.player_id_rt)
                                            as player_key,
        sb.player_id_sb,
        rt.player_id_rt,
        coalesce(sb.player_name, rt.player_name)
                                            as player_name,
        coalesce(sb.team_name_sb, rt.team_name)
                                            as team_name,
        -- Datos de identidad desde Rising Transfers (cuando disponibles)
        rt.team_code,
        rt.position,
        rt.club,
        rt.age,
        rt.market_value_eur,
        -- Equipo resuelto a dimensión maestra
        dt.canonical_name                   as canonical_team_name,
        dt.fifa_code,
        dt.confederation
    from sb_deduped sb
    full outer join rt_squads rt
        on lower(sb.player_name) = lower(rt.player_name)
    left join dim_teams dt
        on sb.team_id_sb = dt.statsbomb_id
        or lower(rt.team_code) = lower(dt.fifa_code)
)

select * from final
