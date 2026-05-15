"""Control de navegacion entre vistas y reglas de pre-requisitos."""
import streamlit as st
from utils.constants import (
    MODO_VALIDACION, MODO_DEMOSTRACION,
    ROL_SUPERVISOR, ROL_CONDUCTOR,
    VISTA_HOME,
    VISTA_VALIDATION_DATA, VISTA_VALIDATION_CONFIG, VISTA_VALIDATION_SIMULATION,
    VISTA_VALIDATION_RESULTS, VISTA_VALIDATION_EXPORT,
    VISTA_DEMO_ROLE_SELECTION,
    VISTA_SUPERVISOR_DATA, VISTA_SUPERVISOR_CONFIG, VISTA_SUPERVISOR_ROUTES,
    VISTA_SUPERVISOR_SIMULATION, VISTA_SUPERVISOR_ALERTS, VISTA_SUPERVISOR_RESULTS,
    VISTA_SUPERVISOR_EXPORT, VISTA_DRIVER,
)

VALIDATION_FLOW = [
    (VISTA_VALIDATION_DATA, "Carga de datos"),
    (VISTA_VALIDATION_CONFIG, "Configuracion"),
    (VISTA_VALIDATION_SIMULATION, "Simulacion"),
    (VISTA_VALIDATION_RESULTS, "Resultados"),
    (VISTA_VALIDATION_EXPORT, "Exportacion"),
]

SUPERVISOR_FLOW = [
    (VISTA_SUPERVISOR_DATA, "Carga de datos"),
    (VISTA_SUPERVISOR_CONFIG, "Configuracion"),
    (VISTA_SUPERVISOR_ROUTES, "Rutas iniciales"),
    (VISTA_SUPERVISOR_SIMULATION, "Simulacion"),
    (VISTA_SUPERVISOR_ALERTS, "Alertas"),
    (VISTA_SUPERVISOR_RESULTS, "Resultados"),
    (VISTA_SUPERVISOR_EXPORT, "Exportacion"),
]

DRIVER_FLOW = [(VISTA_DRIVER, "Ruta del dia")]


def get_flow() -> list:
    modo = st.session_state.get("modo")
    rol = st.session_state.get("rol")
    if modo == MODO_VALIDACION:
        return VALIDATION_FLOW
    if modo == MODO_DEMOSTRACION:
        if rol == ROL_SUPERVISOR:
            return SUPERVISOR_FLOW
        if rol == ROL_CONDUCTOR:
            return DRIVER_FLOW
    return []


def can_advance_to(vista: str) -> tuple:
    """Devuelve (puede_avanzar, motivo) segun pre-requisitos."""
    s = st.session_state

    if vista in (VISTA_VALIDATION_CONFIG, VISTA_SUPERVISOR_CONFIG):
        if not s.get("dataset_validado"):
            return False, "Debes cargar y validar el dataset antes de continuar."

    if vista in (VISTA_VALIDATION_SIMULATION, VISTA_SUPERVISOR_SIMULATION):
        if not s.get("configuracion"):
            return False, "Debes definir la configuracion antes de simular."

    if vista in (VISTA_VALIDATION_RESULTS, VISTA_SUPERVISOR_RESULTS, VISTA_SUPERVISOR_ALERTS):
        if not s.get("resultados"):
            return False, "Debes ejecutar la simulacion antes de revisar los resultados."

    if vista in (VISTA_VALIDATION_EXPORT, VISTA_SUPERVISOR_EXPORT):
        if not s.get("resultados"):
            return False, "Debes ejecutar la simulacion antes de exportar."

    if vista == VISTA_SUPERVISOR_ROUTES:
        if not s.get("configuracion"):
            return False, "Debes definir la configuracion antes de generar rutas."

    if vista == VISTA_DRIVER:
        if not (s.get("rutas_iniciales") or s.get("rutas_finales")):
            return False, "El conductor solo puede ver rutas si el Supervisor ya las genero."

    return True, ""


def render_step_breadcrumb():
    """Renderiza la secuencia de pasos del flujo actual marcando el vigente."""
    flow = get_flow()
    if not flow:
        return
    current = st.session_state.get("vista")
    parts = []
    for i, (slug, label) in enumerate(flow, start=1):
        active = slug == current
        color = "#0F172A" if active else "#94A3B8"
        weight = "600" if active else "400"
        parts.append(f'<span style="color:{color}; font-weight:{weight};">{i}. {label}</span>')
    sep = '<span style="color:#CBD5E1; margin:0 0.55rem;">&rsaquo;</span>'
    html = sep.join(parts)
    st.markdown(
        f'<div style="font-size:0.82rem; color:#64748B; margin-bottom:1.1rem;">{html}</div>',
        unsafe_allow_html=True,
    )


def navigate_to(vista: str):
    """Cambia de vista validando pre-requisitos."""
    can, msg = can_advance_to(vista)
    if not can:
        st.warning(msg)
        return
    st.session_state.vista = vista
    st.rerun()


def back_home():
    st.session_state.vista = VISTA_HOME
    st.session_state.modo = None
    st.session_state.rol = None
    st.rerun()
