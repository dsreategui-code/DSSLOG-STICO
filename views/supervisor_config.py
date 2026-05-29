"""Supervisor - Configuracion operativa de la jornada.

Controles expuestos: tipo de escenario operativo, factor de trafico, variabilidad
de tiempos de servicio, factor de probabilidad de incidencias, umbral de riesgo
y semilla. Motor de optimizacion fijado a OR-Tools (con respaldo greedy interno).
Replanificacion intravehiculo siempre activa y siempre con aprobacion manual.
"""
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from utils.state import log_bitacora
from utils.constants import (
    VISTA_SUPERVISOR_DATA, VISTA_SUPERVISOR_ROUTES,
)
from config.settings import RANDOM_SEED


# Valores internos fijos
_VELOCIDAD_KMH_FIJA = 18.0
_MOTOR_OPTIMIZACION = "auto"     # OR-Tools con respaldo tecnico greedy

# Presets de escenario operativo - solo etiquetan la jornada (no fuerzan los sliders).
ESCENARIOS_OPERATIVOS = {
    "operacion_normal": "Operacion normal",
    "trafico_alto":     "Trafico alto",
    "dia_complicado":   "Dia complicado",
    "personalizado":    "Personalizado",
}


def render():
    render_view_title(
        "Configuracion operativa",
        "Define los parametros con los que se ejecutara la jornada simulada. "
        "Cada replanificacion intravehiculo propuesta requerira tu aprobacion."
    )
    render_step_breadcrumb()

    cfg_prev = st.session_state.get("configuracion") or {}

    col_l, col_r = st.columns(2)
    with col_l:
        escenario = st.selectbox(
            "Escenario operativo",
            options=list(ESCENARIOS_OPERATIVOS.keys()),
            index=list(ESCENARIOS_OPERATIVOS.keys()).index(
                cfg_prev.get("escenario_operativo", "operacion_normal")
            ),
            format_func=lambda x: ESCENARIOS_OPERATIVOS[x],
            help="Etiqueta de la jornada simulada. Se usa en bitacora y exportes.",
        )
        factor_trafico = st.slider(
            "Intensidad de trafico", 0.6, 2.0,
            float(cfg_prev.get("factor_trafico", 1.0)), 0.05,
            help="Multiplicador global sobre los perfiles de trafico por franja horaria. "
                 "1.0 = condiciones tipicas del dataset.",
        )
        factor_variabilidad = st.slider(
            "Variabilidad de tiempos de servicio", 0.5, 2.0,
            float(cfg_prev.get("factor_variabilidad_servicio", 1.0)), 0.05,
            help="Escala la desviacion del tiempo de servicio en cada parada. "
                 "1.0 = variabilidad nominal (sigma 12%).",
        )
    with col_r:
        factor_incidencias = st.slider(
            "Probabilidad de incidencias", 0.0, 2.0,
            float(cfg_prev.get("factor_incidencias", 1.0)), 0.05,
            help="Multiplicador sobre las probabilidades base de incidencias "
                 "(trafico severo, estacionamiento, cliente ausente, etc).",
        )
        umbral = st.slider(
            "Umbral de riesgo para alertar (min acumulados)", 5, 60,
            int(cfg_prev.get("umbral_riesgo_min", 15)), 1,
        )
        semilla = st.number_input(
            "Semilla de reproducibilidad", min_value=0, max_value=10_000,
            value=int(cfg_prev.get("semilla", RANDOM_SEED)),
        )

    st.caption(
        "Motor de optimizacion: OR-Tools (CVRPTW). "
        "La replanificacion intravehiculo solo reordena pedidos pendientes del mismo "
        "vehiculo y requiere aprobacion del Supervisor."
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
                "escenario_operativo": escenario,
                "factor_trafico": float(factor_trafico),
                "factor_variabilidad_servicio": float(factor_variabilidad),
                "factor_incidencias": float(factor_incidencias),
                "umbral_riesgo_min": int(umbral),
                "semilla": int(semilla),
                # Parametros internos no expuestos
                "velocidad_kmh": _VELOCIDAD_KMH_FIJA,
                "motor_optimizacion": _MOTOR_OPTIMIZACION,
                "activar_replanificacion": True,
                "aprobacion_automatica": False,
                "jornada_inicio": "09:00",
                "jornada_fin": "19:00",
            }
            st.session_state.configuracion = cfg
            log_bitacora(
                "Supervisor - configuracion definida",
                f"escenario={ESCENARIOS_OPERATIVOS[escenario]} - "
                f"trafico x{factor_trafico:.2f} - "
                f"variabilidad x{factor_variabilidad:.2f} - "
                f"incidencias x{factor_incidencias:.2f}",
            )
            navigate_to(VISTA_SUPERVISOR_ROUTES)

    render_footer()
