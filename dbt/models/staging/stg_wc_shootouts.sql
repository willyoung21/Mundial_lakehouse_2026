-- Tandas de penales de Mundiales FIFA (filtrado via JOIN con stg_wc_history).
-- Clave para los modelos de eliminatorias donde el ganador es por penales.

with source as (
    select * from {{ source('bronze_raw', 'wc_shootouts') }}
),

wc_matches as (
    select distinct
        match_date,
        home_team_raw,
        away_team_raw
    from {{ ref('stg_wc_history') }}
),

wc_shootouts as (
    select
        s.date::date                        as match_date,
        s.home_team,
        s.away_team,
        s.winner                            as shootout_winner,
        s.first_shooter,
        -- El perdedor es el equipo que no ganó
        case
            when s.winner = s.home_team then s.away_team
            else s.home_team
        end                                 as shootout_loser,
        -- ¿Tiene ventaja el equipo que patea primero?
        (s.winner = s.first_shooter)::boolean as first_shooter_won
    from source s
    join wc_matches m
      on s.date::date = m.match_date
     and s.home_team  = m.home_team_raw
     and s.away_team  = m.away_team_raw
)

select * from wc_shootouts
