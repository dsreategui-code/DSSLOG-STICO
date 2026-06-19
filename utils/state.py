"""Inicializacion y helpers de session_state."""
from datetime import datetime
import streamlit as st
from utils.constants import VISTA_HOME

DEFAULT_STATE = {
    "modo": None,
    "rol": None,
    "vista": VISTA_HOME,
    "dataset": None,
    "dataset_validado": False,
    "dataset_path": None,
    "configuracion": None,
    "rutas_iniciales": None,
    "rutas_finales": None,
    "resultados": None,
    "alertas": [],
    "bitacora": [],
    "decisiones_supervisor": [],
    "exportacion_lista": False,
    "vehiculo_conductor": None,
    # Modo benchmark (ALM RRC) - aislado del flujo DSS.
    "benchmark_resultados": None,
    "benchmark_seleccion": None,
}


def init_state():
    """Inicializa todas las claves de session_state si no existen."""
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = value


def goto(vista: str):
    st.session_state.vista = vista
    st.rerun()


def set_modo(modo: str):
    st.session_state.modo = modo


def set_rol(rol: str):
    st.session_state.rol = rol


def reset_session():
    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value


def log_bitacora(evento: str, detalle: str = ""):
    """Registra un evento con timestamp en la bitacora."""
    st.session_state.bitacora.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "evento": evento,
        "detalle": detalle,
    })
