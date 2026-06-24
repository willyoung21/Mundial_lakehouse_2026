-- Predicciones vs resultados reales WC2026.
-- Una fila por partido: probabilidades del modelo Onside + resultado real + acierto.
-- Diseñado para visualización en Looker Studio: tabla de aciertos del modelo.
-- Fuente predicciones: Onside Arena (CC BY 4.0) · onsidearena.com

with predictions as (
    select * from {{ ref('stg_onside_predictions') }}
),

-- Solo partidos WC2026 con resultado disponible
played as (
    select *
    from predictions
    where actual_home_goals is not null
      and actual_away_goals is not null
)

select
    fixture_id,
    kickoff_utc,
    "group",
    matchday,
    home_team,
    away_team,
    favourite_code,

    -- Probabilidades del modelo (0-100)
    home_win_pct,
    draw_pct,
    away_win_pct,

    -- Predicción del modelo (resultado con mayor probabilidad)
    predicted_result,

    -- Resultado real
    actual_home_goals,
    actual_away_goals,
    actual_result,

    -- Acierto: el resultado predicho coincide con el real
    predicted_result = actual_result                    as prediction_correct,

    -- Nivel de confianza: diferencia entre la probabilidad más alta y la segunda
    greatest(home_win_pct, draw_pct, away_win_pct)
        - case
            when greatest(home_win_pct, draw_pct, away_win_pct) = home_win_pct
                then greatest(draw_pct, away_win_pct)
            when greatest(home_win_pct, draw_pct, away_win_pct) = draw_pct
                then greatest(home_win_pct, away_win_pct)
            else greatest(home_win_pct, draw_pct)
          end                                           as model_confidence_gap

from played
order by kickoff_utc
