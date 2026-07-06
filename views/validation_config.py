"""Validacion - Configuracion del experimento.

Solo se exponen los parametros que el usuario realmente decide: iteraciones,
escenarios, semilla y umbral de riesgo. El motor de optimizacion es OR-Tools
(con fallback tecnico interno) y la replanificacion intravehiculo del escenario
DSS completo se aplica automaticamente cuando mejora el OTD.
"""
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from utils.state import log_bitacora
from utils.constants import (
    VISTA_VALIDATION_DATA, VISTA_VALIDATION_SIMULATION,
)
from config.settings import RANDOM_SEED


# Valores internos fijos (no expuestos en la UI)
_VELOCIDAD_KMH_FIJA = 18.0
_MOTOR_OPTIMIZACION = "auto"   # OR-Tools con respaldo greedy interno

# Condicion de la jornada -> intensidad del estres (factor_incidencias, factor_trafico). La robustez
# (buffer del DSS completo) y la replanificacion solo lucen su valor bajo estres.
_CONDICIONES = {
    "Normal": (1.0, 1.0),
    "Dificil": (2.5, 1.2),
    "Critico": (4.0, 1.4),
}


def render():
    render_view_title(
        "Configuracion del experimento",
        "Define los parametros operativos del experimento de validacion. La replanificacion "
        "intravehiculo se aplica automaticamente en el escenario DSS completo cuando mejora "
        "el OTD proyectado."
    )
    render_step_breadcrumb()

    cfg_prev = st.session_state.get("configuracion") or {}

    col_l, col_r = st.columns(2)
    with col_l:
        iteraciones = st.number_input(
            "Iteraciones Monte Carlo", min_value=5, max_value=200,
            value=int(cfg_prev.get("iteraciones", 30)), step=5,
            help="Numero de corridas independientes por escenario.",
        )
        umbral = st.slider(
            "Umbral de riesgo para replanificar (min acumulados)", 5, 60,
            int(cfg_prev.get("umbral_riesgo_min", 15)), 1,
            help="Cuando el retraso proyectado de los pedidos pendientes excede este "
                 "umbral, el motor evalua una replanificacion intravehiculo.",
        )
        _cond_opts = list(_CONDICIONES.keys())
        condicion = st.selectbox(
            "Condicion de la jornada",
            options=_cond_opts,
            index=_cond_opts.index(cfg_prev.get("condicion_jornada", "Dificil"))
            if cfg_prev.get("condicion_jornada", "Dificil") in _cond_opts else 1,
            help="Intensidad del estres (incidencias y trafico). La robustez del DSS completo y la "
                 "replanificacion demuestran su valor bajo dias Dificil/Critico, no en un dia Normal.",
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
                "sin_dss": "Operacion sin DSS",
                "solo_ruta": "DSS parcial",
                "dss_completo": "DSS completo",
            }.get(x, x),
        )

    st.caption(
        "Motor de optimizacion: OR-Tools (CVRPTW). "
        "La replanificacion intravehiculo del escenario DSS completo se aplica "
        "automaticamente cuando mejora el OTD."
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
            _fi, _ft = _CONDICIONES.get(condicion, (1.0, 1.0))
            cfg = {
                "modo": "validacion",
                "iteraciones": int(iteraciones),
                "umbral_riesgo_min": int(umbral),
                "semilla": int(semilla),
                "escenarios_activos": escenarios,
                "condicion_jornada": condicion,
                "factor_incidencias": _fi,
                "factor_trafico": _ft,
                # Parametros internos no expuestos
                "velocidad_kmh": _VELOCIDAD_KMH_FIJA,
                "motor_optimizacion": _MOTOR_OPTIMIZACION,
                "aprobacion_automatica": True,
                "jornada_inicio": "09:00",
                "jornada_fin": "19:00",
            }
            st.session_state.configuracion = cfg
            log_bitacora("Validacion - configuracion definida",
                         f"{len(escenarios)} escenarios - {iteraciones} iteraciones")
            navigate_to(VISTA_VALIDATION_SIMULATION)

    render_footer()
