-- Resultados históricos de Mundiales FIFA 1930-2022 desde Kaggle.
-- Limpia tipos y normaliza nombres de equipo (LOWER) para facilitar JOINs
-- con team_codes.alt_names en Gold.

with source as (
    select * from {{ source('bronze_raw', 'wc_history') }}
),

cleaned as (
    select
        date::date                                                as match_date,
        trim(home_team)                                           as home_team_raw,
        trim(away_team)                                           as away_team_raw,
        lower(trim(home_team))                                    as home_team_lower,
        lower(trim(away_team))                                    as away_team_lower,
        home_score::int                                           as home_score,
        away_score::int                                           as away_score,
        tournament,
        city,
        country,
        extract(year from date::date)::int                        as wc_year,

        -- Resultado desde perspectiva del equipo local
        case
            when home_score > away_score  then 'home_win'
            when home_score < away_score  then 'away_win'
            else                               'draw'
        end                                                       as result

    from source
    where tournament = 'FIFA World Cup'
      and home_score is not null
      and away_score is not null
)

select
    match_date,
    home_team_raw,
    away_team_raw,
    home_team_lower,
    away_team_lower,
    home_score,
    away_score,
    tournament,
    city,
    country,
    wc_year,
    result
from cleaned
