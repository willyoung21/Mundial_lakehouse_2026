"""Funciones de visualización Plotly reutilizables para el dashboard."""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

CONF_COLORS = {
    "UEFA": "#003399",
    "CONMEBOL": "#FFD700",
    "CONCACAF": "#CC0000",
    "CAF": "#009900",
    "AFC": "#FF6600",
    "OFC": "#9900CC",
}


def probability_bars(
    home: str,
    away: str,
    home_pct: float,
    draw_pct: float,
    away_pct: float,
    height: int = 120,
) -> go.Figure:
    """Barras horizontales win/draw/loss para un partido."""
    fig = go.Figure()

    values = [home_pct, draw_pct, away_pct]
    labels = [f"🏠 {home}", "Empate", f"✈️ {away}"]
    colors = ["#2196F3", "#9E9E9E", "#F44336"]

    for val, label, color in zip(values, labels, colors):
        fig.add_trace(go.Bar(
            x=[val], y=[label],
            orientation="h",
            text=[f"{val:.1f}%"],
            textposition="inside",
            insidetextanchor="middle",
            marker_color=color,
            showlegend=False,
        ))

    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(range=[0, 100], showticklabels=False, showgrid=False),
        yaxis=dict(showgrid=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        barmode="stack",
        font=dict(size=13),
    )
    return fig


def xg_scatter(df: pd.DataFrame) -> go.Figure:
    """Scatter 4-cuadrantes: xG ataque (X) vs goles concedidos/partido (Y).

    Cuadrantes: abajo-derecha = elite (buen ataque, buena defensa).
    """
    if df.empty:
        return go.Figure()

    mean_x = df["avg_xg_per_match"].mean()
    mean_y = df["ga_per_match"].mean()

    conf_col = df["confederation"] if "confederation" in df.columns else ["UEFA"] * len(df)
    colors = [CONF_COLORS.get(c, "#888888") for c in conf_col]

    fig = go.Figure()

    for conf in df["confederation"].unique() if "confederation" in df.columns else ["UEFA"]:
        mask = df["confederation"] == conf
        sub = df[mask]
        fig.add_trace(go.Scatter(
            x=sub["avg_xg_per_match"],
            y=sub["ga_per_match"],
            mode="markers+text",
            name=conf,
            text=sub["team_canonical"],
            textposition="top center",
            textfont=dict(size=9),
            marker=dict(size=10, color=CONF_COLORS.get(conf, "#888888"), line=dict(width=1, color="white")),
            hovertemplate="<b>%{text}</b><br>xG/partido: %{x:.2f}<br>GA/partido: %{y:.2f}<extra></extra>",
        ))

    fig.add_hline(y=mean_y, line_dash="dash", line_color="gray", opacity=0.5)
    fig.add_vline(x=mean_x, line_dash="dash", line_color="gray", opacity=0.5)

    # Etiquetas de cuadrantes
    for text, x, y, ax in [
        ("⭐ Elite", mean_x + 0.05, mean_y - 0.05, "left"),
        ("⚡ Ofensivo", mean_x + 0.05, mean_y + 0.05, "left"),
        ("🛡️ Defensivo", mean_x - 0.05, mean_y - 0.05, "right"),
        ("⚠️ En riesgo", mean_x - 0.05, mean_y + 0.05, "right"),
    ]:
        fig.add_annotation(x=x, y=y, text=text, showarrow=False,
                           font=dict(size=10, color="gray"), xanchor=ax)

    fig.update_layout(
        title="Ataque vs Defensa por Equipo (xG)",
        xaxis_title="xG ofensivo / partido (↑ más ataque)",
        yaxis_title="Goles concedidos / partido (↓ mejor defensa)",
        height=520,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="closest",
    )
    return fig


def champion_odds_bars(df: pd.DataFrame, n: int = 20) -> go.Figure:
    """Barras horizontales de probabilidades de campeón."""
    if df.empty:
        return go.Figure()

    top = df.head(n).copy()
    top = top.sort_values("champion_pct", ascending=True)

    colors = [CONF_COLORS.get(c, "#888888") for c in top.get("confederation", ["UEFA"] * len(top))]

    fig = go.Figure(go.Bar(
        x=top["champion_pct"],
        y=top["team_canonical"].fillna(top["team_name"]),
        orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in top["champion_pct"]],
        textposition="outside",
        customdata=top[["reach_final_pct", "reach_semi_pct", "reach_qf_pct"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Campeón: %{x:.1f}%<br>"
            "Final: %{customdata[0]:.1f}%<br>"
            "Semifinal: %{customdata[1]:.1f}%<br>"
            "Cuartos: %{customdata[2]:.1f}%<extra></extra>"
        ),
    ))

    fig.update_layout(
        title="Probabilidades de Campeón — Onside Arena",
        xaxis_title="Probabilidad (%)",
        height=max(400, n * 22),
        margin=dict(l=10, r=80, t=40, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def results_donut(wc2026_counts: dict, historical_pcts: dict | None = None) -> go.Figure:
    """Donut chart comparando distribución de resultados WC2026 vs histórico."""
    labels = ["Victoria local", "Empate", "Victoria visitante"]
    keys   = ["home_win", "draw", "away_win"]
    colors = ["#2196F3", "#9E9E9E", "#F44336"]

    vals = [wc2026_counts.get(k, 0) for k in keys]
    total = sum(vals) or 1

    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=labels,
        values=vals,
        hole=0.45,
        marker_colors=colors,
        textinfo="label+percent",
        name="WC2026",
        domain=dict(x=[0, 0.48]),
        hovertemplate="%{label}: %{value} partidos (%{percent})<extra></extra>",
    ))

    if historical_pcts:
        hist_vals = [historical_pcts.get(k, 0) for k in keys]
        fig.add_trace(go.Pie(
            labels=labels,
            values=hist_vals,
            hole=0.45,
            marker_colors=colors,
            textinfo="label+percent",
            name="Histórico WC",
            domain=dict(x=[0.52, 1.0]),
            hovertemplate="%{label}: %{percent}<extra>Histórico WC</extra>",
        ))
        fig.update_layout(
            annotations=[
                dict(text="WC2026", x=0.18, y=0.5, font_size=14, showarrow=False),
                dict(text="Histórico", x=0.82, y=0.5, font_size=14, showarrow=False),
            ]
        )
    else:
        fig.update_layout(
            annotations=[dict(text="WC2026", x=0.5, y=0.5, font_size=14, showarrow=False)]
        )

    fig.update_layout(height=380, title="Distribución de Resultados")
    return fig
