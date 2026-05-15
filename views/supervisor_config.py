"""Supervisor - Configuracion operativa de la jornada."""
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from utils.state import log_bitacora
from utils.constants import (
    VISTA_SUPERVISOR_DATA, VISTA_SUPERVISOR_ROUTES,
)
from config.settings import RANDOM_SEED


def render():
    render_view_title(
        "Configuracion operativa",
        "Define los parametros con los que se ejecutara la jornada simulada. "
        "Las replanificaciones intravehiculo requieren tu aprobacion antes de aplicarse."
    )
    render_step_breadcrumb()

    cfg_prev = st.session_state.get("configuracion") or {}

    col_l, col_r = st.columns(2)
    with col_l:
        velocidad = st.slider(
            "Velocidad urbana promedio (km/h)", 10.0, 35.0,
            float(cfg_prev.get("velocidad_kmh", 18.0)), 0.5,
        )
        umbral = st.slider(
            "Umbral de riesgo para alertar (min acumulados)", 5, 60,
            int(cfg_prev.get("umbral_riesgo_min", 15)), 1,
        )
        semilla = st.number_input(
            "Semilla de reproducibilidad", min_value=0, max_value=10_000,
            value=int(cfg_prev.get("semilla", RANDOM_SEED)),
        )
    with col_r:
        replanifica = st.toggle(
            "Activar replanificacion intravehiculo",
            value=bool(cfg_prev.get("activar_replanificacion", True)),
        )
        aprob_auto = st.toggle(
            "Aprobar replanificaciones automaticamente",
            value=bool(cfg_prev.get("aprobacion_automatica", False)),
            help="Si lo desactivas, cada propuesta requiere tu decision en la vista de Alertas.",
        )
        motor = st.radio(
            "Motor de optimizacion de rutas",
            options=["auto", "ortools", "greedy"],
            index=["auto", "ortools", "greedy"].index(cfg_prev.get("motor_optimizacion", "auto")),
            horizontal=True,
            help="auto: intenta OR-Tools y degrada al greedy si no esta disponible.",
        )
        st.caption(
            "Restriccion del DSS: la replanificacion solo reordena pedidos pendientes "
            "del mismo vehiculo. No se reasignan entre vehiculos."
        )

    render_divider()

    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Carga de datos", key="sup_cfg_back",
                     use_container_width=True):
            st.session_state.vista = VISTA_SUPERVISOR_DATA
            st.rerun()
    with col_r:
        if primary("Rutas iniciales", key="sup_cfg_next",
                   use_container_width=True):
            cfg = {
                "modo": "demostracion",
                "velocidad_kmh": float(velocidad),
                "umbral_riesgo_min": int(umbral),
                "semilla": int(semilla),
                "activar_replanificacion": bool(replanifica),
                "aprobacion_automatica": bool(aprob_auto),
                "motor_optimizacion": motor,
                "jornada_inicio": "09:00",
                "jornada_fin": "19:00",
            }
            st.session_state.configuracion = cfg
            log_bitacora("Supervisor - configuracion definida",
                         f"replan={replanifica} · aprob_auto={aprob_auto}")
            navigate_to(VISTA_SUPERVISOR_ROUTES)

    render_footer()
