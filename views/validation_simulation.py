"""Validacion - Ejecucion de la simulacion Monte Carlo multi-escenario."""
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.cards import kpi_row
from services.validation_service import run_validation, label_escenario
from utils.state import log_bitacora
from utils.formatters import fmt_pct, fmt_int
from utils.constants import (
    VISTA_VALIDATION_CONFIG, VISTA_VALIDATION_RESULTS,
)


def render():
    render_view_title(
        "Simulacion",
        "Ejecuta el experimento sobre los escenarios seleccionados. Cada escenario "
        "corre el numero de iteraciones definido, con variabilidad de trafico, "
        "estacionamiento, tiempos de servicio e incidencias."
    )
    render_step_breadcrumb()

    cfg = st.session_state.get("configuracion") or {}
    dataset = st.session_state.get("dataset")
    if not dataset or not cfg:
        st.warning("Falta dataset o configuracion. Vuelve a la pantalla anterior.")
        render_footer()
        return

    escenarios = cfg.get("escenarios_activos", [])
    iteraciones = int(cfg.get("iteraciones", 30))
    total_runs = len(escenarios) * iteraciones

    st.info(
        f"Escenarios: **{len(escenarios)}** · Iteraciones por escenario: **{iteraciones}** "
        f"· Total de corridas: **{total_runs}** · Semilla: {cfg.get('semilla', 42)}"
    )

    if primary("Ejecutar experimento", key="val_run_sim",
               use_container_width=False, disabled=not escenarios):
        with st.spinner("Ejecutando Monte Carlo..."):
            resultados = run_validation(dataset, cfg)
        st.session_state.resultados = resultados
        log_bitacora("Validacion - simulacion ejecutada",
                     f"{len(escenarios)} escenarios · {iteraciones} iter")
        st.success("Simulacion completada.")

    res = st.session_state.get("resultados")
    if res and res.get("kpis_por_escenario") is not None and not res["kpis_por_escenario"].empty:
        st.markdown("#### Resumen por escenario")
        cols = st.columns(len(res["kpis_por_escenario"]))
        for col, (_, r) in zip(cols, res["kpis_por_escenario"].iterrows()):
            with col:
                kpi_row([
                    {"label": label_escenario(r["escenario"]),
                     "value": fmt_pct(r.get("otd", 0)),
                     "delta": f"OTIF {fmt_pct(r.get('otif', 0))}",
                     "delta_dir": "flat"},
                ])

    render_divider()
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Configuracion", key="val_sim_back",
                     use_container_width=True):
            st.session_state.vista = VISTA_VALIDATION_CONFIG
            st.rerun()
    with col_r:
        if primary("Resultados", key="val_sim_next",
                   use_container_width=True,
                   disabled=not st.session_state.get("resultados")):
            navigate_to(VISTA_VALIDATION_RESULTS)

    render_footer()
