-- Predicciones pre-partido WC2026 con probabilidades Monte Carlo (10,000 simulaciones).
-- Fuente: Onside Arena (CC BY 4.0) · onsidearena.com/data
-- Se actualiza durante el torneo: actual_home_goals / actual_away_goals se rellenan
-- conforme se juegan los partidos. verdict = fav_won / fav_lost.

with source as (
    select * from {{ source('bronze_raw', 'onside_predictions') }}
)

select
    fixture_id,
    kickoff_utc::timestamp with time zone                as kickoff_utc,
    "group",
    matchday::int,
    home_code,
    home_name                                            as home_team,
    away_code,
    away_name                                            as away_team,

    model_home_pct::float                                as home_win_pct,
    model_draw_pct::float                                as draw_pct,
    model_away_pct::float                                as away_win_pct,
    favourite_code,

    -- Resultado real (NULL hasta que se juega el partido)
    actual_home_goals::int                               as actual_home_goals,
    actual_away_goals::int                               as actual_away_goals,

    -- fav_won / fav_lost — determinado por Onside
    verdict,

    -- Columnas derivadas
    case
        when model_home_pct >= model_draw_pct and model_home_pct >= model_away_pct then 'home_win'
        when model_away_pct >= model_draw_pct and model_away_pct >= model_home_pct then 'away_win'
        else 'draw'
    end                                                  as predicted_result,

    case
        when actual_home_goals is not null and actual_away_goals is not null
        then case
            when actual_home_goals > actual_away_goals then 'home_win'
            when actual_home_goals < actual_away_goals then 'away_win'
            else 'draw'
        end
        else null
    end                                                  as actual_result

from source
