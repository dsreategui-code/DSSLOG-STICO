"""Helpers de graficos Plotly con estilo coherente."""
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from config.settings import (
    COLOR_PRIMARY, COLOR_ACCENT, COLOR_SUCCESS, COLOR_WARNING,
    COLOR_DANGER, COLOR_NEUTRAL,
)
from utils.constants import COLOR_ESTADO

PALETTE = ["#0C111D", "#1570EF", "#027A48", "#B54708", "#B42318", "#667085",
           "#7F56D9", "#0E96CC"]


def _base_layout(title: str = "", height: int = 360) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=13, color=COLOR_PRIMARY,
                                          family="Inter, sans-serif")),
        height=height,
        margin=dict(l=24, r=16, t=52, b=44),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font=dict(family="Inter, sans-serif", color=COLOR_PRIMARY, size=11.5),
        xaxis=dict(gridcolor="#EAECF0", zeroline=False, linecolor="#EAECF0"),
        yaxis=dict(gridcolor="#EAECF0", zeroline=False, linecolor="#EAECF0"),
        legend=dict(orientation="h", y=-0.18, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11)),
    )


def chart_otd_evolution(evolucion: pd.DataFrame) -> go.Figure:
    """Linea de evolucion del OTD a lo largo de la jornada."""
    fig = go.Figure()
    if evolucion is None or evolucion.empty:
        fig.update_layout(**_base_layout("Evolucion del OTD durante la operacion"))
        return fig

    if "escenario" in evolucion.columns:
        for i, esc in enumerate(evolucion["escenario"].unique()):
            sub = evolucion[evolucion["escenario"] == esc]
            fig.add_trace(go.Scatter(
                x=sub["hora"], y=sub["otd"],
                mode="lines+markers", name=esc,
                line=dict(color=PALETTE[i % len(PALETTE)], width=2.5),
                marker=dict(size=5),
            ))
    else:
        fig.add_trace(go.Scatter(
            x=evolucion["hora"], y=evolucion["otd"],
            mode="lines+markers", name="OTD",
            line=dict(color=COLOR_ACCENT, width=2.5),
            marker=dict(size=5),
        ))

    layout = _base_layout("Evolucion del OTD durante la operacion", height=380)
    layout["yaxis"] = dict(
        gridcolor="#E2E8F0", zeroline=False,
        title="OTD (%)", range=[0, 105], ticksuffix="%",
    )
    layout["xaxis"] = dict(gridcolor="#E2E8F0", zeroline=False, title="Hora de operacion")
    fig.update_layout(**layout)
    return fig


def chart_scenario_comparison(df_kpis: pd.DataFrame, metric: str = "otd",
                              metric_label: str = "OTD (%)") -> go.Figure:
    fig = go.Figure()
    if df_kpis is None or df_kpis.empty:
        fig.update_layout(**_base_layout(f"Comparacion por {metric_label}"))
        return fig
    fig.add_trace(go.Bar(
        x=df_kpis["escenario"], y=df_kpis[metric],
        marker_color=[PALETTE[i % len(PALETTE)] for i in range(len(df_kpis))],
        text=[f"{v:.1f}" for v in df_kpis[metric]],
        textposition="outside",
    ))
    layout = _base_layout(f"Comparacion de escenarios - {metric_label}")
    layout["yaxis"]["title"] = metric_label
    fig.update_layout(**layout)
    return fig


def chart_boxplot_delivery_times(entregas: pd.DataFrame) -> go.Figure:
    """Boxplot del retraso por vehiculo o escenario."""
    fig = go.Figure()
    if entregas is None or entregas.empty:
        fig.update_layout(**_base_layout("Distribucion de tiempos de entrega"))
        return fig

    group_col = "escenario" if "escenario" in entregas.columns else "vehiculo_id"
    for i, g in enumerate(sorted(entregas[group_col].dropna().unique())):
        sub = entregas[entregas[group_col] == g]
        fig.add_trace(go.Box(
            y=sub["retraso_min"], name=str(g),
            marker_color=PALETTE[i % len(PALETTE)],
            boxmean="sd",
        ))

    layout = _base_layout("Distribucion de retrasos (min)")
    layout["yaxis"]["title"] = "Retraso (min)"
    fig.update_layout(**layout)
    return fig


def chart_vehicle_ranking(df_veh: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df_veh is None or df_veh.empty:
        fig.update_layout(**_base_layout("Ranking de vehiculos por OTD"))
        return fig
    df_sorted = df_veh.sort_values("otd", ascending=True)
    fig.add_trace(go.Bar(
        x=df_sorted["otd"], y=df_sorted["vehiculo_id"],
        orientation="h",
        marker_color=COLOR_ACCENT,
        text=[f"{v:.1f}%" for v in df_sorted["otd"]],
        textposition="outside",
    ))
    layout = _base_layout("Ranking de vehiculos por OTD")
    layout["xaxis"] = dict(gridcolor="#E2E8F0", title="OTD (%)", range=[0, 105])
    fig.update_layout(**layout)
    return fig


def chart_capacity_usage(df_veh: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df_veh is None or df_veh.empty:
        fig.update_layout(**_base_layout("Capacidad utilizada por vehiculo"))
        return fig
    fig.add_trace(go.Bar(
        x=df_veh["vehiculo_id"], y=df_veh["uso_capacidad_pct"],
        marker_color=COLOR_PRIMARY,
        text=[f"{v:.0f}%" for v in df_veh["uso_capacidad_pct"]],
        textposition="outside",
    ))
    layout = _base_layout("Capacidad utilizada por vehiculo")
    layout["yaxis"] = dict(gridcolor="#E2E8F0", title="Uso (%)", range=[0, 110])
    fig.update_layout(**layout)
    return fig


def chart_orders_per_vehicle(df_veh: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df_veh is None or df_veh.empty:
        fig.update_layout(**_base_layout("Pedidos por vehiculo"))
        return fig
    fig.add_trace(go.Bar(
        x=df_veh["vehiculo_id"], y=df_veh["pedidos_asignados"],
        marker_color=COLOR_ACCENT,
        text=df_veh["pedidos_asignados"].astype(int),
        textposition="outside",
    ))
    layout = _base_layout("Pedidos por vehiculo")
    layout["yaxis"]["title"] = "Pedidos asignados"
    fig.update_layout(**layout)
    return fig


def chart_alerts_by_type(alertas: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if alertas is None or alertas.empty:
        fig.update_layout(**_base_layout("Alertas por tipo"))
        return fig
    by_tipo = alertas.groupby("tipo").size().reset_index(name="cantidad")
    fig.add_trace(go.Bar(
        x=by_tipo["tipo"], y=by_tipo["cantidad"],
        marker_color=COLOR_WARNING,
        text=by_tipo["cantidad"], textposition="outside",
    ))
    layout = _base_layout("Alertas por tipo")
    layout["yaxis"]["title"] = "Cantidad"
    fig.update_layout(**layout)
    return fig


def chart_replanificaciones(stats: dict) -> go.Figure:
    fig = go.Figure()
    if not stats:
        fig.update_layout(**_base_layout("Replanificaciones"))
        return fig
    cat = ["Sugeridas", "Aprobadas", "Rechazadas"]
    vals = [stats.get("sugeridas", 0), stats.get("aprobadas", 0), stats.get("rechazadas", 0)]
    colors = [COLOR_NEUTRAL, COLOR_SUCCESS, COLOR_DANGER]
    fig.add_trace(go.Bar(x=cat, y=vals, marker_color=colors,
                        text=vals, textposition="outside"))
    layout = _base_layout("Replanificaciones intravehiculo")
    layout["yaxis"]["title"] = "Cantidad"
    fig.update_layout(**layout)
    return fig


def chart_estados_distribucion(entregas: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if entregas is None or entregas.empty:
        fig.update_layout(**_base_layout("Distribucion de estados"))
        return fig
    by_estado = entregas.groupby("estado").size().reset_index(name="cantidad")
    by_estado["color"] = by_estado["estado"].map(COLOR_ESTADO).fillna(COLOR_NEUTRAL)
    fig.add_trace(go.Bar(
        x=by_estado["estado"], y=by_estado["cantidad"],
        marker_color=by_estado["color"].tolist(),
        text=by_estado["cantidad"], textposition="outside",
    ))
    layout = _base_layout("Distribucion de estados de entrega")
    layout["yaxis"]["title"] = "Pedidos"
    fig.update_layout(**layout)
    return fig


def chart_variability_otd(iteraciones: pd.DataFrame) -> go.Figure:
    """Boxplot del OTD por escenario sobre iteraciones Monte Carlo."""
    fig = go.Figure()
    if iteraciones is None or iteraciones.empty:
        fig.update_layout(**_base_layout("Variabilidad del OTD por escenario"))
        return fig
    for i, esc in enumerate(sorted(iteraciones["escenario"].unique())):
        sub = iteraciones[iteraciones["escenario"] == esc]
        fig.add_trace(go.Box(
            y=sub["otd"], name=esc,
            marker_color=PALETTE[i % len(PALETTE)],
            boxmean="sd",
        ))
    layout = _base_layout("Variabilidad del OTD (Monte Carlo)")
    layout["yaxis"] = dict(gridcolor="#E2E8F0", title="OTD (%)", range=[0, 105])
    fig.update_layout(**layout)
    return fig
