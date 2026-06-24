-- Partidos históricos de StatsBomb: WC2022, Copa América 2021, Euro 2020, Nations League.
-- statsbombpy >= 1.0 expande los dicts anidados en columnas planas — home_team es el nombre
-- del equipo (string), home_team_id es su ID, etc. No se necesita extracción ::jsonb.

with source as (
    select * from {{ source('bronze_raw', 'statsbomb_matches') }}
),

cleaned as (
    select
        match_id::bigint                                           as match_id,
        match_date::date                                          as match_date,
        kick_off                                                  as kick_off,
        home_score::int                                           as home_score,
        away_score::int                                           as away_score,
        match_status,
        match_week::int                                           as match_week,
        competition_slug,

        -- Columnas planas (statsbombpy expande los dicts anidados)
        competition_name,
        season                                                     as season_name,

        home_team_id::bigint                                       as home_team_id_sb,
        home_team                                                  as home_team_name,
        away_team_id::bigint                                       as away_team_id_sb,
        away_team                                                  as away_team_name,
        competition_stage                                          as stage,
        stadium                                                    as stadium_name

    from source
)

select * from cleaned
