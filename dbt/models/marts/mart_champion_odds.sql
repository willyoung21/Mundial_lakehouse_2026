-- Tableau de probabilidades de campeón WC2026, ordenado por favorito.
-- Enriquecido con nombre canónico y confederación desde dim_teams.
-- Fuente: Onside Arena (CC BY 4.0) · se refresca cada hora durante el torneo.
-- Diseñado para conectarse a Looker Studio: widget "Quién ganará el Mundial".

with champions as (
    select * from {{ ref('stg_onside_champions') }}
),

dim_teams as (
    select canonical_name, fifa_code, confederation
    from {{ ref('dim_teams') }}
)

select
    c.champion_rank,
    c.team_code,
    c.team_name,
    coalesce(dt.canonical_name, c.team_name)            as team_canonical,
    c."group",
    coalesce(dt.confederation, c.confederation)         as confederation,

    -- Probabilidades de fase (%)
    c.champion_pct,
    c.reach_final_pct,
    c.reach_semi_pct,
    c.reach_qf_pct,
    c.reach_r16_pct,

    -- Probabilidad de ser eliminado en fase de grupos (complemento de llegar a R16)
    round((100 - c.reach_r16_pct)::numeric, 2)          as eliminated_groups_pct

from champions c
left join dim_teams dt
    on lower(c.team_code) = lower(dt.fifa_code)
order by c.champion_rank
