"""Fase 9 - Vista de analisis del benchmark SVRPBench (TWCVRP fiel).

Lee los resultados de `data_benchmark/svrpbench_results/final_twcvrp/` (generados por la
Fase 8b) y los presenta de forma interpretada: ranking, costo por modelo y por tamano,
calidad de servicio (OTD/CVR), robustez y el efecto de las mejoras del DSS.

Solo LEE archivos del benchmark; no ejecuta solvers ni toca el flujo operativo del DSS.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.cards import kpi_row, info_card
from components.charts import _base_layout, PALETTE
from utils.constants import VISTA_HOME

RESULTS_DIR = Path(__file__).resolve().parents[1] / \
    "data_benchmark" / "svrpbench_results" / "final_twcvrp"

# Etiquetas legibles por modelo.
_NOMBRES = {
    "DSS": "DSS (propuesto)",
    "or-tools-tw": "OR-Tools TWCVRP",
    "or-tools": "OR-Tools (solo cap.)",
    "nn2opt": "NN + 2-opt",
}
# Costo del DSS ANTES de las mejoras (corrida fiel previa), para el antes/despues.
_DSS_ANTES_POR_TAMANO = {50: 14922.9, 100: 39294.1, 200: 95462.8}


@st.cache_data(show_spinner=False)
def _load(nombre: str):
    f = RESULTS_DIR / nombre
    if not f.exists():
        return None
    return pd.read_csv(f)


def _color_modelo(modelo: str) -> str:
    orden = ["DSS", "or-tools-tw", "nn2opt", "or-tools"]
    paleta = {"DSS": "#027A48", "or-tools-tw": "#1570EF",
              "nn2opt": "#B54708", "or-tools": "#667085"}
    return paleta.get(modelo, PALETTE[orden.index(modelo) % len(PALETTE)]
                      if modelo in orden else PALETTE[0])


def _fig_costo_por_modelo(by_model: pd.DataFrame) -> go.Figure:
    d = by_model.sort_values("costo_prom")
    fig = go.Figure(go.Bar(
        x=[_NOMBRES.get(m, m) for m in d["model_name"]],
        y=d["costo_prom"],
        marker_color=[_color_modelo(m) for m in d["model_name"]],
        text=[f"{v:,.0f}" for v in d["costo_prom"]], textposition="outside",
    ))
    fig.update_layout(**_base_layout("Costo operativo promedio (menor es mejor)", height=340))
    fig.update_yaxes(title="costo (min)")
    return fig


def _fig_costo_por_tamano(by_ms: pd.DataFrame) -> go.Figure:
    tamanos = sorted(by_ms["instance_size"].unique())
    fig = go.Figure()
    # Baseline ingenua = el mas barato entre or-tools y nn2opt por tamano.
    naive = (by_ms[by_ms["model_name"].isin(["or-tools", "nn2opt"])]
             .groupby("instance_size")["costo_prom"].min())
    series = [
        ("DSS (propuesto)", "#027A48", None,
         [by_ms[(by_ms.model_name == "DSS") & (by_ms.instance_size == t)]["costo_prom"].iloc[0]
          for t in tamanos]),
        ("OR-Tools TWCVRP", "#1570EF", "dash",
         [by_ms[(by_ms.model_name == "or-tools-tw") & (by_ms.instance_size == t)]["costo_prom"].iloc[0]
          for t in tamanos]),
        ("Heuristica ingenua", "#B54708", "dot", [naive[t] for t in tamanos]),
    ]
    for nombre, color, dash, vals in series:
        fig.add_trace(go.Scatter(
            x=[str(t) for t in tamanos], y=vals, mode="lines+markers", name=nombre,
            line=dict(color=color, width=2.5, dash=dash)))
    fig.update_layout(**_base_layout("Costo por tamano de instancia", height=360))
    fig.update_xaxes(title="clientes por instancia")
    fig.update_yaxes(title="costo (min)")
    return fig


def _fig_antes_despues(by_ms: pd.DataFrame) -> go.Figure:
    tamanos = sorted(by_ms["instance_size"].unique())
    ahora = [by_ms[(by_ms.model_name == "DSS") & (by_ms.instance_size == t)]["costo_prom"].iloc[0]
             for t in tamanos]
    antes = [_DSS_ANTES_POR_TAMANO.get(t) for t in tamanos]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[str(t) for t in tamanos], y=antes, name="DSS antes",
                         marker_color="#D0D5DD",
                         text=[f"{v:,.0f}" for v in antes], textposition="outside"))
    fig.add_trace(go.Bar(x=[str(t) for t in tamanos], y=ahora, name="DSS ahora",
                         marker_color="#027A48",
                         text=[f"{v:,.0f}" for v in ahora], textposition="outside"))
    fig.update_layout(**_base_layout("Efecto de las mejoras al DSS", height=340), barmode="group")
    fig.update_xaxes(title="clientes por instancia")
    fig.update_yaxes(title="costo (min)")
    return fig


def _fig_calidad(by_model: pd.DataFrame) -> go.Figure:
    d = by_model.copy()
    d["OTD %"] = (d["otd_benchmark"] * 100).round(1)
    fig = go.Figure(go.Bar(
        x=[_NOMBRES.get(m, m) for m in d["model_name"]], y=d["OTD %"],
        marker_color=[_color_modelo(m) for m in d["model_name"]],
        text=[f"{v:.1f}%" for v in d["OTD %"]], textposition="outside"))
    fig.update_layout(**_base_layout("Entregas a tiempo (OTD)", height=320))
    fig.update_yaxes(title="OTD (%)", range=[90, 101])
    return fig


def render():
    render_view_title(
        "Benchmark SVRPBench - analisis de resultados",
        "Comparacion del DSS contra solvers de referencia sobre el benchmark academico "
        "SVRPBench (TWCVRP estocastico, single-depot, multi-vehiculo). Reconstruccion fiel "
        "al paper: capacidad real, ventanas por cliente y evaluador estocastico oficial.",
        eyebrow="Fase 9  /  Validacion externa",
    )

    by_model = _load("twcvrp_results_by_model.csv")
    by_ms = _load("twcvrp_results_by_model_size.csv")
    ranking = _load("twcvrp_model_ranking.csv")
    rep = _load("twcvrp_dss_reparaciones.csv")

    if by_model is None or ranking is None:
        st.warning(
            "No se encontraron los resultados del benchmark en "
            "`data_benchmark/svrpbench_results/final_twcvrp/`. "
            "Ejecuta `run_final_fase8b.py` para generarlos."
        )
        render_divider()
        if st.button("Volver al inicio", key="bench_back_empty"):
            st.session_state.vista = VISTA_HOME
            st.rerun()
        render_footer()
        return

    dss = by_model[by_model["model_name"] == "DSS"].iloc[0]
    pos_dss = int(ranking[ranking["model_name"] == "DSS"]["rank"].iloc[0])
    n_modelos = len(ranking)
    mejor = ranking.iloc[0]["model_name"]

    kpi_row([
        {"label": "Posicion del DSS", "value": f"{pos_dss}o de {n_modelos}",
         "helptext": "Ranking por costo, factibilidad, CVR, OTD y runtime"},
        {"label": "Costo DSS", "value": f"{dss['costo_prom']:,.0f}",
         "helptext": "Tiempo operativo promedio bajo escenarios estocasticos (min)"},
        {"label": "OTD DSS", "value": f"{dss['otd_benchmark'] * 100:.1f}%",
         "helptext": "Entregas dentro de ventana"},
        {"label": "Robustez DSS", "value": f"{dss['robustness']:.2f}",
         "helptext": "Variabilidad del costo entre escenarios (menor es mejor)"},
    ])

    st.write("")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.plotly_chart(_fig_costo_por_modelo(by_model), use_container_width=True,
                        config={"displayModeBar": False})
    with c2:
        if by_ms is not None:
            st.plotly_chart(_fig_costo_por_tamano(by_ms), use_container_width=True,
                            config={"displayModeBar": False})

    c3, c4 = st.columns(2, gap="large")
    with c3:
        if by_ms is not None:
            st.plotly_chart(_fig_antes_despues(by_ms), use_container_width=True,
                            config={"displayModeBar": False})
    with c4:
        st.plotly_chart(_fig_calidad(by_model), use_container_width=True,
                        config={"displayModeBar": False})

    render_divider()
    st.markdown("#### Ranking de modelos")
    rk = ranking[["rank", "model_name", "costo_prom", "feasibility",
                  "constraint_violation_rate", "otd_benchmark", "runtime_seconds"]].copy()
    rk["model_name"] = rk["model_name"].map(lambda m: _NOMBRES.get(m, m))
    rk["otd_benchmark"] = (rk["otd_benchmark"] * 100).round(1)
    rk.columns = ["#", "Modelo", "Costo prom.", "Factibilidad", "CVR (%)",
                  "OTD (%)", "Runtime (s)"]
    st.dataframe(rk, use_container_width=True, hide_index=True)

    render_divider()
    col_a, col_b, col_c = st.columns(3, gap="medium")
    with col_a:
        info_card(
            "Hallazgo principal",
            "Con un benchmark TWCVRP fiel, el DSS queda empatado con el mejor OR-Tools "
            "TWCVRP y supera ~31-40% en costo a las heuristicas ingenuas, con la mejor "
            "robustez. A 50-100 clientes (ultima milla real) esta estadisticamente empatado.",
            eyebrow="Conclusion",
        )
    with col_b:
        info_card(
            "Mejora clave al DSS",
            "Desacoplar la espera de la tolerancia de ventana en el optimizador CVRPTW: "
            "el vehiculo ahora puede esperar a que abra una ventana. Bajo el costo del DSS "
            "~34% y casi elimino los clientes no servidos.",
            eyebrow="Que cambio",
        )
    with col_c:
        n_rep = int(rep["n_reparadas_dedicadas"].sum()) if rep is not None else 0
        info_card(
            "Cobertura y honestidad",
            f"Todos los modelos sirven al 100% de los clientes. Los {n_rep} casos que el DSS "
            "no encaja en ventana estricta se cubren con viajes dedicados, con su costo "
            "cargado y reportado aparte. Mismo evaluador del paper para todos.",
            eyebrow="Metodologia",
        )

    render_divider()
    if st.button("Volver al inicio", key="bench_back"):
        st.session_state.vista = VISTA_HOME
        st.rerun()
    render_footer()
