"""Predicciones de próximos partidos — modelo Poisson Monte Carlo."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from utils.db import query
from utils.charts import probability_bars

st.set_page_config(page_title="Predicciones | WC2026", page_icon="🔮", layout="wide")
st.title("🔮 Predicciones de Partidos")

API_URL = os.getenv("API_URL", "http://localhost:8000")

# ── Verificar disponibilidad del API ──────────────────────────────────────────
@st.cache_data(ttl=30)
def _api_ok() -> bool:
    try:
        r = requests.get(f"{API_URL}/matches?limit=1", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

api_available = _api_ok()
if not api_available:
    st.warning(
        f"FastAPI no está disponible en `{API_URL}`. "
        "Las predicciones del modelo no se pueden calcular. "
        "Inicia la API con: `uvicorn api.main:app --port 8000`",
        icon="⚠️",
    )


def _predict(home: str, away: str, n: int = 10_000) -> dict | None:
    if not api_available:
        return None
    try:
        r = requests.post(f"{API_URL}/predict/winner",
                          json={"home": home, "away": away, "n": n}, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ── Cargar partidos ───────────────────────────────────────────────────────────
upcoming = query("""
    SELECT match_id, match_date, stage,
           home_team_name AS home,
           away_team_name AS away
    FROM gold.fact_matches
    WHERE data_source = 'api_football'
      AND home_score IS NULL
      AND home_team_name IS NOT NULL
      AND away_team_name IS NOT NULL
    ORDER BY match_date ASC
    LIMIT 30
""")

played = query("""
    SELECT match_id, match_date, stage,
           home_team_name AS home,
           away_team_name AS away,
           home_score, away_score, result
    FROM gold.fact_matches
    WHERE data_source = 'api_football' AND home_score IS NOT NULL
    ORDER BY match_date DESC
    LIMIT 40
""")

# ── SECCIÓN 1: Próximos partidos ──────────────────────────────────────────────
st.subheader("📅 Próximos partidos")

if upcoming.empty:
    st.info("No hay partidos pendientes — puede que todos los grupos estén terminados.")
else:
    tab_tabla, tab_cards = st.tabs(["📋 Tabla resumen", "📊 Detalle con gráficas"])

    with tab_tabla:
        st.caption("Las probabilidades se calculan con Monte Carlo Poisson usando estadísticas de StatsBomb + Onside Arena.")
        n_sim = st.select_slider("Simulaciones Monte Carlo", [1000, 5000, 10000, 25000, 50000], value=10000)

        # Construir tabla de predicciones
        rows = []
        if api_available:
            prog = st.progress(0, text="Calculando predicciones...")
            for i, (_, row) in enumerate(upcoming.iterrows()):
                prog.progress((i + 1) / len(upcoming), text=f"Prediciendo {row['home']} vs {row['away']}...")
                pred = _predict(row["home"], row["away"], n_sim)
                if pred:
                    if pred["home_win_pct"] >= pred["away_win_pct"] and pred["home_win_pct"] >= pred["draw_pct"]:
                        fav = row["home"]
                        fav_pct = pred["home_win_pct"]
                    elif pred["draw_pct"] >= pred["home_win_pct"] and pred["draw_pct"] >= pred["away_win_pct"]:
                        fav = "Empate"
                        fav_pct = pred["draw_pct"]
                    else:
                        fav = row["away"]
                        fav_pct = pred["away_win_pct"]
                    rows.append({
                        "Fecha": row["match_date"],
                        "Fase": row["stage"],
                        "Local": row["home"],
                        "% L": f"{pred['home_win_pct']:.0f}%",
                        "% E": f"{pred['draw_pct']:.0f}%",
                        "% V": f"{pred['away_win_pct']:.0f}%",
                        "Visitante": row["away"],
                        "Favorito": fav,
                        "_home_pct": pred["home_win_pct"],
                        "_pred": pred,
                        "_home": row["home"],
                        "_away": row["away"],
                    })
            prog.empty()

        if rows:
            df_pred = pd.DataFrame(rows)
            show_cols = ["Fecha", "Fase", "Local", "% L", "% E", "% V", "Visitante", "Favorito"]
            st.dataframe(
                df_pred[show_cols],
                hide_index=True,
                use_container_width=True,
            )
        else:
            # Sin API: mostrar tabla sin probabilidades
            df_show = upcoming.copy()
            df_show["Partido"] = df_show["home"] + " vs " + df_show["away"]
            st.dataframe(
                df_show[["match_date", "stage", "Partido"]].rename(
                    columns={"match_date": "Fecha", "stage": "Fase"}
                ),
                hide_index=True,
                use_container_width=True,
            )

    with tab_cards:
        if not api_available:
            st.info("Inicia la FastAPI para ver las predicciones detalladas.")
        else:
            n_sim2 = st.slider("Simulaciones Monte Carlo", 1000, 50000, 10000, step=1000)
            for _, row in upcoming.iterrows():
                with st.container():
                    col_info, col_chart = st.columns([1, 3])
                    with col_info:
                        st.markdown(f"**{row['match_date']}**  \n{row['stage']}")
                        st.markdown(f"🏠 **{row['home']}**  \n✈️ **{row['away']}**")
                    with col_chart:
                        pred = _predict(row["home"], row["away"], n_sim2)
                        if pred:
                            fig = probability_bars(
                                row["home"], row["away"],
                                pred["home_win_pct"], pred["draw_pct"], pred["away_win_pct"],
                            )
                            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                            with st.expander("Detalles del modelo"):
                                c1, c2, c3 = st.columns(3)
                                c1.metric("λ local", f"{pred.get('lambda_home', 0):.2f}")
                                c2.metric("λ visitante", f"{pred.get('lambda_away', 0):.2f}")
                                c3.metric("Partidos simulados", f"{n_sim2:,}")
                    st.divider()

# ── SECCIÓN 2: Partidos jugados ───────────────────────────────────────────────
st.subheader("✅ Partidos jugados — resultado real vs predicción")

if played.empty:
    st.info("No hay partidos completados aún.")
else:
    result_label = {"home_win": "Local", "draw": "Empate", "away_win": "Visitante"}
    result_emoji = {"home_win": "🏠", "draw": "🤝", "away_win": "✈️"}

    show_n = st.slider("Últimos N partidos", 5, min(40, len(played)), min(10, len(played)))
    tab_resumen, tab_detalle = st.tabs(["📋 Tabla", "📊 Con predicciones"])

    with tab_resumen:
        df_played_show = played.head(show_n).copy()
        df_played_show["Partido"] = df_played_show["home"] + " vs " + df_played_show["away"]
        df_played_show["Marcador"] = (
            df_played_show["home_score"].astype(int).astype(str) + " - " +
            df_played_show["away_score"].astype(int).astype(str)
        )
        df_played_show["Resultado"] = df_played_show["result"].map(
            lambda r: f"{result_emoji.get(r, '')} {result_label.get(r, r)}"
        )
        st.dataframe(
            df_played_show[["match_date", "stage", "Partido", "Marcador", "Resultado"]].rename(
                columns={"match_date": "Fecha", "stage": "Fase"}
            ),
            hide_index=True,
            use_container_width=True,
        )

    with tab_detalle:
        if not api_available:
            st.info("Inicia la FastAPI para ver las predicciones del modelo.")
        else:
            for _, row in played.head(show_n).iterrows():
                col_info, col_chart, col_result = st.columns([1, 3, 1])
                with col_info:
                    st.markdown(f"**{row['match_date']}**  \n{row['stage']}")
                    st.markdown(f"🏠 {row['home']}  \n✈️ {row['away']}")
                with col_chart:
                    pred = _predict(row["home"], row["away"])
                    if pred:
                        fig = probability_bars(
                            row["home"], row["away"],
                            pred["home_win_pct"], pred["draw_pct"], pred["away_win_pct"],
                        )
                        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                with col_result:
                    score = f"{int(row['home_score'])} - {int(row['away_score'])}"
                    st.metric("Resultado", score)
                    st.caption(f"{result_emoji.get(row['result'], '')} {result_label.get(row['result'], row['result'])}")
                st.divider()
