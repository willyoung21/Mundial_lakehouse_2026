-- Dimensión maestra de equipos: resuelve identidad entre API-Football, StatsBomb y Kaggle.
-- JOIN central del proyecto — todos los facts hacen referencia a esta tabla.
-- Agrega contexto histórico (participaciones en Mundiales) desde stg_wc_history.

with team_codes as (
    select * from {{ ref('team_codes') }}
),

wc_history as (
    select * from {{ ref('stg_wc_history') }}
),

-- Contar participaciones históricas en Mundiales
wc_appearances as (
    select
        canonical_name,
        count(distinct wc_year)     as wc_appearances,
        count(*)                    as wc_matches_played,
        sum(case
            when home_team_lower = lower(tc.canonical_name) and result = 'home_win' then 1
            when away_team_lower = lower(tc.canonical_name) and result = 'away_win' then 1
            else 0
        end)                        as wc_wins,
        max(wc_year)                as last_wc_year
    from wc_history wh
    cross join team_codes tc
    where lower(wh.home_team_raw) = any(
              string_to_array(lower(tc.alt_names), ';')
          )
       or lower(wh.away_team_raw) = any(
              string_to_array(lower(tc.alt_names), ';')
          )
    group by canonical_name
),

final as (
    select
        tc.canonical_name,
        tc.fifa_code,
        tc.confederation,

        -- IDs en cada fuente (−1 = pendiente de verificar)
        nullif(tc.apifootball_id, -1)   as apifootball_id,
        nullif(tc.statsbomb_id, -1)     as statsbomb_id,

        tc.alt_names,

        -- Contexto histórico
        coalesce(wa.wc_appearances, 0)  as wc_appearances,
        coalesce(wa.wc_matches_played, 0) as wc_matches_played,
        coalesce(wa.wc_wins, 0)         as wc_wins,
        wa.last_wc_year

    from team_codes tc
    left join wc_appearances wa on wa.canonical_name = tc.canonical_name
)

select * from final
