"""Vista de Planificacion CORTEX-LM.

Ejecuta el pipeline de planificacion (factibilidad -> matriz contextual -> rutas candidatas
-> simulacion/riesgo -> recomendacion explicable) y muestra la comparacion de candidatas,
el IRI por pedido y la recomendacion. Permite enviar el escenario recomendado al Gemelo
Digital Operativo y exportar resultados.
"""
import streamlit as st

from components.cards import info_card, kpi_row
from components.layout import render_divider, render_footer, render_view_title
from core.metrics import kpis_recomendada, tabla_candidatas, tabla_iri
from core.planner import planificar
from dashboards.risk_dashboard import (es_robusto, fig_iri_clasificacion,
                                       fig_ranking_robusto, fig_robustez_por_escenario)
from services.cortex_loader import cargar_contexto
from services.data_loader import dataset_exists, generar_dataset_demo
from utils.constants import VISTA_DIGITAL_TWIN, VISTA_DEMO_ROLE_SELECTION


def _guard_dataset() -> bool:
    """Si el dataset demo no existe (despliegue limpio), ofrece generarlo. True si falta."""
    if dataset_exists():
        return False
    st.warning("El dataset demo aun no existe en este entorno. Generalo para continuar.")
    if st.button("Generar dataset demo", type="primary", key="plan_gen_ds"):
        with st.spinner("Generando dataset demo..."):
            ok = generar_dataset_demo()
        if ok:
            st.rerun()
        else:
            st.error("No se pudo generar el dataset (revisa generar_dataset_sintetico.py).")
    render_divider()
    if st.button("Volver a Demostracion", key="plan_nodata_back"):
        st.session_state.vista = VISTA_DEMO_ROLE_SELECTION
        st.rerun()
    render_footer()
    return True

def _contexto():
    if st.session_state.get("plan_ctx") is None:
        st.session_state.plan_ctx = cargar_contexto()
    return st.session_state.plan_ctx


def render():
    render_view_title(
        "Planificacion CORTEX-LM",
        "Genera rutas candidatas con distintos perfiles de decision, las evalua por "
        "simulacion estocastica y recomienda una de forma explicable. La matriz base usa "
        "OSRM local (o respaldo si no esta disponible); el contexto urbano ajusta los tiempos.",
        eyebrow="CORTEX-LM  /  Planificacion",
    )
    if _guard_dataset():
        return
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
        if st.button("Volver a Demostracion", key="plan_back0"):
            st.session_state.vista = VISTA_DEMO_ROLE_SELECTION
            st.rerun()
        render_footer()
        return

    # --- Factibilidad ---
    if not res["factible"]:
        st.error("La jornada NO es factible con los datos actuales:")
        for c in res["factibilidad"]["errores"]:
            st.write(f"- **{c['nombre']}**: {c['detalle']}")
        render_divider()
        if st.button("Volver a Demostracion", key="plan_back1"):
            st.session_state.vista = VISTA_DEMO_ROLE_SELECTION
            st.rerun()
        render_footer()
        return

    origen = res["matriz_origen"]
    badge = {"osrm": "OSRM local", "cache": "cache OSRM",
             "haversine_respaldo": "respaldo (haversine) - sin OSRM"}.get(origen, origen)
    elegida = (res.get("recomendacion") or {}).get("elegida")
    robusto = es_robusto(res)
    if robusto:
        otd_nom = float(elegida["otd_nominal"])
        otd_peor = float(elegida["otd_peor"])
        riesgo = int(elegida["pedidos_en_riesgo_peor"])
    else:
        kpis = kpis_recomendada(res)
        otd_nom = otd_peor = float(kpis.get("otd", 0.0))
        riesgo = int(kpis.get("pedidos_en_riesgo", 0))

    kpi_row([
        {"label": "Perfil recomendado", "value": str(res["perfil_recomendado"])},
        {"label": "OTD (nominal)", "value": f"{otd_nom * 100:.1f}%",
         "helptext": "Entregas a tiempo esperadas en condiciones nominales"},
        {"label": "OTD (peor caso)", "value": f"{otd_peor * 100:.1f}%",
         "delta": f"{(otd_peor - otd_nom) * 100:+.1f} pts",
         "delta_dir": "down" if otd_peor < otd_nom - 1e-9 else "flat",
         "helptext": "Bajo el peor escenario del conjunto de ambiguedad (DRO)"},
        {"label": "Pedidos en riesgo (peor)", "value": str(riesgo)},
    ])
    st.caption(f"Matriz base: **{badge}**  ·  modo: **{res.get('modo', '-')}**  ·  "
               f"escenarios de ambiguedad: {', '.join(res.get('ambiguedad') or ['nominal'])}")

    # --- Recomendacion explicable ---
    st.success(f"**Recomendacion:** {res['recomendacion']['explicacion']}")

    # --- Robustez (DRO): nominal vs peor caso ---
    if robusto:
        render_divider()
        st.markdown("#### Robustez ante la incertidumbre (DRO)")
        rc1, rc2 = st.columns([6, 5], gap="large")
        with rc1:
            st.plotly_chart(fig_robustez_por_escenario(elegida), use_container_width=True,
                            config={"displayModeBar": False})
        with rc2:
            st.plotly_chart(fig_ranking_robusto(res), use_container_width=True,
                            config={"displayModeBar": False})
        st.caption("El plan se evalua sobre un conjunto de escenarios (nominal + 'Lima peor'). "
                   "Se recomienda la candidata con mejor PEOR CASO (menor CVaR de tardanza), no "
                   "la de mejor promedio: robusta a que la realidad sea peor que los datos.")

    # --- Comparacion de candidatas ---
    render_divider()
    st.markdown("#### Rutas candidatas (nominal vs peor caso, score robusto)")
    tc = tabla_candidatas(res)
    st.dataframe(tc.round(3), use_container_width=True, hide_index=True)

    # --- IRI por pedido ---
    render_divider()
    st.markdown("#### Indice de Riesgo de Incumplimiento (IRI) por pedido")
    iri = tabla_iri(res)
    if not iri.empty:
        ic1, ic2 = st.columns([4, 7], gap="large")
        with ic1:
            st.plotly_chart(fig_iri_clasificacion(iri), use_container_width=True,
                            config={"displayModeBar": False})
        with ic2:
            st.dataframe(iri, use_container_width=True, hide_index=True)

    # --- Acciones ---
    render_divider()
    a1, a2, a3 = st.columns(3)
    if a1.button("Enviar al Gemelo Digital", type="primary", use_container_width=True):
        st.session_state.dt_escenario = res["escenario"]
        st.session_state.dt_tick = 0
        st.session_state.dt_bump = 0
        st.session_state.dt_sig = None          # reset decisiones de re-ruteo del gemelo
        st.session_state.dt_dec = {}
        st.session_state.vista = VISTA_DIGITAL_TWIN
        st.rerun()
    a2.download_button("Exportar candidatas (CSV)", tc.to_csv(index=False).encode("utf-8"),
                       file_name="cortex_candidatas.csv", mime="text/csv",
                       use_container_width=True)
    a3.download_button("Exportar IRI (CSV)", iri.to_csv(index=False).encode("utf-8"),
                       file_name="cortex_iri.csv", mime="text/csv", use_container_width=True)

    render_divider()
    if st.button("Volver a Demostracion", key="plan_back2"):
        st.session_state.vista = VISTA_DEMO_ROLE_SELECTION
        st.rerun()
    render_footer()
