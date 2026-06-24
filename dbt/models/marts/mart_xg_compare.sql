-- Comparativa de xG promedio por equipo entre competiciones.
-- Permite ver si un equipo mejoró o empeoró su calidad de llegadas de
-- Copa América/Euro 2020 → WC2022 → WC2026.
-- Útil para el análisis táctico y como feature para el modelo ML.

with team_xg as (
    select
        competition_slug,
        team_id_sb::int                                     as team_id_sb,
        team_name,
        match_id,
        sum(shot_xg)                                        as match_xg,
        count(*) filter (where event_type = 'Shot')         as shots
    from {{ ref('stg_events_sb') }}
    where event_type = 'Shot'
    group by competition_slug, team_id_sb, team_name, match_id
),

dim_teams as (
    select canonical_name, statsbomb_id, fifa_code, confederation
    from {{ ref('dim_teams') }}
),

-- xG promedio por partido para cada competición StatsBomb
xg_by_competition as (
    select
        coalesce(dt.canonical_name, tx.team_name)                   as team_canonical,
        dt.fifa_code,
        dt.confederation,

        -- WC 2022
        round(avg(match_xg) filter (where competition_slug = 'wc2022')::numeric, 3)
                                                                    as xg_wc2022,
        count(match_id) filter (where competition_slug = 'wc2022') as matches_wc2022,

        -- Copa América 2024
        round(avg(match_xg) filter (where competition_slug = 'copa_america_2024')::numeric, 3)
                                                                    as xg_copa_2024,
        count(match_id) filter (where competition_slug = 'copa_america_2024')
                                                                    as matches_copa_2024,

        -- UEFA Euro 2020
        round(avg(match_xg) filter (where competition_slug = 'euro_2020')::numeric, 3)
                                                                    as xg_euro_2020,
        count(match_id) filter (where competition_slug = 'euro_2020')
                                                                    as matches_euro_2020,

        -- UEFA Euro 2024
        round(avg(match_xg) filter (where competition_slug = 'euro_2024')::numeric, 3)
                                                                    as xg_euro_2024,
        count(match_id) filter (where competition_slug = 'euro_2024')
                                                                    as matches_euro_2024

    from team_xg tx
    left join dim_teams dt on tx.team_id_sb = dt.statsbomb_id
    group by coalesce(dt.canonical_name, tx.team_name), dt.fifa_code, dt.confederation
),

-- xG de WC2026 vacío — api_team_stats no existe (API-Football free plan no cubre WC2026).
-- Se llenará cuando haya xG real disponible.
wc2026_xg as (
    select
        null::text    as team_canonical,
        null::numeric as xg_wc2026,
        null::bigint  as matches_wc2026
    where false
),

final as (
    select
        xc.team_canonical,
        xc.fifa_code,
        xc.confederation,
        xc.xg_wc2022,
        xc.matches_wc2022,
        xc.xg_copa_2024,
        xc.matches_copa_2024,
        xc.xg_euro_2020,
        xc.matches_euro_2020,
        xc.xg_euro_2024,
        xc.matches_euro_2024,
        w26.xg_wc2026,
        w26.matches_wc2026,

        -- Tendencia: promedio de competiciones previas al WC2022 (Copa 2024 es posterior, se excluye)
        coalesce(xc.xg_euro_2020, xc.xg_euro_2024)                 as xg_prev_euro_avg,

        round((xc.xg_wc2022 - coalesce(
            xc.xg_euro_2020,
            xc.xg_euro_2024
        ))::numeric, 3)                                             as xg_delta_wc2022_vs_euro

    from xg_by_competition xc
    left join wc2026_xg w26 on xc.team_canonical = w26.team_canonical
    where xc.team_canonical is not null
)

select * from final
order by confederation, team_canonical
