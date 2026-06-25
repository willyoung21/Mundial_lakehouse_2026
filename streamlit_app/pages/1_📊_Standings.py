"""Tabla de posiciones en vivo — 12 grupos WC2026."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st
from utils.db import query

st.set_page_config(page_title="Standings | WC2026", page_icon="📊", layout="wide")
st.title("📊 Tabla de Posiciones — WC2026")
st.caption("Top 2 de cada grupo + 8 mejores terceros avanzan al R32")


@st.cache_data(ttl=300)
def load_standings() -> pd.DataFrame:
    return query("""
        WITH all_matches AS (
            SELECT stage,
                   home_team_name AS team,
                   home_score AS gf, away_score AS ga,
                   CASE WHEN home_score > away_score THEN 3
                        WHEN home_score = away_score THEN 1 ELSE 0 END AS pts,
                   CASE WHEN home_score > away_score THEN 1 ELSE 0 END AS wins,
                   CASE WHEN home_score = away_score THEN 1 ELSE 0 END AS draws,
                   CASE WHEN home_score < away_score THEN 1 ELSE 0 END AS losses
            FROM gold.fact_matches
            WHERE data_source = 'api_football'
              AND home_score IS NOT NULL
              AND stage LIKE 'Group%'
            UNION ALL
            SELECT stage,
                   away_team_name,
                   away_score, home_score,
                   CASE WHEN away_score > home_score THEN 3
                        WHEN away_score = home_score THEN 1 ELSE 0 END,
                   CASE WHEN away_score > home_score THEN 1 ELSE 0 END,
                   CASE WHEN away_score = home_score THEN 1 ELSE 0 END,
                   CASE WHEN away_score < home_score THEN 1 ELSE 0 END
            FROM gold.fact_matches
            WHERE data_source = 'api_football'
              AND away_score IS NOT NULL
              AND stage LIKE 'Group%'
        )
        SELECT stage AS grp, team,
               COUNT(*) AS pj,
               SUM(wins) AS g, SUM(draws) AS e, SUM(losses) AS p,
               SUM(gf) AS gf, SUM(ga) AS ga,
               SUM(gf) - SUM(ga) AS dg,
               SUM(pts) AS pts
        FROM all_matches
        GROUP BY stage, team
        ORDER BY stage, pts DESC, dg DESC, gf DESC
    """)


df = load_standings()

if df.empty:
    st.warning("No hay datos de standings disponibles todavía.")
    st.stop()

groups = sorted(df["grp"].unique())

# Calcular umbral del mejor 8° tercero
thirds = []
for grp in groups:
    gdf = df[df["grp"] == grp].reset_index(drop=True)
    if len(gdf) >= 3:
        thirds.append(
            {
                "team": gdf.iloc[2]["team"],
                "pts": gdf.iloc[2]["pts"],
                "dg": gdf.iloc[2]["dg"],
                "gf": gdf.iloc[2]["gf"],
            }
        )
if thirds:
    thirds_sorted = sorted(thirds, key=lambda x: (-x["pts"], -x["dg"], -x["gf"]))
    third_threshold = (
        thirds_sorted[min(7, len(thirds_sorted) - 1)]["pts"] if len(thirds_sorted) >= 8 else 0
    )
else:
    third_threshold = 0


def _status(pos: int, pts: int) -> str:
    if pos <= 2:
        return "🟢 Clasificado"
    if pos == 3 and pts >= third_threshold:
        return "🟡 Posible 3°"
    return "🔴 Eliminado"


def _render_group(gdf: pd.DataFrame):
    rows = []
    for j, row in gdf.reset_index(drop=True).iterrows():
        pos = j + 1
        rows.append(
            {
                "Pos": pos,
                "Equipo": row["team"],
                "PJ": int(row["pj"]),
                "G": int(row["g"]),
                "E": int(row["e"]),
                "P": int(row["p"]),
                "GF": int(row["gf"]),
                "GA": int(row["ga"]),
                "DG": int(row["dg"]),
                "Pts": int(row["pts"]),
                "Estado": _status(pos, int(row["pts"])),
            }
        )
    display = pd.DataFrame(rows)
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=210,
        column_config={
            "Estado": st.column_config.TextColumn("Estado", width="medium"),
            "Equipo": st.column_config.TextColumn("Equipo", width="large"),
        },
    )


# Selector
options = ["Todos los grupos"] + groups
selected = st.selectbox("Selecciona grupo:", options)
display_groups = groups if selected == "Todos los grupos" else [selected]

if selected == "Todos los grupos":
    for row_start in range(0, len(display_groups), 3):
        cols = st.columns(3)
        for i, grp in enumerate(display_groups[row_start : row_start + 3]):
            gdf = df[df["grp"] == grp]
            with cols[i]:
                st.markdown(f"**{grp}**")
                _render_group(gdf)
else:
    grp = display_groups[0]
    gdf = df[df["grp"] == grp]
    _render_group(gdf)

st.divider()
st.caption(
    "🟢 Clasificado (top 2)  |  🟡 Posible mejor 3°  |  🔴 En riesgo  \n"
    "_Cache 5 min — refresca para actualizar_"
)
