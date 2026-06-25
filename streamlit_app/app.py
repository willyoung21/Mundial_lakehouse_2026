"""WC2026 Football Intelligence Dashboard — página de inicio."""

import streamlit as st
from utils.db import query

st.set_page_config(
    page_title="WC2026 Intelligence",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚽ WC2026 — Football Intelligence Dashboard")
st.caption("Pipeline de inteligencia táctica · Bronze → Silver → Gold → Predicciones")

# ── KPIs del torneo ────────────────────────────────────────────────────────────
try:
    kpi_df = query("""
        SELECT
            COUNT(*) FILTER (WHERE home_score IS NOT NULL)  AS played,
            COUNT(*) FILTER (WHERE home_score IS NULL)      AS upcoming,
            SUM(home_score + away_score) FILTER (WHERE home_score IS NOT NULL) AS total_goals
        FROM gold.fact_matches
        WHERE data_source = 'api_football'
    """)

    goleadores_df = query("""
        SELECT
            home_team_name   AS equipo,
            SUM(home_score)  AS goles
        FROM gold.fact_matches
        WHERE data_source = 'api_football' AND home_score IS NOT NULL
        GROUP BY home_team_name
        UNION ALL
        SELECT away_team_name, SUM(away_score)
        FROM gold.fact_matches
        WHERE data_source = 'api_football' AND away_score IS NOT NULL
        GROUP BY away_team_name
    """)
    top_scorer = goleadores_df.groupby("equipo")["goles"].sum().sort_values(ascending=False).head(1)

    played = int(kpi_df["played"].iloc[0] or 0)
    upcoming = int(kpi_df["upcoming"].iloc[0] or 0)
    goals = int(kpi_df["total_goals"].iloc[0] or 0)
    avg_g = round(goals / played, 2) if played else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Partidos jugados", played)
    col2.metric("Partidos pendientes", upcoming)
    col3.metric("Goles en el torneo", goals)
    col4.metric("Media goles/partido", avg_g)

except Exception as e:
    st.error(f"Error conectando a Neon: {e}")
    st.stop()

st.divider()

# ── Últimos resultados + próximos partidos ────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📋 Últimos resultados")
    recent = query("""
        SELECT match_date, stage, home_team_name, home_score, away_score, away_team_name
        FROM gold.fact_matches
        WHERE data_source = 'api_football' AND home_score IS NOT NULL
        ORDER BY match_date DESC
        LIMIT 8
    """)
    if not recent.empty:
        recent["Partido"] = (
            recent["home_team_name"]
            + "  "
            + recent["home_score"].astype(str)
            + " - "
            + recent["away_score"].astype(str)
            + "  "
            + recent["away_team_name"]
        )
        st.dataframe(
            recent[["match_date", "stage", "Partido"]].rename(
                columns={"match_date": "Fecha", "stage": "Grupo"}
            ),
            hide_index=True,
            use_container_width=True,
        )

with col_right:
    st.subheader("🗓️ Próximos partidos")
    nxt = query("""
        SELECT match_date, stage, home_team_name, away_team_name
        FROM gold.fact_matches
        WHERE data_source = 'api_football' AND home_score IS NULL
        ORDER BY match_date ASC
        LIMIT 8
    """)
    if not nxt.empty:
        nxt["home_team_name"] = nxt["home_team_name"].fillna("TBD")
        nxt["away_team_name"] = nxt["away_team_name"].fillna("TBD")
        nxt["Partido"] = nxt["home_team_name"] + " vs " + nxt["away_team_name"]
        st.dataframe(
            nxt[["match_date", "stage", "Partido"]].rename(
                columns={"match_date": "Fecha", "stage": "Grupo"}
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No hay partidos programados disponibles.")

st.divider()
st.caption(
    "Datos: worldcup26.ir · StatsBomb · Onside Arena · Rising Transfers · Kaggle  |  Actualización automática cada 5 min"
)
