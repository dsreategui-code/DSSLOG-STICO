"""Dashboard de Riesgo y Variabilidad (CORTEX-LM).

Hace visible la inteligencia del cerebro robusto: robustez del plan ante el conjunto de
ambiguedad (nominal vs peor caso), ranking robusto por CVaR e IRI por clasificacion. Solo
LEE la salida de core.planner.planificar (modo robusto/DRO); no recalcula nada.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from components.charts import _base_layout

COLOR_CLASIF = {"Bajo": "#027A48", "Moderado": "#B54708", "Alto": "#B42318",
                "Critico": "#7A271A"}


def es_robusto(res: dict) -> bool:
    elegida = (res.get("recomendacion") or {}).get("elegida")
    return bool(elegida and "por_config" in elegida)


def tabla_por_escenario(elegida: dict) -> pd.DataFrame:
    """OTD y CVaR de la candidata recomendada bajo cada escenario del conjunto de ambiguedad."""
    filas = []
    for cfg, m in elegida.get("por_config", {}).items():
        filas.append({"escenario": cfg, "OTD": round(m["otd"] * 100, 1),
                      "CVaR_min": m["cvar_tardanza_min"], "riesgo": m["pedidos_en_riesgo"]})
    return pd.DataFrame(filas)


def fig_robustez_por_escenario(elegida: dict) -> go.Figure:
    """El grafico clave del DRO: como rinde el plan si el mundo es nominal vs peor de lo esperado."""
    d = tabla_por_escenario(elegida)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d["escenario"], y=d["OTD"], name="OTD (%)",
                         marker_color="#027A48", yaxis="y"))
    fig.add_trace(go.Scatter(x=d["escenario"], y=d["CVaR_min"], name="CVaR tardanza (min)",
                             mode="lines+markers", marker_color="#B42318", yaxis="y2"))
    lay = _base_layout("Robustez del plan ante la incertidumbre (DRO)", height=330)
    piso = min(70.0, float(d["OTD"].min()) - 5) if not d.empty else 70.0
    lay["yaxis"] = dict(title="OTD (%)", range=[piso, 101], gridcolor="#EAECF0")
    lay["yaxis2"] = dict(title="CVaR tardanza (min)", overlaying="y", side="right",
                         showgrid=False)
    fig.update_layout(**lay)
    return fig


def fig_ranking_robusto(res: dict) -> go.Figure:
    """Score robusto (peor caso ajustado por CVaR) por candidata; la recomendada resaltada."""
    evals = res.get("evaluaciones", [])
    reco = res.get("perfil_recomendado")
    d = pd.DataFrame([{"perfil": e["perfil"], "score": e.get("score_robusto", 0.0)}
                     for e in evals]).sort_values("score").reset_index(drop=True)
    colores = ["#027A48" if p == reco else "#98A2B3" for p in d["perfil"]]
    fig = go.Figure(go.Bar(x=d["perfil"], y=d["score"], marker_color=colores,
                           text=[f"{v:.0f}" for v in d["score"]], textposition="outside"))
    fig.update_layout(**_base_layout("Ranking robusto (menor score = mas robusto)", height=330))
    fig.update_yaxes(title="score de riesgo (peor caso)")
    fig.update_xaxes(tickangle=-30)
    return fig


def fig_iri_clasificacion(iri_df: pd.DataFrame) -> go.Figure:
    orden = ["Bajo", "Moderado", "Alto", "Critico"]
    cnt = iri_df["clasificacion"].value_counts().reindex(orden).fillna(0)
    fig = go.Figure(go.Bar(x=orden, y=cnt.values,
                           marker_color=[COLOR_CLASIF[c] for c in orden],
                           text=[int(v) for v in cnt.values], textposition="outside"))
    fig.update_layout(**_base_layout("Pedidos por nivel de riesgo (IRI)", height=300))
    fig.update_yaxes(title="nº pedidos")
    return fig
