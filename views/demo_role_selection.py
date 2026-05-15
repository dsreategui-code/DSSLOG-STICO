"""Seleccion de rol dentro del modo Demostracion interactiva."""
import streamlit as st
from components.layout import render_view_title, render_divider, render_footer
from components.cards import feature_card
from components.buttons import secondary
from utils.constants import (
    ROL_SUPERVISOR, ROL_CONDUCTOR,
    VISTA_SUPERVISOR_DATA, VISTA_DRIVER, VISTA_HOME,
)


def render():
    render_view_title(
        "Selecciona tu rol",
        "Cada perfil accede a un subconjunto del DSS adecuado a sus responsabilidades.",
        eyebrow="Demostracion interactiva",
    )

    col1, col2 = st.columns(2, gap="large")

    with col1:
        feature_card(
            eyebrow="Perfil A",
            title="Supervisor / Operador",
            description=(
                "Carga datos, configura el escenario, genera las rutas iniciales, "
                "ejecuta la simulacion, evalua las alertas y aprueba o rechaza las "
                "replanificaciones intravehiculo. Acceso completo a resultados y exportaciones."
            ),
        )
        if st.button("Ingresar como Supervisor", key="rol_sup",
                     type="primary", use_container_width=True):
            st.session_state.rol = ROL_SUPERVISOR
            st.session_state.vista = VISTA_SUPERVISOR_DATA
            st.rerun()

    with col2:
        rutas_listas = bool(
            st.session_state.get("rutas_iniciales") or st.session_state.get("rutas_finales")
        )
        nota = "" if rutas_listas else (
            " Disponible cuando el Supervisor haya generado las rutas."
        )
        feature_card(
            eyebrow="Perfil B",
            title="Conductor",
            description=(
                "Selecciona tu vehiculo, consulta la ruta asignada del dia, revisa la "
                "lista de pedidos en orden de entrega y abre cada parada en el navegador." + nota
            ),
        )
        if st.button("Ingresar como Conductor", key="rol_drv", type="primary",
                     use_container_width=True, disabled=not rutas_listas):
            st.session_state.rol = ROL_CONDUCTOR
            st.session_state.vista = VISTA_DRIVER
            st.rerun()
        if not rutas_listas:
            st.caption("El acceso al rol Conductor depende de la generacion previa de rutas.")

    render_divider()
    if secondary("Volver al inicio", key="role_back"):
        st.session_state.vista = VISTA_HOME
        st.session_state.modo = None
        st.session_state.rol = None
        st.rerun()

    render_footer()
