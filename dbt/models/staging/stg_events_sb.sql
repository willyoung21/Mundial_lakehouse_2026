-- Eventos StatsBomb aplanados — StatsBombPy 1.x ya aplana dicts anidados a columnas escalares.
-- Una fila por evento. Solo tipos relevantes (filtrado en bronze_to_neon).
-- Patrón StatsBombPy 1.x: {"id": X, "name": Y} → field (nombre string) + field_id (int).

with source as (
    select * from {{ source('bronze_raw', 'statsbomb_events') }}
),

parsed as (
    select
        id                                                               as event_id,
        match_id::bigint                                                 as match_id,
        index::int                                                       as event_index,
        period::int,
        minute::int,
        second::int,
        timestamp,
        competition_slug,

        -- StatsBombPy 1.x entrega `type` como string plano (ej: 'Shot', 'Pass')
        -- Se renombró a event_type_json en bronze_to_neon; aquí lo exponemos como event_type
        event_type_json                                                  as event_type,

        -- Jugador: player_json = nombre string, player_id = int (ambas columnas separadas)
        player_id::text                                                  as player_id_sb,
        player_json                                                      as player_name,

        -- Equipo: team_json = nombre string, team_id = int
        team_id::text                                                    as team_id_sb,
        team_json                                                        as team_name,

        -- Posición: position_json = nombre string (renombrado de position)
        position_json                                                    as position,

        -- Ubicación: sigue siendo lista [x, y] serializada por _serialize_lists()
        ((location_json::jsonb) ->> 0)::float                          as location_x,
        ((location_json::jsonb) ->> 1)::float                          as location_y,

        duration::float,
        under_pressure::boolean,

        -- ── Tiro: columnas planas shot_* (NULL para eventos que no son Shot) ─────
        shot_statsbomb_xg::float                                        as shot_xg,
        shot_outcome                                                     as shot_outcome,
        shot_body_part                                                   as shot_body_part,
        shot_first_time::boolean                                         as shot_first_time,

        -- ── Pase: columnas planas pass_* (NULL para eventos que no son Pass) ─────
        pass_goal_assist::boolean                                        as pass_goal_assist,
        pass_shot_assist::boolean                                        as pass_shot_assist,
        pass_outcome                                                     as pass_outcome,
        -- pass_outcome = NULL → pase completado; cualquier valor → pase fallido
        pass_height                                                      as pass_height,
        pass_length::float                                               as pass_length,
        pass_through_ball::boolean                                       as pass_through_ball,
        -- pass_switch = TRUE cuando el pase cambia el punto de ataque (proxy de pase progresivo)
        pass_switch::boolean                                             as pass_progressive,

        -- ── Porteo: carry_end_location es lista serializada → mismo parsing jsonb ─
        ((carry_end_location::jsonb) ->> 0)::float                     as carry_end_x,
        ((carry_end_location::jsonb) ->> 1)::float                     as carry_end_y,

        -- ── Dribbling ─────────────────────────────────────────────────────────────
        dribble_outcome                                                  as dribble_outcome

    from source
)

select * from parsed
