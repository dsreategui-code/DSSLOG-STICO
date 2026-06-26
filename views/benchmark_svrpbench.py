"""Fase 9 - Vista de analisis del benchmark SVRPBench (TWCVRP fiel).

Lee los resultados de `data_benchmark/svrpbench_results/final_twcvrp/` (generados por la
Fase 8b) y los presenta de forma interpretada: perfil de rendimiento en TODOS los criterios
(radar), tabla comparativa completa, detalle por criterio, ranking y conclusiones.

Solo LEE archivos del benchmark; no ejecuta solvers ni toca el flujo operativo del DSS.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.cards import kpi_row, info_card
from components.charts import _base_layout
from config.settings import COLOR_PRIMARY
from utils.constants import VISTA_HOME

RESULTS_DIR = Path(__file__).resolve().parents[1] / \
    "data_benchmark" / "svrpbench_results" / "final_twcvrp"

_NOMBRES = {
    "DSS": "DSS (propuesto)",
    "or-tools-tw": "OR-Tools TWCVRP",
    "or-tools": "OR-Tools (solo cap.)",
    "nn2opt": "NN + 2-opt",
}
_COLOR = {"DSS": "#027A48", "or-tools-tw": "#1570EF",
          "nn2opt": "#B54708", "or-tools": "#98A2B3"}
_RGB = {"DSS": "2,122,72", "or-tools-tw": "21,112,239",
        "nn2opt": "181,71,8", "or-tools": "152,162,179"}
_DSS_ANTES_POR_TAMANO = {50: 14922.9, 100: 39294.1, 200: 95462.8}

# Criterios para el radar: (etiqueta, columna, direccion 'up'=mas es mejor / 'down'=menos).
_CRITERIOS_RADAR = [
    ("Costo bajo", "costo_prom", "down"),
    ("Robustez", "robustness", "down"),
    ("OTD", "otd_benchmark", "up"),
    ("Bajo CVR", "constraint_violation_rate", "down"),
    ("Utilizacion", "vehicle_utilization", "up"),
    ("Velocidad", "runtime_seconds", "down"),
]
# Tabla completa: (etiqueta, columna, direccion, formateador).
_CRITERIOS_TABLA = [
    ("Costo promedio (min)", "costo_prom", "down", lambda v: f"{v:,.0f}"),
    ("Robustez (variabilidad)", "robustness", "down", lambda v: f"{v:.2f}"),
    ("OTD (%)", "otd_benchmark", "up", lambda v: f"{v * 100:.1f}"),
    ("CVR (%)", "constraint_violation_rate", "down", lambda v: f"{v:.2f}"),
    ("Violaciones de ventana (prom)", "time_window_violations", "down", lambda v: f"{v:.2f}"),
    ("Utilizacion de vehiculos (%)", "vehicle_utilization", "up", lambda v: f"{v * 100:.0f}"),
    ("Factibilidad (FR)", "feasibility", "up", lambda v: f"{v:.2f}"),
    ("Cobertura (%)", "demand_fulfillment", "up", lambda v: f"{v * 100:.0f}"),
    ("Runtime (s)", "runtime_seconds", "down", lambda v: f"{v:.2f}"),
]


@st.cache_data(show_spinner=False)
def _load(nombre: str):
    f = RESULTS_DIR / nombre
    return pd.read_csv(f) if f.exists() else None


def _color(modelo: str) -> str:
    return _COLOR.get(modelo, "#667085")


def _score(serie: pd.Series, direccion: str):
    """Normaliza a [0,1] donde 1 = mejor entre los modelos (min-max por criterio)."""
    s = serie.astype(float)
    lo, hi = float(s.min()), float(s.max())
    if hi - lo < 1e-12:
        return [1.0] * len(s)
    if direccion == "up":
        return ((s - lo) / (hi - lo)).tolist()
    return ((hi - s) / (hi - lo)).tolist()


def _fig_radar(by_model: pd.DataFrame) -> go.Figure:
    theta = [c[0] for c in _CRITERIOS_RADAR]
    scores = {c[0]: _score(by_model[c[1]], c[2]) for c in _CRITERIOS_RADAR}
    fig = go.Figure()
    for i, m in enumerate(by_model["model_name"].tolist()):
        r = [scores[c[0]][i] for c in _CRITERIOS_RADAR]
        fig.add_trace(go.Scatterpolar(
            r=r + [r[0]], theta=theta + [theta[0]], name=_NOMBRES.get(m, m),
            fill="toself", fillcolor=f"rgba({_RGB.get(m, '102,112,133')},0.10)",
            line=dict(color=_color(m), width=2),
        ))
    fig.update_layout(
        height=440, margin=dict(l=60, r=60, t=30, b=60), paper_bgcolor="#FFFFFF",
        font=dict(family="Inter, sans-serif", color=COLOR_PRIMARY, size=11.5),
        polar=dict(
            bgcolor="#FFFFFF",
            radialaxis=dict(visible=True, range=[0, 1], showticklabels=False,
                            gridcolor="#EAECF0", linecolor="#EAECF0"),
            angularaxis=dict(gridcolor="#EAECF0", linecolor="#EAECF0",
                             tickfont=dict(size=11.5)),
        ),
        legend=dict(orientation="h", y=-0.08, x=0, font=dict(size=11)),
    )
    return fig


def _tabla_completa(by_model: pd.DataFrame):
    modelos = by_model["model_name"].tolist()
    cols = [_NOMBRES.get(m, m) for m in modelos]
    data, raw = {}, {}
    for label, key, direccion, fmt in _CRITERIOS_TABLA:
        vals = by_model[key].astype(float).tolist()
        data[label] = [fmt(v) for v in vals]
        raw[label] = (vals, direccion)
    df = pd.DataFrame(data, index=cols).T  # filas = criterios, columnas = modelos

    def _hl(row):
        vals, direccion = raw[row.name]
        best = min(vals) if direccion == "down" else max(vals)
        return ["background-color: #E7F4EC" if abs(v - best) < 1e-9 else "" for v in vals]

    return df.style.apply(_hl, axis=1)


def _fig_costo_por_modelo(by_model: pd.DataFrame) -> go.Figure:
    d = by_model.sort_values("costo_prom")
    fig = go.Figure(go.Bar(
        x=[_NOMBRES.get(m, m) for m in d["model_name"]], y=d["costo_prom"],
        marker_color=[_color(m) for m in d["model_name"]],
        text=[f"{v:,.0f}" for v in d["costo_prom"]], textposition="outside"))
    fig.update_layout(**_base_layout("Costo operativo promedio (menor es mejor)", height=330))
    fig.update_yaxes(title="costo (min)")
    return fig


def _fig_costo_por_tamano(by_ms: pd.DataFrame) -> go.Figure:
    tamanos = sorted(by_ms["instance_size"].unique())
    naive = (by_ms[by_ms["model_name"].isin(["or-tools", "nn2opt"])]
             .groupby("instance_size")["costo_prom"].min())

    def serie(modelo):
        return [by_ms[(by_ms.model_name == modelo) & (by_ms.instance_size == t)]["costo_prom"].iloc[0]
                for t in tamanos]
    fig = go.Figure()
    for nombre, color, dash, vals in [
        ("DSS (propuesto)", "#027A48", None, serie("DSS")),
        ("OR-Tools TWCVRP", "#1570EF", "dash", serie("or-tools-tw")),
        ("Heuristica ingenua", "#B54708", "dot", [naive[t] for t in tamanos])]:
        fig.add_trace(go.Scatter(x=[str(t) for t in tamanos], y=vals, mode="lines+markers",
                                 name=nombre, line=dict(color=color, width=2.5, dash=dash)))
    fig.update_layout(**_base_layout("Costo por tamano de instancia", height=330))
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
                         marker_color="#D0D5DD", text=[f"{v:,.0f}" for v in antes],
                         textposition="outside"))
    fig.add_trace(go.Bar(x=[str(t) for t in tamanos], y=ahora, name="DSS ahora",
                         marker_color="#027A48", text=[f"{v:,.0f}" for v in ahora],
                         textposition="outside"))
    fig.update_layout(**_base_layout("Efecto de las mejoras al DSS", height=330), barmode="group")
    fig.update_xaxes(title="clientes por instancia")
    fig.update_yaxes(title="costo (min)")
    return fig


def _fig_robustez(by_model: pd.DataFrame) -> go.Figure:
    d = by_model.sort_values("robustness")
    fig = go.Figure(go.Bar(
        x=[_NOMBRES.get(m, m) for m in d["model_name"]], y=d["robustness"],
        marker_color=[_color(m) for m in d["model_name"]],
        text=[f"{v:.2f}" for v in d["robustness"]], textposition="outside"))
    fig.update_layout(**_base_layout("Robustez: variabilidad del costo (menor es mejor)", height=330))
    fig.update_yaxes(title="desv. estandar del costo")
    return fig


def render():
    render_view_title(
        "Benchmark SVRPBench - rendimiento en todos los criterios",
        "Comparacion del DSS contra solvers de referencia sobre el benchmark academico "
        "SVRPBench (TWCVRP estocastico). Reconstruccion fiel al paper: capacidad real, "
        "ventanas por cliente y evaluador estocastico oficial. Mismo evaluador para todos.",
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

    kpi_row([
        {"label": "Posicion del DSS", "value": f"{pos_dss}o de {n_modelos}",
         "helptext": "Ranking por costo, factibilidad, CVR, OTD y runtime"},
        {"label": "Costo DSS", "value": f"{dss['costo_prom']:,.0f}",
         "helptext": "Tiempo operativo promedio bajo escenarios estocasticos (min)"},
        {"label": "OTD DSS", "value": f"{dss['otd_benchmark'] * 100:.1f}%",
         "helptext": "Entregas dentro de ventana"},
        {"label": "Robustez DSS", "value": f"{dss['robustness']:.2f}",
         "helptext": "Variabilidad del costo entre escenarios (la mejor de todos)"},
    ])

    # --- Perfil de rendimiento en TODOS los criterios (radar) ---
    render_divider()
    st.markdown("#### Perfil de rendimiento en todos los criterios")
    col_r, col_t = st.columns([5, 6], gap="large")
    with col_r:
        st.plotly_chart(_fig_radar(by_model), use_container_width=True,
                        config={"displayModeBar": False})
        st.caption(
            "Cada eje normalizado 0-1 (borde = mejor entre los modelos). Muestra la posicion "
            "relativa en cada criterio, no la magnitud absoluta; los valores reales en la tabla."
        )
    with col_t:
        st.markdown("**Tabla comparativa completa** (verde = mejor por criterio)")
        st.dataframe(_tabla_completa(by_model), use_container_width=True)

    # --- Detalle por criterio ---
    render_divider()
    st.markdown("#### Detalle por criterio")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.plotly_chart(_fig_costo_por_modelo(by_model), use_container_width=True,
                        config={"displayModeBar": False})
        st.plotly_chart(_fig_robustez(by_model), use_container_width=True,
                        config={"displayModeBar": False})
    with c2:
        if by_ms is not None:
            st.plotly_chart(_fig_costo_por_tamano(by_ms), use_container_width=True,
                            config={"displayModeBar": False})
            st.plotly_chart(_fig_antes_despues(by_ms), use_container_width=True,
                            config={"displayModeBar": False})

    # --- Ranking ---
    render_divider()
    st.markdown("#### Ranking de modelos")
    rk = ranking[["rank", "model_name", "costo_prom", "feasibility",
                  "constraint_violation_rate", "otd_benchmark", "runtime_seconds"]].copy()
    rk["model_name"] = rk["model_name"].map(lambda m: _NOMBRES.get(m, m))
    rk["otd_benchmark"] = (rk["otd_benchmark"] * 100).round(1)
    rk.columns = ["#", "Modelo", "Costo prom.", "Factibilidad", "CVR (%)", "OTD (%)", "Runtime (s)"]
    st.dataframe(rk, use_container_width=True, hide_index=True)

    # --- Conclusiones ---
    render_divider()
    col_a, col_b, col_c = st.columns(3, gap="medium")
    with col_a:
        info_card(
            "Hallazgo principal",
            "El DSS queda empatado con el mejor OR-Tools TWCVRP y supera ~31-40% en costo a "
            "las heuristicas ingenuas. Es el unico modelo en la esquina 'barato y estable'.",
            eyebrow="Conclusion",
        )
    with col_b:
        info_card(
            "Por que destaca",
            "Tiene la MEJOR robustez (menor variabilidad del costo entre escenarios), que es "
            "justo el objetivo del DSS: reducir la variabilidad de los tiempos de entrega.",
            eyebrow="Robustez",
        )
    with col_c:
        n_rep = int(rep["n_reparadas_dedicadas"].sum()) if rep is not None else 0
        info_card(
            "Honestidad metodologica",
            f"Todos sirven al 100% de clientes; los {n_rep} casos que el DSS no encaja en "
            "ventana estricta se cubren con viajes dedicados, con su costo cargado y reportado.",
            eyebrow="Metodologia",
        )

    render_divider()
    if st.button("Volver al inicio", key="bench_back"):
        st.session_state.vista = VISTA_HOME
        st.rerun()
    render_footer()
