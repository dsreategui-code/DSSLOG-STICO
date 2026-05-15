"""Supervisor - Ejecucion de la jornada simulada."""
from dataclasses import asdict
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.cards import kpi_row
from optimization.route_optimizer import Ruta
from simulation.sim_engine import simular_jornada
from utils.state import log_bitacora
from utils.formatters import fmt_pct, fmt_int
from utils.constants import (
    VISTA_SUPERVISOR_ROUTES, VISTA_SUPERVISOR_ALERTS, VISTA_SUPERVISOR_RESULTS,
)


def _rutas_dict_to_obj(rutas_dict: dict) -> dict:
    return {v: Ruta(**r) for v, r in rutas_dict.items()}


def render():
    render_view_title(
        "Simulacion de la jornada",
        "Ejecuta la simulacion estocastica de la jornada (09:00 a 19:00) con la flota "
        "y rutas asignadas. Las alertas de riesgo se registran para revision."
    )
    render_step_breadcrumb()

    dataset = st.session_state.get("dataset")
    cfg = st.session_state.get("configuracion") or {}
    rutas_dict = st.session_state.get("rutas_iniciales")
    if not dataset or not cfg or not rutas_dict:
        st.warning("Faltan datos, configuracion o rutas iniciales.")
        render_footer()
        return

    if primary("Ejecutar jornada", key="sup_run_sim"):
        with st.spinner("Simulando jornada..."):
            rutas_obj = _rutas_dict_to_obj(rutas_dict)
            res = simular_jornada(
                dataset,
                rutas=rutas_obj,
                configuracion=cfg,
                replanifica=bool(cfg.get("activar_replanificacion", True)),
                aprobacion_automatica=bool(cfg.get("aprobacion_automatica", False)),
                seed=int(cfg.get("semilla", 42)),
            )
        st.session_state.resultados = res
        st.session_state.rutas_finales = res.get("rutas_finales")
        st.session_state.alertas = res.get("alertas", [])
        st.session_state.decisiones_supervisor = res.get("decisiones", [])
        log_bitacora(
            "Supervisor - simulacion ejecutada",
            f"OTD inicial {res['kpis'].get('otd', 0):.1f}% · "
            f"{len(res.get('alertas', []))} alertas",
        )
        st.success("Jornada simulada correctamente.")

    res = st.session_state.get("resultados")
    if res and res.get("kpis"):
        k = res["kpis"]
        kpi_row([
            {"label": "OTD", "value": fmt_pct(k.get("otd"))},
            {"label": "OTIF", "value": fmt_pct(k.get("otif"))},
            {"label": "A tiempo", "value": fmt_int(k.get("entregas_a_tiempo"))},
            {"label": "Alertas", "value": fmt_int(len(res.get("alertas", [])))},
        ])

    render_divider()
    col_l, c_alert, c_res = st.columns([1, 1, 1])
    with col_l:
        if secondary("Rutas iniciales", key="sup_sim_back",
                     use_container_width=True):
            st.session_state.vista = VISTA_SUPERVISOR_ROUTES
            st.rerun()
    with c_alert:
        if primary("Alertas", key="sup_sim_to_alerts",
                   use_container_width=True,
                   disabled=not st.session_state.get("resultados")):
            navigate_to(VISTA_SUPERVISOR_ALERTS)
    with c_res:
        if primary("Resultados", key="sup_sim_to_res",
                   use_container_width=True,
                   disabled=not st.session_state.get("resultados")):
            navigate_to(VISTA_SUPERVISOR_RESULTS)

    render_footer()
