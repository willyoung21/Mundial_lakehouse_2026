"""Análisis táctico: xG scatter, favoritos al título, distribución de resultados."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st
from utils.charts import champion_odds_bars, results_donut, xg_scatter
from utils.db import query

st.set_page_config(page_title="Analytics | WC2026", page_icon="📈", layout="wide")
st.title("📈 Analytics — WC2026 Tactical Intelligence")
st.caption("Datos de StatsBomb (xG) + Onside Arena (champion odds) + worldcup26.ir (resultados)")

tab_xg, tab_odds, tab_dist = st.tabs(
    [
        "⚽ xG por Equipo",
        "🏆 Favoritos al Título",
        "📊 Distribución de Resultados",
    ]
)

# ── Tab 1: xG scatter ─────────────────────────────────────────────────────────
with tab_xg:
    st.subheader("Ataque vs Defensa — xG WC2026")
    st.caption(
        "Eje X: xG ofensivo por partido. Eje Y: goles concedidos por partido (↓ = mejor defensa). "
        "Cuadrante inferior-derecho = equipos elite."
    )

    @st.cache_data(ttl=300)
    def load_xg_data() -> pd.DataFrame:
        return query("""
            SELECT team_canonical,
                   confederation,
                   avg_xg_per_match,
                   ROUND(goals_conceded::numeric / NULLIF(matches_played, 0), 2) AS ga_per_match,
                   matches_played,
                   goals_scored,
                   goals_conceded
            FROM gold.mart_performance
            WHERE competition_slug = 'wc2026' AND matches_played > 0
            ORDER BY avg_xg_per_match DESC NULLS LAST
        """)

    df_xg = load_xg_data()

    if df_xg.empty:
        st.info(
            "No hay datos de xG para WC2026 todavía. Los datos de xG provienen de StatsBomb (disponibles al finalizar el torneo)."
        )
        # Fallback: mostrar goles reales si no hay xG
        df_fallback = query("""
            SELECT team_canonical,
                   confederation,
                   ROUND(goals_scored::numeric / NULLIF(matches_played, 0), 2) AS avg_xg_per_match,
                   ROUND(goals_conceded::numeric / NULLIF(matches_played, 0), 2) AS ga_per_match,
                   matches_played
            FROM gold.mart_performance
            WHERE competition_slug = 'wc2026' AND matches_played > 0
        """)
        if not df_fallback.empty:
            st.caption("Mostrando goles reales (xG no disponible aún).")
            st.plotly_chart(xg_scatter(df_fallback), use_container_width=True)
    else:
        st.plotly_chart(xg_scatter(df_xg), use_container_width=True)

        with st.expander("Ver tabla de datos"):
            cols_show = [
                "team_canonical",
                "confederation",
                "avg_xg_per_match",
                "ga_per_match",
                "matches_played",
            ]
            st.dataframe(
                df_xg[[c for c in cols_show if c in df_xg.columns]].rename(
                    columns={
                        "team_canonical": "Equipo",
                        "confederation": "Conf",
                        "avg_xg_per_match": "xG/partido",
                        "ga_per_match": "GA/partido",
                        "matches_played": "PJ",
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )

    # xG comparativo entre competiciones
    st.subheader("xG promedio por competición (contexto histórico)")
    df_comp = query("""
        SELECT competition_slug,
               ROUND(AVG(avg_xg_per_match)::numeric, 3) AS avg_xg
        FROM gold.mart_performance
        WHERE avg_xg_per_match IS NOT NULL AND matches_played > 0
        GROUP BY competition_slug
        ORDER BY avg_xg DESC
    """)
    if not df_comp.empty:
        import plotly.express as px

        fig_comp = px.bar(
            df_comp,
            x="competition_slug",
            y="avg_xg",
            labels={"competition_slug": "Competición", "avg_xg": "xG promedio / partido"},
            color="avg_xg",
            color_continuous_scale="Blues",
            title="xG promedio por competición",
            height=350,
        )
        fig_comp.update_layout(showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig_comp, use_container_width=True)

# ── Tab 2: Champion odds ───────────────────────────────────────────────────────
with tab_odds:
    st.subheader("Favoritos al Título — Predicciones Monte Carlo (Onside Arena)")
    st.caption("10,000 simulaciones del torneo por equipo. Datos CC BY 4.0 de Onside Arena.")

    @st.cache_data(ttl=600)
    def load_champion_odds() -> pd.DataFrame:
        return query("""
            SELECT team_canonical, team_name, confederation,
                   champion_pct, reach_final_pct, reach_semi_pct,
                   reach_qf_pct, champion_rank
            FROM gold.mart_champion_odds
            ORDER BY champion_rank ASC
            LIMIT 32
        """)

    df_odds = load_champion_odds()

    if df_odds.empty:
        st.info(
            "No hay datos de Onside Arena disponibles. Ejecuta: `python -m ingestion.onside_loader`"
        )
    else:
        n_show = st.slider("Top N equipos", 10, 32, 20)
        st.plotly_chart(champion_odds_bars(df_odds, n=n_show), use_container_width=True)

        # Tabla detallada
        with st.expander("Ver tabla completa de probabilidades"):
            cols_show = [
                "champion_rank",
                "team_canonical",
                "confederation",
                "champion_pct",
                "reach_final_pct",
                "reach_semi_pct",
                "reach_qf_pct",
            ]
            display = df_odds[[c for c in cols_show if c in df_odds.columns]].rename(
                columns={
                    "champion_rank": "#",
                    "team_canonical": "Equipo",
                    "confederation": "Conf",
                    "champion_pct": "Campeón %",
                    "reach_final_pct": "Final %",
                    "reach_semi_pct": "Semi %",
                    "reach_qf_pct": "Cuartos %",
                }
            )
            st.dataframe(
                display,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Campeón %": st.column_config.NumberColumn("Campeón %", format="%.1f%%"),
                    "Final %": st.column_config.NumberColumn("Final %", format="%.1f%%"),
                    "Semi %": st.column_config.NumberColumn("Semi %", format="%.1f%%"),
                    "Cuartos %": st.column_config.NumberColumn("Cuartos %", format="%.1f%%"),
                },
            )

# ── Tab 3: Distribución de resultados ─────────────────────────────────────────
with tab_dist:
    st.subheader("Distribución de Resultados — WC2026 vs Histórico")

    @st.cache_data(ttl=300)
    def load_results() -> tuple[dict, dict]:
        df_wc = query("""
            SELECT result, COUNT(*) AS n
            FROM gold.fact_matches
            WHERE data_source = 'api_football' AND result IS NOT NULL
            GROUP BY result
        """)
        df_hist = query("""
            SELECT result, COUNT(*) AS n
            FROM gold.fact_matches
            WHERE data_source != 'api_football' AND result IS NOT NULL
              AND competition_slug IN ('wc_historical', 'wc_history')
            GROUP BY result
        """)
        wc = {row["result"]: row["n"] for _, row in df_wc.iterrows()}
        hist_total = df_hist["n"].sum() if not df_hist.empty else 1
        hist = {
            row["result"]: round(row["n"] / hist_total * 100, 1) for _, row in df_hist.iterrows()
        }
        return wc, hist

    wc_counts, hist_pcts = load_results()

    if not wc_counts:
        st.info("No hay resultados de WC2026 todavía.")
    else:
        col1, col2, col3 = st.columns(3)
        total = sum(wc_counts.values()) or 1
        col1.metric(
            "Victoria local",
            f"{wc_counts.get('home_win', 0)}",
            f"{wc_counts.get('home_win', 0) / total * 100:.1f}%",
        )
        col2.metric(
            "Empates",
            f"{wc_counts.get('draw', 0)}",
            f"{wc_counts.get('draw', 0) / total * 100:.1f}%",
        )
        col3.metric(
            "Victoria visitante",
            f"{wc_counts.get('away_win', 0)}",
            f"{wc_counts.get('away_win', 0) / total * 100:.1f}%",
        )

        fig_donut = results_donut(wc_counts, hist_pcts if hist_pcts else None)
        st.plotly_chart(fig_donut, use_container_width=True)

        # Tabla por fase
        st.subheader("Por fase del torneo")
        df_by_stage = query("""
            SELECT stage,
                   COUNT(*) FILTER (WHERE result = 'home_win') AS local,
                   COUNT(*) FILTER (WHERE result = 'draw') AS empates,
                   COUNT(*) FILTER (WHERE result = 'away_win') AS visitante,
                   COUNT(*) AS total
            FROM gold.fact_matches
            WHERE data_source = 'api_football' AND result IS NOT NULL
            GROUP BY stage
            ORDER BY stage
        """)
        if not df_by_stage.empty:
            df_by_stage["% local"] = (df_by_stage["local"] / df_by_stage["total"] * 100).round(1)
            df_by_stage["% empate"] = (df_by_stage["empates"] / df_by_stage["total"] * 100).round(1)
            df_by_stage["% visit."] = (df_by_stage["visitante"] / df_by_stage["total"] * 100).round(
                1
            )
            st.dataframe(
                df_by_stage[
                    [
                        "stage",
                        "total",
                        "local",
                        "empates",
                        "visitante",
                        "% local",
                        "% empate",
                        "% visit.",
                    ]
                ].rename(
                    columns={
                        "stage": "Fase",
                        "total": "Total",
                        "local": "Local",
                        "empates": "Empate",
                        "visitante": "Visitante",
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )
