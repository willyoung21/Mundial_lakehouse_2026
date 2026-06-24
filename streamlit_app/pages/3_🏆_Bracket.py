"""Simulador de bracket WC2026 — ingresa marcadores para simular la fase de grupos y armar el cuadro."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import requests
import pandas as pd
import streamlit as st

from utils.db import query
from utils.charts import probability_bars

st.set_page_config(page_title="Bracket | WC2026", page_icon="🏆", layout="wide")
st.title("🏆 Simulador de Bracket — WC2026")
st.caption(
    "Los partidos jugados muestran el resultado real. Para los pendientes, ingresa marcadores para simular "
    "quién avanza. Luego ve a la pestaña **Bracket** para simular las eliminatorias."
)

API_URL = os.getenv("API_URL", "http://localhost:8000")

# ── Session state ─────────────────────────────────────────────────────────────
if "sim_scores" not in st.session_state:
    st.session_state.sim_scores = {}   # {str(match_id): (home, away)}
if "bracket_picks" not in st.session_state:
    st.session_state.bracket_picks = {}  # {match_key: winner_team}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_score(match) -> tuple[int, int] | None:
    mid = str(match["match_id"])
    if pd.notna(match["home_score"]):
        return int(match["home_score"]), int(match["away_score"])
    if mid in st.session_state.sim_scores:
        return st.session_state.sim_scores[mid]
    return None


def _compute_standings(group_matches: pd.DataFrame) -> pd.DataFrame:
    all_teams = sorted(set(group_matches["home"].tolist() + group_matches["away"].tolist()))
    records = []
    for _, m in group_matches.iterrows():
        score = _get_score(m)
        if score is None:
            continue
        hs, as_ = score
        home, away = m["home"], m["away"]
        hp = 3 if hs > as_ else (1 if hs == as_ else 0)
        ap = 3 if as_ > hs else (1 if as_ == hs else 0)
        records.append({"team": home, "gf": hs, "ga": as_, "pts": hp,
                         "wins": 1 if hp == 3 else 0, "draws": 1 if hp == 1 else 0,
                         "losses": 1 if hp == 0 else 0, "pj": 1})
        records.append({"team": away, "gf": as_, "ga": hs, "pts": ap,
                         "wins": 1 if ap == 3 else 0, "draws": 1 if ap == 1 else 0,
                         "losses": 1 if ap == 0 else 0, "pj": 1})

    if not records:
        return pd.DataFrame({"team": all_teams, "pj": 0, "wins": 0, "draws": 0,
                              "losses": 0, "gf": 0, "ga": 0, "dg": 0, "pts": 0})

    df = pd.DataFrame(records).groupby("team", as_index=False).sum()
    df["dg"] = df["gf"] - df["ga"]
    registered = set(df["team"])
    extras = [{"team": t, "pj": 0, "wins": 0, "draws": 0, "losses": 0,
                "gf": 0, "ga": 0, "dg": 0, "pts": 0}
              for t in all_teams if t not in registered]
    if extras:
        df = pd.concat([df, pd.DataFrame(extras)], ignore_index=True)
    return df.sort_values(["pts", "dg", "gf"], ascending=False).reset_index(drop=True)


def _predict(home: str, away: str) -> dict | None:
    if not home or not away or "?" in (home, away):
        return None
    try:
        r = requests.post(f"{API_URL}/predict/winner",
                          json={"home": home, "away": away}, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ── Cargar partidos de grupo ───────────────────────────────────────────────────
@st.cache_data(ttl=120)
def load_group_matches() -> pd.DataFrame:
    return query("""
        SELECT match_id, match_date, stage AS grp,
               home_team_name AS home,
               away_team_name AS away,
               home_score, away_score
        FROM gold.fact_matches
        WHERE data_source = 'api_football' AND stage LIKE 'Group%'
        ORDER BY stage, match_date ASC, match_id ASC
    """)


df_all = load_group_matches()

if df_all.empty:
    st.error("No hay datos de la fase de grupos. Verifica la ingesta.")
    st.stop()

groups = sorted(df_all["grp"].unique())
qualified: dict[str, list[str]] = {}

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_groups, tab_bracket = st.tabs(["⚽ Fase de Grupos", "🏆 Bracket Eliminatorio"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: FASE DE GRUPOS
# ─────────────────────────────────────────────────────────────────────────────
with tab_groups:
    st.subheader("Resultados por grupo")
    st.caption(
        "✅ = resultado real. ⏳ = partido pendiente: ingresa L (local) y V (visitante) para simular."
    )

    cols_grid = st.columns(3)

    for gi, grp in enumerate(groups):
        gdf = df_all[df_all["grp"] == grp].reset_index(drop=True)

        with cols_grid[gi % 3]:
            st.markdown(f"### {grp}")

            # Partidos
            for _, match in gdf.iterrows():
                mid = str(match["match_id"])
                home, away = match["home"], match["away"]

                if pd.notna(match["home_score"]):
                    hs, as_ = int(match["home_score"]), int(match["away_score"])
                    st.markdown(f"✅ **{home}** {hs}–{as_} **{away}**")
                else:
                    prev = st.session_state.sim_scores.get(mid, (0, 0))
                    c1, c2, c3 = st.columns([4, 1, 1])
                    c1.caption(f"⏳ {home} vs {away}")
                    new_h = c2.number_input("L", 0, 20, int(prev[0]),
                                            key=f"h_{mid}", label_visibility="collapsed")
                    new_a = c3.number_input("V", 0, 20, int(prev[1]),
                                            key=f"a_{mid}", label_visibility="collapsed")
                    st.session_state.sim_scores[mid] = (int(new_h), int(new_a))

            # Posiciones (recalcula en vivo)
            standings = _compute_standings(gdf)
            qualified[grp] = standings["team"].tolist()

            st.markdown("---")
            pos_icons = ["🥇", "🥈", "🥉", "4️⃣"]
            for j, row in standings.iterrows():
                icon = pos_icons[j] if j < 4 else "  "
                pj, pts, gf, ga, dg = int(row["pj"]), int(row["pts"]), int(row["gf"]), int(row["ga"]), int(row["dg"])
                st.markdown(f"{icon} **{row['team']}** &nbsp; {pts}pts &nbsp; {gf}–{ga} (DG {dg:+d})")
            st.markdown("")

    # Resumen clasificados
    st.divider()
    st.subheader("Clasificados al bracket eliminatorio")

    thirds_data = []
    for grp in groups:
        gdf = df_all[df_all["grp"] == grp]
        st_df = _compute_standings(gdf)
        if len(st_df) >= 3:
            row = st_df.iloc[2].to_dict()
            row["grp"] = grp
            thirds_data.append(row)

    if thirds_data:
        thirds_df = pd.DataFrame(thirds_data).sort_values(["pts", "dg", "gf"], ascending=False).reset_index(drop=True)
        best_thirds = thirds_df["team"].tolist()[:8]
    else:
        best_thirds = []
    while len(best_thirds) < 8:
        best_thirds.append("?")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Ganadores y subcampeones (24 equipos):**")
        rows_cl = [{"Grupo": grp, "1°": qualified.get(grp, ["?"])[0],
                    "2°": qualified.get(grp, ["?", "?"])[1] if len(qualified.get(grp, [])) > 1 else "?"}
                   for grp in sorted(qualified.keys())]
        st.dataframe(pd.DataFrame(rows_cl), hide_index=True, use_container_width=True)
    with col_r:
        st.markdown("**8 mejores terceros:**")
        rows_t3 = [{"#": i+1, "Equipo": t} for i, t in enumerate(best_thirds) if t != "?"]
        if rows_t3:
            st.dataframe(pd.DataFrame(rows_t3), hide_index=True, use_container_width=True)
        else:
            st.caption("Pendiente de resultados.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: BRACKET ELIMINATORIO
# ─────────────────────────────────────────────────────────────────────────────
with tab_bracket:
    # Recalcular qualified con datos actuales de session_state
    for grp in groups:
        gdf = df_all[df_all["grp"] == grp]
        st_df = _compute_standings(gdf)
        qualified[grp] = st_df["team"].tolist()

    thirds_data2 = []
    for grp in groups:
        gdf = df_all[df_all["grp"] == grp]
        st_df = _compute_standings(gdf)
        if len(st_df) >= 3:
            row = st_df.iloc[2].to_dict()
            row["grp"] = grp
            thirds_data2.append(row)
    if thirds_data2:
        best_thirds2 = pd.DataFrame(thirds_data2).sort_values(["pts", "dg", "gf"], ascending=False)["team"].tolist()[:8]
    else:
        best_thirds2 = []
    while len(best_thirds2) < 8:
        best_thirds2.append("?")

    def _q(grp: str, pos: int) -> str:
        t = qualified.get(grp, [])
        return t[pos] if len(t) > pos else "?"

    expected_groups = [f"Group {c}" for c in "ABCDEFGHIJKL"]
    G = {c: expected_groups[i] for i, c in enumerate("ABCDEFGHIJKL")}

    R32_PAIRS = [
        (_q(G["A"], 0), _q(G["B"], 1)), (_q(G["B"], 0), _q(G["A"], 1)),
        (_q(G["C"], 0), _q(G["D"], 1)), (_q(G["D"], 0), _q(G["C"], 1)),
        (_q(G["E"], 0), _q(G["F"], 1)), (_q(G["F"], 0), _q(G["E"], 1)),
        (_q(G["G"], 0), _q(G["H"], 1)), (_q(G["H"], 0), _q(G["G"], 1)),
        (_q(G["I"], 0), _q(G["J"], 1)), (_q(G["J"], 0), _q(G["I"], 1)),
        (_q(G["K"], 0), _q(G["L"], 1)), (_q(G["L"], 0), _q(G["K"], 1)),
        (best_thirds2[0], best_thirds2[1]), (best_thirds2[2], best_thirds2[3]),
        (best_thirds2[4], best_thirds2[5]), (best_thirds2[6], best_thirds2[7]),
    ]

    def _match_card(round_key: str, home: str, away: str) -> str:
        """Muestra probabilidades y radio para elegir ganador. Retorna el ganador."""
        st.markdown(f"**{home}** vs **{away}**")
        pred = _predict(home, away)
        if pred:
            fig = probability_bars(home, away,
                                   pred["home_win_pct"], pred["draw_pct"], pred["away_win_pct"],
                                   height=85)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            default = home if pred["home_win_pct"] >= pred["away_win_pct"] else away
        else:
            st.caption("API no disponible")
            default = home

        current = st.session_state.bracket_picks.get(round_key, default)
        opts = [home, away] if home != "?" and away != "?" else [home, away]
        idx = opts.index(current) if current in opts else 0
        winner = st.radio("Avanza:", opts, index=idx,
                          key=f"pick_{round_key}", horizontal=True,
                          label_visibility="collapsed")
        st.session_state.bracket_picks[round_key] = winner
        st.success(f"→ {winner}")
        return winner

    # ── R32 ──────────────────────────────────────────────────────────────────
    st.subheader("Dieciseisavos de Final (R32) — 16 partidos")
    st.caption("Elige quién avanza en cada partido. Las probabilidades vienen del modelo Poisson.")

    r32_winners = []
    r32_cols = st.columns(4)
    for i, (home, away) in enumerate(R32_PAIRS):
        with r32_cols[i % 4]:
            st.markdown(f"**Partido {i+1}**")
            w = _match_card(f"r32_{i}", home, away)
            r32_winners.append(w)
            st.markdown("---")

    # ── R16 ──────────────────────────────────────────────────────────────────
    st.subheader("Octavos de Final (R16)")
    r16_pairs = [(r32_winners[i], r32_winners[i+1]) for i in range(0, 16, 2)]
    r16_winners = []
    r16_cols = st.columns(4)
    for i, (home, away) in enumerate(r16_pairs):
        with r16_cols[i % 4]:
            st.markdown(f"**Octavo {i+1}**")
            w = _match_card(f"r16_{i}", home, away)
            r16_winners.append(w)
            st.markdown("---")

    # ── Cuartos ───────────────────────────────────────────────────────────────
    st.subheader("Cuartos de Final")
    qf_pairs = [(r16_winners[i], r16_winners[i+1]) for i in range(0, 8, 2)]
    qf_winners = []
    qf_cols = st.columns(4)
    for i, (home, away) in enumerate(qf_pairs):
        with qf_cols[i % 4]:
            st.markdown(f"**Cuarto {i+1}**")
            w = _match_card(f"qf_{i}", home, away)
            qf_winners.append(w)
            st.markdown("---")

    # ── Semifinales ───────────────────────────────────────────────────────────
    st.subheader("Semifinales")
    sf_pairs = [(qf_winners[i], qf_winners[i+1]) for i in range(0, 4, 2)]
    sf_winners = []
    sf_cols = st.columns(2)
    for i, (home, away) in enumerate(sf_pairs):
        with sf_cols[i]:
            st.markdown(f"**Semifinal {i+1}**")
            w = _match_card(f"sf_{i}", home, away)
            sf_winners.append(w)
            st.markdown("---")

    # ── Final ─────────────────────────────────────────────────────────────────
    st.subheader("🏆 Gran Final")
    if len(sf_winners) >= 2:
        col_fin, col_champ = st.columns([3, 1])
        with col_fin:
            champion = _match_card("final", sf_winners[0], sf_winners[1])
        with col_champ:
            st.metric("Campeón predicho", champion)
            pred_fin = _predict(sf_winners[0], sf_winners[1])
            if pred_fin:
                pct = pred_fin["home_win_pct"] if champion == sf_winners[0] else pred_fin["away_win_pct"]
                st.metric("Probabilidad de ganar", f"{pct:.1f}%")

    st.divider()
    if st.button("Reiniciar todos los picks", type="secondary"):
        st.session_state.bracket_picks = {}
        st.session_state.sim_scores = {}
        st.rerun()
