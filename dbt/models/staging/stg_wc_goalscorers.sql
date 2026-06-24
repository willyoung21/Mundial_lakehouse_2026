-- Goleadores de partidos de Mundiales FIFA (filtrado via JOIN con stg_wc_history).
-- La fuente Bronze tiene todos los torneos; aquí quedamos solo con WC.

with source as (
    select * from {{ source('bronze_raw', 'wc_goalscorers') }}
),

wc_matches as (
    select distinct
        match_date,
        home_team_raw,
        away_team_raw
    from {{ ref('stg_wc_history') }}
),

wc_goalscorers as (
    select
        g.date::date                        as match_date,
        g.home_team,
        g.away_team,
        g.team                              as scoring_team,
        g.scorer,
        g.minute::int                       as minute,
        g.own_goal::boolean                 as own_goal,
        g.penalty::boolean                  as penalty,
        case
            when g.own_goal then 'own_goal'
            when g.penalty  then 'penalty'
            else                 'open_play'
        end                                 as goal_type
    from source g
    join wc_matches m
      on g.date::date = m.match_date
     and g.home_team   = m.home_team_raw
     and g.away_team   = m.away_team_raw
    where g.scorer is not null
)

select * from wc_goalscorers
