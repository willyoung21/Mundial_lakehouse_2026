-- Estadísticas agregadas por jugador por partido (desde eventos StatsBomb).
-- Una fila por jugador por partido. Base para mart_player_scouting.
-- Las métricas /90 se calculan en Gold donde se conocen los minutos jugados.

with events as (
    select * from {{ ref('stg_events_sb') }}
),

player_match_stats as (
    select
        match_id,
        competition_slug,
        player_id_sb,
        player_name,
        team_id_sb,
        team_name,

        -- Tiros y xG
        count(*) filter (where event_type = 'Shot')                             as shots,
        count(*) filter (where event_type = 'Shot' and shot_outcome = 'Goal')  as goals,
        coalesce(sum(shot_xg) filter (where event_type = 'Shot'), 0)           as xg,

        -- Pases
        count(*) filter (where event_type = 'Pass')                            as passes,
        count(*) filter (where event_type = 'Pass' and pass_outcome is null)   as passes_completed,
        count(*) filter (where event_type = 'Pass' and pass_goal_assist)       as assists,
        count(*) filter (where event_type = 'Pass' and pass_through_ball)      as through_balls,
        count(*) filter (where event_type = 'Pass' and pass_progressive)       as progressive_passes,

        -- Presiones defensivas
        count(*) filter (where event_type = 'Pressure')                        as pressures,

        -- Porteo progresivo
        count(*) filter (where event_type = 'Carry')                           as carries,

        -- Dribbling
        count(*) filter (where event_type = 'Dribble' and dribble_outcome = 'Complete')
                                                                                as dribbles_completed,
        count(*) filter (where event_type = 'Dribble')                        as dribbles_attempted,

        -- Acciones defensivas
        count(*) filter (where event_type = 'Interception')                    as interceptions,
        count(*) filter (where event_type = 'Block')                           as blocks,
        count(*) filter (where event_type = 'Clearance')                       as clearances,
        count(*) filter (where event_type = 'Ball Recovery')                   as ball_recoveries,

        -- Duelos
        count(*) filter (where event_type = 'Duel')                            as duels

    from events
    where player_id_sb is not null
    group by
        match_id,
        competition_slug,
        player_id_sb,
        player_name,
        team_id_sb,
        team_name
)

select * from player_match_stats
