-- Estadisticas de jugadores en el WC2026 (vacío hasta que la API libere datos de jugadores).
-- La tabla bronze_raw.api_player_stats no existe todavía; devolvemos un result set vacío
-- con el esquema correcto para que los marts downstream no fallen.

select
    null::bigint    as match_id,
    null::bigint    as player_id_api,
    null::text      as player_name,
    null::int       as team_id_api,
    null::text      as team_name,
    null::int       as minutes_played,
    null::float     as rating,
    null::int       as goals,
    null::int       as assists,
    null::int       as shots_total,
    null::int       as shots_on_target,
    null::int       as passes_total,
    null::int       as passes_key,
    null::float     as passes_accuracy,
    null::int       as tackles,
    null::int       as interceptions,
    null::int       as duels_won,
    null::int       as dribbles_success,
    null::int       as yellow_cards,
    null::int       as red_cards,
    'wc2026'::text  as competition_slug
where false
