"""Dashboards de resultados de la operacion simulada (Gemelo Digital Operativo).

Resumen visual de como termino la jornada del gemelo: entregas por hora (a tiempo vs tardias),
tardanza acumulada por vehiculo e impacto de las incidencias aleatorias. Solo LEE la tabla de
operacion (core.twin_sim.tabla_operacion); no recalcula nada.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from components.charts import _base_layout

VERDE, AMBAR, ROJO = "#027A48", "#B54708", "#B42318"


def fig_entregas_por_hora(df: pd.DataFrame) -> go.Figure:
    """Barras apiladas por hora: entregas a tiempo (verde) vs tardias (ambar)."""
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(**_base_layout("Entregas por hora"))
        return fig
    g = (df.groupby("hora").agg(a_tiempo=("a_tiempo", "sum"), total=("a_tiempo", "size"))
         .reset_index().sort_values("hora"))
    g["tardias"] = g["total"] - g["a_tiempo"]
    horas = [f"{int(h):02d}:00" for h in g["hora"]]
    fig.add_bar(x=horas, y=g["a_tiempo"], name="A tiempo", marker_color=VERDE)
    fig.add_bar(x=horas, y=g["tardias"], name="Tardias", marker_color=AMBAR)
    fig.update_layout(barmode="stack",
                      **_base_layout("Entregas simuladas por hora", height=320))
    fig.update_yaxes(title="nº entregas")
    return fig


def fig_tardanza_por_vehiculo(df: pd.DataFrame) -> go.Figure:
    """Tardanza acumulada (min) por vehiculo; verde si cumple, rojo si acumula retraso."""
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(**_base_layout("Tardanza por vehiculo"))
        return fig
    g = (df.groupby("vehiculo_id").agg(tard=("tardanza_min", "sum"))
         .reset_index().sort_values("tard"))
    col = [ROJO if v > 1e-6 else VERDE for v in g["tard"]]
    fig = go.Figure(go.Bar(x=g["vehiculo_id"], y=g["tard"], marker_color=col,
                           text=[f"{v:.0f}" for v in g["tard"]], textposition="outside"))
    fig.update_layout(**_base_layout("Tardanza acumulada por vehiculo", height=320))
    fig.update_yaxes(title="min de tardanza")
    fig.update_xaxes(tickangle=-30)
    return fig


def fig_otd_otif_camion(tc: pd.DataFrame) -> go.Figure:
    """OTD y OTIF por vehiculo (barras agrupadas, %)."""
    fig = go.Figure()
    if tc is None or tc.empty:
        fig.update_layout(**_base_layout("OTD / OTIF por vehiculo"))
        return fig
    fig.add_bar(x=tc["vehiculo_id"], y=(tc["otd"] * 100).round(1), name="OTD %",
                marker_color="#1570EF")
    fig.add_bar(x=tc["vehiculo_id"], y=(tc["otif"] * 100).round(1), name="OTIF %",
                marker_color="#0D9488")
    fig.update_layout(barmode="group",
                      **_base_layout("OTD / OTIF por vehiculo", height=320))
    fig.update_yaxes(title="%", range=[0, 105])
    return fig


def fig_incidencias_por_tipo(agregados: dict) -> go.Figure:
    """Incidencias por tipo/causa (barras horizontales)."""
    fig = go.Figure()
    pt = (agregados or {}).get("por_tipo")
    if pt is None or pt.empty:
        fig.update_layout(**_base_layout("Incidencias por tipo"))
        return fig
    pt = pt.sort_values("n")
    fig = go.Figure(go.Bar(x=pt["n"], y=pt["descripcion"], orientation="h",
                           marker_color="#B54708",
                           text=pt["n"], textposition="outside"))
    fig.update_layout(**_base_layout("Incidencias por tipo/causa", height=300))
    fig.update_xaxes(title="nº incidencias")
    return fig


def fig_incidencias_por_franja(agregados: dict) -> go.Figure:
    """Incidencias por franja horaria."""
    fig = go.Figure()
    pf = (agregados or {}).get("por_franja")
    if pf is None or pf.empty:
        fig.update_layout(**_base_layout("Incidencias por franja"))
        return fig
    orden = ["mañana", "mediodia", "tarde"]
    pf = pf.set_index("franja").reindex(orden).fillna(0).reset_index()
    fig = go.Figure(go.Bar(x=pf["franja"], y=pf["n"], marker_color="#7F56D9",
                           text=pf["n"].astype(int), textposition="outside"))
    fig.update_layout(**_base_layout("Incidencias por franja horaria", height=300))
    fig.update_yaxes(title="nº incidencias")
    return fig


def fig_variabilidad(var_info: dict) -> go.Figure:
    """Distribucion del OTD entre corridas (menor dispersion = operacion mas consistente)."""
    fig = go.Figure()
    muestras = (var_info or {}).get("muestras") or []
    if not muestras:
        fig.update_layout(**_base_layout("Variabilidad del OTD"))
        return fig
    fig.add_trace(go.Box(y=[m * 100 for m in muestras], name="OTD", boxmean="sd",
                         marker_color="#1570EF"))
    fig.update_layout(**_base_layout(
        f"Variabilidad del OTD ({var_info.get('n', 0)} corridas · σ="
        f"{var_info.get('otd_std', 0) * 100:.1f} pts)", height=320))
    fig.update_yaxes(title="OTD (%)", range=[0, 105])
    return fig


def fig_estado_final(df: pd.DataFrame) -> go.Figure:
    """Dona: reparto final de pedidos a tiempo / tardios / con incidencia."""
    fig = go.Figure()
    if df is None or df.empty:
        fig.update_layout(**_base_layout("Estado final de la jornada"))
        return fig
    con_inc = int(df["incidencia"].sum())
    a_tiempo = int(df["a_tiempo"].sum())
    tardios = int(len(df) - a_tiempo)
    fig = go.Figure(go.Pie(
        labels=["A tiempo", "Tardios", "Con incidencia"],
        values=[a_tiempo, tardios, con_inc], hole=0.55,
        marker_colors=[VERDE, AMBAR, ROJO], sort=False))
    fig.update_traces(textinfo="value")
    fig.update_layout(**_base_layout("Reparto de la jornada", height=320))
    return fig
