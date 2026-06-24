-- Probabilidades de campeón WC2026 por equipo (Monte Carlo 5,000 runs).
-- Fuente: Onside Arena (CC BY 4.0) · onsidearena.com/data/champions.csv
-- Actualización horaria durante el torneo, incorporando resultados reales como priors.

with source as (
    select * from {{ source('bronze_raw', 'onside_champions') }}
)

select
    rank::int                                            as champion_rank,
    team_code,
    team_name,
    "group",
    confederation,
    champion_pct::float                                  as champion_pct,
    reach_final_pct::float                               as reach_final_pct,
    reach_semi_pct::float                                as reach_semi_pct,
    reach_qf_pct::float                                  as reach_qf_pct,
    reach_r16_pct::float                                 as reach_r16_pct
from source
