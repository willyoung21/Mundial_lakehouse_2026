-- Estadísticas por 90 minutos de temporada de club (2025-26) para jugadores WC2026.
-- Fuente: Rising Transfers (CC BY 4.0) · github.com/risingtransfers/world-cup-2026-data
-- Solo jugadores con ≥450 minutos en liga para reducir ruido estadístico.
-- Join key con stg_wc2026_squads: player_id (RT) o player_name.
--
-- Nota: columnas per90 exactas dependen del CSV descargado.
-- Inspeccionar con: SELECT column_name FROM information_schema.columns
--                   WHERE table_schema = 'bronze_raw' AND table_name = 'wc2026_per90';

with source as (
    select * from {{ source('bronze_raw', 'wc2026_per90') }}
)

-- Pasa todas las columnas as-is. Refinar tipos y aliases una vez que se conozcan
-- los nombres exactos de las columnas per90 descargando el CSV real.
-- Inspeccionar con: SELECT column_name FROM information_schema.columns
--                   WHERE table_schema='bronze_raw' AND table_name='wc2026_per90';
select *
from source
where player_name is not null
  and minutes::int >= 450
