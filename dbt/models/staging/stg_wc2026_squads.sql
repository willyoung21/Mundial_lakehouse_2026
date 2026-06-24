-- Planteles WC2026: 1,363 jugadores de los 48 equipos.
-- Fuente: Rising Transfers (CC BY 4.0) · github.com/risingtransfers/world-cup-2026-data
-- Complementa stg_player_stats_sb (StatsBomb) con datos de identidad de los convocados.

with source as (
    select * from {{ source('bronze_raw', 'wc2026_squads') }}
)

select
    player_id::text                                   as player_id_rt,
    player_name,
    slug                                              as rt_slug,
    country                                           as team_name,
    country_code                                      as team_code,
    position,
    club,
    age::int,
    rt_value_estimate_eur::bigint                     as market_value_eur,
    'wc2026'                                          as competition_slug
from source
where player_name is not null
