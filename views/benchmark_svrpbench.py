"""Fase 9 - Vista de analisis del benchmark SVRPBench (TWCVRP fiel).

Lee los resultados de `data_benchmark/svrpbench_results/final_twcvrp/` (Fase 8b) y los
presenta de forma interpretada: perfil de rendimiento en todos los criterios (radar),
tabla comparativa completa, comparacion por tamano de instancia (50/100/200), detalle por
criterio, ranking y conclusiones.

Argumento central (honesto): el DSS supera ampliamente a las heuristicas comunes y empata
con el mejor OR-Tools TWCVRP. La robustez se muestra como un criterio mas, sin sobrevenderla
(las diferencias absolutas entre modelos son pequenas).

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

_CRITERIOS_RADAR = [
    ("Costo bajo", "costo_prom", "down"),
    ("OTD", "otd_benchmark", "up"),
    ("Bajo CVR", "constraint_violation_rate", "down"),
    ("Utilizacion", "vehicle_utilization", "up"),
    ("Velocidad", "runtime_seconds", "down"),
    ("Robustez", "robustness", "down"),
]
_CRITERIOS_TABLA = [
    ("Costo promedio (min)", "costo_prom", "down", lambda v: f"{v:,.0f}"),
    ("OTD (%)", "otd_benchmark", "up", lambda v: f"{v * 100:.1f}"),
    ("CVR (%)", "constraint_violation_rate", "down", lambda v: f"{v:.2f}"),
    ("Violaciones de ventana (prom)", "time_window_violations", "down", lambda v: f"{v:.2f}"),
    ("Utilizacion de vehiculos (%)", "vehicle_utilization", "up", lambda v: f"{v * 100:.0f}"),
    ("Factibilidad (FR)", "feasibility", "up", lambda v: f"{v:.2f}"),
    ("Cobertura (%)", "demand_fulfillment", "up", lambda v: f"{v * 100:.0f}"),
    ("Robustez (variabilidad, min)", "robustness", "down", lambda v: f"{v:.2f}"),
    ("Runtime (s)", "runtime_seconds", "down", lambda v: f"{v:.2f}"),
]


@st.cache_data(show_spinner=False)
def _load(nombre: str):
    f = RESULTS_DIR / nombre
    return pd.read_csv(f) if f.exists() else None


def _color(modelo: str) -> str:
    return _COLOR.get(modelo, "#667085")


def _ahorro_vs_naive(df: pd.DataFrame) -> float:
    """% de ahorro del DSS frente a la mejor heuristica ingenua (or-tools/nn2opt)."""
    dss = float(df[df.model_name == "DSS"]["costo_prom"].iloc[0])
    naive = float(df[df.model_name.isin(["or-tools", "nn2opt"])]["costo_prom"].min())
    return (1 - dss / naive) * 100 if naive else 0.0


def _score(serie: pd.Series, direccion: str):
    s = serie.astype(float)
    lo, hi = float(s.min()), float(s.max())
    if hi - lo < 1e-12:
        return [1.0] * len(s)
    return ((s - lo) / (hi - lo)).tolist() if direccion == "up" else ((hi - s) / (hi - lo)).tolist()


def _fig_radar(by_model: pd.DataFrame) -> go.Figure:
    theta = [c[0] for c in _CRITERIOS_RADAR]
    scores = {c[0]: _score(by_model[c[1]], c[2]) for c in _CRITERIOS_RADAR}
    fig = go.Figure()
    for i, m in enumerate(by_model["model_name"].tolist()):
        r = [scores[c[0]][i] for c in _CRITERIOS_RADAR]
        fig.add_trace(go.Scatterpolar(
            r=r + [r[0]], theta=theta + [theta[0]], name=_NOMBRES.get(m, m),
            fill="toself", fillcolor=f"rgba({_RGB.get(m, '102,112,133')},0.10)",
            line=dict(color=_color(m), width=2)))
    fig.update_layout(
        height=440, margin=dict(l=60, r=60, t=30, b=60), paper_bgcolor="#FFFFFF",
        font=dict(family="Inter, sans-serif", color=COLOR_PRIMARY, size=11.5),
        polar=dict(bgcolor="#FFFFFF",
                   radialaxis=dict(visible=True, range=[0, 1], showticklabels=False,
                                   gridcolor="#EAECF0", linecolor="#EAECF0"),
                   angularaxis=dict(gridcolor="#EAECF0", linecolor="#EAECF0",
                                    tickfont=dict(size=11.5))),
        legend=dict(orientation="h", y=-0.08, x=0, font=dict(size=11)))
    return fig


def _tabla_completa(df_modelos: pd.DataFrame):
    modelos = df_modelos["model_name"].tolist()
    cols = [_NOMBRES.get(m, m) for m in modelos]
    data, raw = {}, {}
    for label, key, direccion, fmt in _CRITERIOS_TABLA:
        vals = df_modelos[key].astype(float).tolist()
        data[label] = [fmt(v) for v in vals]
        raw[label] = (vals, direccion)
    df = pd.DataFrame(data, index=cols).T

    def _hl(row):
        vals, direccion = raw[row.name]
        best = min(vals) if direccion == "down" else max(vals)
        return ["background-color: #E7F4EC" if abs(v - best) < 1e-9 else "" for v in vals]

    return df.style.apply(_hl, axis=1)


def _fig_costo_modelos(df: pd.DataFrame, titulo: str) -> go.Figure:
    d = df.sort_values("costo_prom")
    fig = go.Figure(go.Bar(
        x=[_NOMBRES.get(m, m) for m in d["model_name"]], y=d["costo_prom"],
        marker_color=[_color(m) for m in d["model_name"]],
        text=[f"{v:,.0f}" for v in d["costo_prom"]], textposition="outside"))
    fig.update_layout(**_base_layout(titulo, height=330))
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


def _fig_utilizacion(by_model: pd.DataFrame) -> go.Figure:
    d = by_model.sort_values("vehicle_utilization", ascending=False)
    fig = go.Figure(go.Bar(
        x=[_NOMBRES.get(m, m) for m in d["model_name"]], y=(d["vehicle_utilization"] * 100),
        marker_color=[_color(m) for m in d["model_name"]],
        text=[f"{v * 100:.0f}%" for v in d["vehicle_utilization"]], textposition="outside"))
    fig.update_layout(**_base_layout("Utilizacion de vehiculos (mayor es mejor)", height=330))
    fig.update_yaxes(title="carga / capacidad (%)", range=[0, 105])
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


def render():
    render_view_title(
        "Benchmark SVRPBench - rendimiento del DSS por criterio",
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
    ahorro = _ahorro_vs_naive(by_model)

    kpi_row([
        {"label": "Posicion del DSS", "value": f"{pos_dss}o de {len(ranking)}",
         "helptext": "Ranking por costo, factibilidad, CVR, OTD y runtime"},
        {"label": "Costo DSS", "value": f"{dss['costo_prom']:,.0f}",
         "helptext": "Tiempo operativo promedio bajo escenarios estocasticos (min)"},
        {"label": "Ahorro vs heuristica", "value": f"-{ahorro:.0f}%",
         "helptext": "Costo del DSS frente a la mejor heuristica ingenua (NN+2opt / OR-Tools cap.)"},
        {"label": "OTD DSS", "value": f"{dss['otd_benchmark'] * 100:.1f}%",
         "helptext": "Entregas dentro de ventana"},
    ])

    # --- Perfil en todos los criterios ---
    render_divider()
    st.markdown("#### Perfil de rendimiento en todos los criterios")
    col_r, col_t = st.columns([5, 6], gap="large")
    with col_r:
        st.plotly_chart(_fig_radar(by_model), use_container_width=True,
                        config={"displayModeBar": False})
        st.caption(
            "Cada eje normalizado 0-1 (borde = mejor entre los modelos): muestra la posicion "
            "RELATIVA, no la magnitud. Nota: en robustez las diferencias absolutas son muy "
            "pequenas (fracciones de minuto); el diferenciador real es el costo."
        )
    with col_t:
        st.markdown("**Tabla comparativa completa** (verde = mejor por criterio)")
        st.dataframe(_tabla_completa(by_model), use_container_width=True)

    # --- Comparacion por tamano de instancia ---
    if by_ms is not None:
        render_divider()
        st.markdown("#### Comparacion por tamano de instancia")
        st.caption("Cada modelo se evaluo en 10 instancias de cada tamano (50, 100 y 200 clientes).")
        tabs = st.tabs(["50 clientes", "100 clientes", "200 clientes"])
        for tab, size in zip(tabs, [50, 100, 200]):
            with tab:
                sub = by_ms[by_ms["instance_size"] == size]
                if sub.empty:
                    st.info("Sin datos para este tamano.")
                    continue
                ahorro_s = _ahorro_vs_naive(sub)
                c_izq, c_der = st.columns([5, 6], gap="large")
                with c_izq:
                    st.plotly_chart(
                        _fig_costo_modelos(sub, f"Costo a {size} clientes (menor es mejor)"),
                        use_container_width=True, config={"displayModeBar": False})
                    st.caption(f"A {size} clientes, el DSS es ~{ahorro_s:.0f}% mas barato que la "
                               "mejor heuristica ingenua.")
                with c_der:
                    st.markdown(f"**Todos los indicadores a {size} clientes** (verde = mejor)")
                    st.dataframe(_tabla_completa(sub), use_container_width=True)

    # --- Detalle por criterio ---
    render_divider()
    st.markdown("#### Detalle por criterio")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.plotly_chart(_fig_costo_modelos(by_model, "Costo operativo promedio (menor es mejor)"),
                        use_container_width=True, config={"displayModeBar": False})
        st.plotly_chart(_fig_utilizacion(by_model), use_container_width=True,
                        config={"displayModeBar": False})
    with c2:
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
            "Argumento central",
            f"El DSS es ~{ahorro:.0f}% mas barato que las heuristicas comunes (NN+2opt, "
            "OR-Tools solo capacidad), con igual servicio (OTD ~99%) y casi el doble de "
            "utilizacion de flota. Esa es la ventaja real y de gran magnitud.",
            eyebrow="Conclusion",
        )
    with col_b:
        info_card(
            "Al nivel del estado del arte",
            "Empata (~1%) con un OR-Tools TWCVRP construido a proposito para este problema. "
            "El DSS no es un sistema improvisado: compite con la mejor herramienta disponible.",
            eyebrow="Comparacion",
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
