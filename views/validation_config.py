"""Validacion - Configuracion del experimento."""
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from utils.state import log_bitacora
from utils.constants import (
    VISTA_VALIDATION_DATA, VISTA_VALIDATION_SIMULATION,
)
from config.settings import RANDOM_SEED


def render():
    render_view_title(
        "Configuracion del experimento",
        "Define los parametros operativos del experimento de validacion. La replanificacion "
        "intravehiculo solo aplica al escenario DSS completo."
    )
    render_step_breadcrumb()

    cfg_prev = st.session_state.get("configuracion") or {}

    col_l, col_r = st.columns(2)
    with col_l:
        iteraciones = st.number_input(
            "Iteraciones Monte Carlo", min_value=5, max_value=200,
            value=int(cfg_prev.get("iteraciones", 30)), step=5,
        )
        velocidad = st.slider(
            "Velocidad urbana promedio (km/h)", 10.0, 35.0,
            float(cfg_prev.get("velocidad_kmh", 18.0)), 0.5,
        )
        umbral = st.slider(
            "Umbral de riesgo para replanificar (min acumulados)", 5, 60,
            int(cfg_prev.get("umbral_riesgo_min", 15)), 1,
        )
    with col_r:
        semilla = st.number_input(
            "Semilla de reproducibilidad", min_value=0, max_value=10_000,
            value=int(cfg_prev.get("semilla", RANDOM_SEED)),
        )
        escenarios = st.multiselect(
            "Escenarios a comparar",
            options=["sin_dss", "solo_ruta", "dss_completo"],
            default=cfg_prev.get("escenarios_activos",
                                 ["sin_dss", "solo_ruta", "dss_completo"]),
            format_func=lambda x: {
                "sin_dss": "Sin DSS",
                "solo_ruta": "Ruta optimizada",
                "dss_completo": "DSS completo",
            }.get(x, x),
        )
        st.write("")
        aprob_auto = st.toggle(
            "Aprobar replanificaciones automaticamente (modo validacion)",
            value=bool(cfg_prev.get("aprobacion_automatica", True)),
            help="En validacion la replanificacion intravehiculo se aplica sola si mejora el OTD.",
        )

    render_divider()

    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Carga de datos", key="val_cfg_back",
                     use_container_width=True):
            st.session_state.vista = VISTA_VALIDATION_DATA
            st.rerun()
    with col_r:
        if primary("Simulacion", key="val_cfg_next",
                   use_container_width=True,
                   disabled=not escenarios):
            cfg = {
                "modo": "validacion",
                "iteraciones": int(iteraciones),
                "velocidad_kmh": float(velocidad),
                "umbral_riesgo_min": int(umbral),
                "semilla": int(semilla),
                "escenarios_activos": escenarios,
                "aprobacion_automatica": bool(aprob_auto),
                "jornada_inicio": "09:00",
                "jornada_fin": "19:00",
            }
            st.session_state.configuracion = cfg
            log_bitacora("Validacion - configuracion definida",
                         f"{len(escenarios)} escenarios · {iteraciones} iteraciones")
            navigate_to(VISTA_VALIDATION_SIMULATION)

    render_footer()
