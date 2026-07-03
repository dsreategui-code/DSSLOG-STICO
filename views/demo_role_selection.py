"""Hub de la Demostracion interactiva.

Reune la operacion visual (Gemelo Digital), el Motor de Decision (Planificacion CORTEX-LM,
transversal a todo el sistema) y el recorrido operativo por roles (Supervisor / Conductor).
"""
import streamlit as st
from components.layout import render_view_title, render_divider, render_footer
from components.cards import feature_card
from components.buttons import secondary
from utils.constants import (
    MODO_DEMOSTRACION, ROL_SUPERVISOR, ROL_CONDUCTOR,
    VISTA_DIGITAL_TWIN, VISTA_PLANNING, VISTA_SUPERVISOR_DATA, VISTA_DRIVER, VISTA_HOME,
)


def render():
    render_view_title(
        "Demostracion interactiva",
        "Observa la operacion en vivo con el Gemelo Digital, prepara la jornada con el Motor "
        "de Decision (transversal a todo el sistema) o recorre el flujo operativo por roles.",
        eyebrow="Demostracion",
    )

    # --- Operacion visual + motor de decision ---
    col1, col2 = st.columns(2, gap="large")
    with col1:
        feature_card(
            eyebrow="Operacion visual",
            title="Gemelo Digital Operativo",
            description=(
                "Reconstruccion simulada de la jornada en un mapa animado en vivo: rutas, "
                "vehiculos en movimiento, estado de pedidos, incidencias aleatorias y "
                "decisiones de re-ruteo por vehiculo (cada uno se paraliza y espera tu "
                "aprobacion sin detener a los demas). Gemelo operativo simulado."
            ),
        )
        if st.button("Abrir Gemelo Digital", key="hub_twin",
                     type="primary", use_container_width=True):
            st.session_state.modo = MODO_DEMOSTRACION
            st.session_state.rol = None
            st.session_state.vista = VISTA_DIGITAL_TWIN
            st.rerun()

    with col2:
        feature_card(
            eyebrow="Motor de decision (transversal)",
            title="Planificacion CORTEX-LM",
            description=(
                "Genera rutas candidatas por perfil de decision, las evalua por simulacion "
                "estocastica y recomienda una de forma explicable. Indicadores: robustez DRO "
                "(nominal vs peor caso), ranking por CVaR e IRI por pedido. Envia el escenario "
                "recomendado al Gemelo Digital."
            ),
        )
        if st.button("Abrir Motor de Decision", key="hub_plan",
                     type="secondary", use_container_width=True):
            st.session_state.modo = MODO_DEMOSTRACION
            st.session_state.rol = None
            st.session_state.vista = VISTA_PLANNING
            st.rerun()

    render_divider()
    st.markdown("#### Recorrido operativo por roles")

    # --- Roles operativos ---
    col3, col4 = st.columns(2, gap="large")
    with col3:
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
                     type="secondary", use_container_width=True):
            st.session_state.modo = MODO_DEMOSTRACION
            st.session_state.rol = ROL_SUPERVISOR
            st.session_state.vista = VISTA_SUPERVISOR_DATA
            st.rerun()

    with col4:
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
        if st.button("Ingresar como Conductor", key="rol_drv", type="secondary",
                     use_container_width=True, disabled=not rutas_listas):
            st.session_state.modo = MODO_DEMOSTRACION
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
