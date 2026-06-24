-- Partidos en vivo del WC2026 desde worldcup26.ir.
-- Esquema alineado con stg_matches_sb para facilitar el UNION en fact_matches.
-- EDA 2026-06-18: eliminadas stadium_name, venue_city, referee (100% null en la fuente).
-- Agregada match_result como columna derivada.

with source as (
    select * from {{ source('bronze_raw', 'api_fixtures') }}
),

cleaned as (
    select
        fixture_id::bigint                                        as match_id,
        date::timestamp                                           as match_date,
        status                                                    as match_status,
        league_round                                              as stage,

        home_team_id::numeric::int                                as home_team_id_api,
        home_team_name,
        away_team_id::numeric::int                                as away_team_id_api,
        away_team_name,

        goals_home::numeric::int                                  as home_score,
        goals_away::numeric::int                                  as away_score,
        score_ht_home::numeric::int                               as ht_home_score,
        score_ht_away::numeric::int                               as ht_away_score,

        -- Resultado derivado: NULL para partidos no jugados aún
        case
            when goals_home is null or goals_away is null          then null
            when goals_home::numeric::int > goals_away::numeric::int then 'home_win'
            when goals_home::numeric::int < goals_away::numeric::int then 'away_win'
            else                                                         'draw'
        end                                                       as match_result,

        -- Columna homóloga a competition_slug de StatsBomb
        'wc2026'                                                  as competition_slug,
        'FIFA World Cup 2026'                                     as competition_name,
        '2026'                                                    as season_name

    from source
    where status in ('Match Finished', 'FT', 'AET', 'PEN', 'Scheduled', 'In Progress')
)

select * from cleaned
