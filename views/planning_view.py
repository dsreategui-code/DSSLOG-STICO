"""Vista de Planificacion CORTEX-LM.

Ejecuta el pipeline de planificacion (factibilidad -> matriz contextual -> rutas candidatas
-> simulacion/riesgo -> recomendacion explicable) y muestra la comparacion de candidatas,
el IRI por pedido y la recomendacion. Permite enviar el escenario recomendado al Gemelo
Digital Operativo y exportar resultados.
"""
import plotly.graph_objects as go
import streamlit as st

from components.cards import info_card, kpi_row
from components.charts import _base_layout
from components.layout import render_divider, render_footer, render_view_title
from core.metrics import kpis_recomendada, tabla_candidatas, tabla_iri
from core.planner import planificar
from services.cortex_loader import cargar_contexto
from utils.constants import VISTA_DIGITAL_TWIN, VISTA_HOME

_COLOR_CLASIF = {"Bajo": "#027A48", "Moderado": "#B54708", "Alto": "#B42318",
                 "Critico": "#7A271A"}


def _contexto():
    if st.session_state.get("plan_ctx") is None:
        st.session_state.plan_ctx = cargar_contexto()
    return st.session_state.plan_ctx


def _fig_candidatas(tc):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=tc["perfil"], y=(tc["otd"] * 100), name="OTD (%)",
                         marker_color="#1570EF", yaxis="y"))
    fig.add_trace(go.Scatter(x=tc["perfil"], y=tc["distancia_km"], name="Distancia (km)",
                             mode="lines+markers", marker_color="#B54708", yaxis="y2"))
    lay = _base_layout("Candidatas: OTD vs distancia", height=320)
    lay["yaxis"] = dict(title="OTD (%)", range=[80, 101], gridcolor="#EAECF0")
    lay["yaxis2"] = dict(title="km", overlaying="y", side="right", showgrid=False)
    fig.update_layout(**lay)
    return fig


def render():
    render_view_title(
        "Planificacion CORTEX-LM",
        "Genera rutas candidatas con distintos perfiles de decision, las evalua por "
        "simulacion estocastica y recomienda una de forma explicable. La matriz base usa "
        "OSRM local (o respaldo si no esta disponible); el contexto urbano ajusta los tiempos.",
        eyebrow="CORTEX-LM  /  Planificacion",
    )
    ctx = _contexto()
    if ctx["avisos"]:
        st.warning("Avisos de carga: " + " ".join(ctx["avisos"]))

    n_total = len(ctx["pedidos"])
    c1, c2, c3 = st.columns([2, 2, 1.4])
    n_plan = c1.slider("Pedidos a planificar", 4, n_total, min(20, n_total),
                       help="Subconjunto para una corrida agil (el solver y la simulacion "
                            "escalan con el tamano).")
    fechas = ["(sin evento)"] + sorted({e.fecha for e in ctx["eventos"]})
    fecha_sel = c2.selectbox("Fecha (calendario de eventos)", fechas)
    planificar_btn = c3.button("Planificar", type="primary", use_container_width=True)

    if planificar_btn:
        with st.spinner("Planificando: candidatas + simulacion estocastica..."):
            ctx["parametros"].usar_osrm = bool(ctx["parametros"].usar_osrm)
            fecha = None if fecha_sel == "(sin evento)" else fecha_sel
            st.session_state.plan_result = planificar(ctx, max_pedidos=int(n_plan),
                                                      fecha=fecha)

    res = st.session_state.get("plan_result")
    if not res:
        st.info("Configura los parametros y pulsa **Planificar** para generar la propuesta.")
        render_divider()
        if st.button("Volver al inicio", key="plan_back0"):
            st.session_state.vista = VISTA_HOME
            st.rerun()
        render_footer()
        return

    # --- Factibilidad ---
    if not res["factible"]:
        st.error("La jornada NO es factible con los datos actuales:")
        for c in res["factibilidad"]["errores"]:
            st.write(f"- **{c['nombre']}**: {c['detalle']}")
        render_divider()
        if st.button("Volver al inicio", key="plan_back1"):
            st.session_state.vista = VISTA_HOME
            st.rerun()
        render_footer()
        return

    origen = res["matriz_origen"]
    badge = {"osrm": "OSRM local", "cache": "cache OSRM",
             "haversine_respaldo": "respaldo (haversine) - sin OSRM"}.get(origen, origen)
    kpis = kpis_recomendada(res)
    kpi_row([
        {"label": "Perfil recomendado", "value": res["perfil_recomendado"]},
        {"label": "OTD", "value": f"{kpis.get('otd', 0) * 100:.1f}%"},
        {"label": "Pedidos en riesgo", "value": str(int(kpis.get("pedidos_en_riesgo", 0)))},
        {"label": "Matriz base", "value": badge},
    ])

    # --- Recomendacion explicable ---
    st.success(f"**Recomendacion:** {res['recomendacion']['explicacion']}")

    # --- Comparacion de candidatas ---
    render_divider()
    st.markdown("#### Rutas candidatas por perfil")
    tc = tabla_candidatas(res)
    cda, cdb = st.columns([5, 6], gap="large")
    with cda:
        st.plotly_chart(_fig_candidatas(tc), use_container_width=True,
                        config={"displayModeBar": False})
    with cdb:
        st.dataframe(tc.round(3), use_container_width=True, hide_index=True)

    # --- IRI por pedido ---
    render_divider()
    st.markdown("#### Indice de Riesgo de Incumplimiento (IRI) por pedido")
    iri = tabla_iri(res)
    if not iri.empty:
        resumen = iri["clasificacion"].value_counts().to_dict()
        st.caption("Distribucion: " + "  ".join(f"{k}: {v}" for k, v in resumen.items()))
        st.dataframe(iri, use_container_width=True, hide_index=True)

    # --- Acciones ---
    render_divider()
    a1, a2, a3 = st.columns(3)
    if a1.button("Enviar al Gemelo Digital", type="primary", use_container_width=True):
        st.session_state.dt_escenario = res["escenario"]
        st.session_state.dt_tick = 0
        st.session_state.dt_replan = None
        st.session_state.vista = VISTA_DIGITAL_TWIN
        st.rerun()
    a2.download_button("Exportar candidatas (CSV)", tc.to_csv(index=False).encode("utf-8"),
                       file_name="cortex_candidatas.csv", mime="text/csv",
                       use_container_width=True)
    a3.download_button("Exportar IRI (CSV)", iri.to_csv(index=False).encode("utf-8"),
                       file_name="cortex_iri.csv", mime="text/csv", use_container_width=True)

    render_divider()
    if st.button("Volver al inicio", key="plan_back2"):
        st.session_state.vista = VISTA_HOME
        st.rerun()
    render_footer()
