"""Pantalla inicial - seleccion de modo."""
import streamlit as st
from components.layout import render_view_title, render_divider, render_footer
from components.cards import info_card, feature_card
from utils.constants import (
    MODO_VALIDACION, MODO_DEMOSTRACION,
    VISTA_VALIDATION_DATA, VISTA_DEMO_ROLE_SELECTION,
)


def render():
    render_view_title(
        "Plataforma de apoyo a la decision",
        "Sistema para reducir la variabilidad de los tiempos de entrega estimados en "
        "la ultima milla. Distribucion de colchones desde Callao hacia Lima Metropolitana, "
        "jornada de 09:00 a 19:00, flota de diez vehiculos.",
        eyebrow="Ultima Milla  /  Lima Metropolitana",
    )

    st.write("")
    col1, col2 = st.columns(2, gap="large")

    with col1:
        feature_card(
            eyebrow="01  /  Validacion",
            title="Experimento controlado",
            description=(
                "Ejecuta Monte Carlo sobre el dataset sintetico de 80 pedidos y 10 vehiculos. "
                "Compara escenarios (sin DSS, ruta optimizada y DSS completo), mide variabilidad "
                "y respalda la propuesta del sistema con evidencia cuantitativa."
            ),
        )
        if st.button("Ingresar a validacion", key="home_val",
                     type="primary", use_container_width=True):
            st.session_state.modo = MODO_VALIDACION
            st.session_state.rol = None
            st.session_state.vista = VISTA_VALIDATION_DATA
            st.rerun()

    with col2:
        feature_card(
            eyebrow="02  /  Demostracion interactiva",
            title="Recorrido del DSS",
            description=(
                "Opera el sistema como Supervisor para gestionar la jornada completa "
                "o como Conductor para consultar tu ruta asignada y los enlaces de navegacion. "
                "Toma decisiones reales sobre las replanificaciones intravehiculo."
            ),
        )
        if st.button("Ingresar a demostracion", key="home_demo",
                     type="primary", use_container_width=True):
            st.session_state.modo = MODO_DEMOSTRACION
            st.session_state.rol = None
            st.session_state.vista = VISTA_DEMO_ROLE_SELECTION
            st.rerun()

    render_divider()

    col_a, col_b, col_c = st.columns(3, gap="medium")
    with col_a:
        info_card(
            "Contexto operativo",
            "Salida unica desde el almacen en Callao. Variabilidad por trafico, "
            "estacionamiento, accesibilidad e incidencias.",
            eyebrow="Alcance",
        )
    with col_b:
        info_card(
            "Logica del DSS",
            "Optimizacion inicial de rutas, simulacion estocastica de la jornada y "
            "replanificacion intravehiculo de pedidos pendientes sin reasignacion entre flotas.",
            eyebrow="Modelo",
        )
    with col_c:
        info_card(
            "Indicador clave",
            "Evolucion del OTD durante la operacion, calculado como "
            "entregas a tiempo acumuladas sobre entregas completadas acumuladas.",
            eyebrow="Metricas",
        )

    render_footer()
