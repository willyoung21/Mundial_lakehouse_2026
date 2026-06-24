-- Tabla de hechos de partidos: union de todas las fuentes con team_key resuelto.
-- Incluye StatsBomb (WC2022, Copa América, Euro 2020) + API-Football (WC2026).
-- Los IDs de equipo se resuelven a canonical_name via dim_teams.

with sb_matches as (
    select
        match_id,
        match_date::date                                    as match_date,
        competition_slug,
        competition_name,
        season_name,
        stage,
        stadium_name,
        home_team_id_sb::int                               as home_team_id_sb,
        home_team_name,
        away_team_id_sb::int                               as away_team_id_sb,
        away_team_name,
        home_score,
        away_score,
        'statsbomb'                                        as data_source
    from {{ ref('stg_matches_sb') }}
),

wc2026_matches as (
    select
        match_id,
        match_date::date                                    as match_date,
        competition_slug,
        competition_name,
        season_name,
        stage,
        null::text                                         as stadium_name,
        home_team_id_api,
        home_team_name,
        away_team_id_api,
        away_team_name,
        home_score,
        away_score,
        'api_football'                                     as data_source
    from {{ ref('stg_matches_wc2026') }}
),

dim_teams as (
    select canonical_name, statsbomb_id, apifootball_id, fifa_code, confederation
    from {{ ref('dim_teams') }}
),

-- Unir y resolver equipos a canonical_name
fact as (
    -- Partidos StatsBomb
    select
        m.match_id,
        m.match_date,
        m.competition_slug,
        m.competition_name,
        m.season_name,
        m.stage,
        m.stadium_name,
        m.home_team_name,
        m.away_team_name,
        coalesce(ht.canonical_name, m.home_team_name)      as home_team_canonical,
        coalesce(at.canonical_name, m.away_team_name)      as away_team_canonical,
        ht.fifa_code                                        as home_team_code,
        at.fifa_code                                        as away_team_code,
        ht.confederation                                    as home_confederation,
        at.confederation                                    as away_confederation,
        m.home_score,
        m.away_score,
        case
            when m.home_score > m.away_score then 'home_win'
            when m.home_score < m.away_score then 'away_win'
            else 'draw'
        end                                                 as result,
        m.data_source
    from sb_matches m
    left join dim_teams ht on m.home_team_id_sb = ht.statsbomb_id
    left join dim_teams at on m.away_team_id_sb = at.statsbomb_id

    union all

    -- Partidos WC2026
    select
        m.match_id,
        m.match_date,
        m.competition_slug,
        m.competition_name,
        m.season_name,
        m.stage,
        m.stadium_name,
        m.home_team_name,
        m.away_team_name,
        coalesce(ht.canonical_name, m.home_team_name)      as home_team_canonical,
        coalesce(at.canonical_name, m.away_team_name)      as away_team_canonical,
        ht.fifa_code                                        as home_team_code,
        at.fifa_code                                        as away_team_code,
        ht.confederation                                    as home_confederation,
        at.confederation                                    as away_confederation,
        m.home_score,
        m.away_score,
        case
            when m.home_score is null or m.away_score is null then null
            when m.home_score > m.away_score then 'home_win'
            when m.home_score < m.away_score then 'away_win'
            else 'draw'
        end                                                 as result,
        m.data_source
    from wc2026_matches m
    -- worldcup26.ir usa sus propios IDs (distintos a los de API-Football en team_codes).
    -- El JOIN por nombre es la única forma confiable de resolver canonical_name.
    left join dim_teams ht on lower(m.home_team_name) = lower(ht.canonical_name)
    left join dim_teams at on lower(m.away_team_name) = lower(at.canonical_name)
)

select * from fact
