"""Vista del Conductor - vehiculo, ruta, mapa y enlaces de navegacion."""
import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

from components.layout import (
    render_view_title, render_divider, render_footer, render_empty_state,
)
from components.buttons import secondary
from components.cards import kpi_row
from maps.route_maps import mapa_rutas
from maps.waze_links import waze_links_for_route
from utils.constants import VISTA_DEMO_ROLE_SELECTION


def render():
    render_view_title(
        "Ruta asignada",
        "Selecciona tu vehiculo para ver la secuencia del dia, el mapa de la ruta "
        "y los enlaces de navegacion para cada parada.",
        eyebrow="Conductor",
    )

    rutas = st.session_state.get("rutas_finales") or st.session_state.get("rutas_iniciales")
    dataset = st.session_state.get("dataset")

    if not rutas:
        render_empty_state(
            "Aun no hay rutas asignadas",
            "El Supervisor debe generar las rutas antes de que el conductor pueda consultarlas.",
        )
        render_divider()
        if secondary("Cambiar de rol", key="drv_back"):
            st.session_state.vista = VISTA_DEMO_ROLE_SELECTION
            st.rerun()
        render_footer()
        return

    vehiculos = dataset.get("vehiculos") if dataset else None
    pedidos = dataset.get("pedidos") if dataset else None
    if vehiculos is None or vehiculos.empty or pedidos is None:
        render_empty_state(
            "Sin flota o pedidos disponibles",
            "Carga el dataset para mostrar la ruta.",
        )
        render_footer()
        return

    opciones = vehiculos["vehiculo_id"].tolist()
    actual = st.session_state.get("vehiculo_conductor")
    idx = opciones.index(actual) if actual in opciones else 0
    seleccionado = st.selectbox("Selecciona tu vehiculo", opciones, index=idx)
    st.session_state.vehiculo_conductor = seleccionado

    veh = vehiculos[vehiculos["vehiculo_id"] == seleccionado].iloc[0]
    ruta_veh = rutas.get(seleccionado, {})
    secuencia = ruta_veh.get("secuencia", []) if isinstance(ruta_veh, dict) else getattr(ruta_veh, "secuencia", [])

    kpi_row([
        {"label": "Vehiculo", "value": str(veh.get("placa", "-"))},
        {"label": "Conductor", "value": str(veh.get("conductor", "-"))},
        {"label": "Zona preferente", "value": str(veh.get("zona_preferente", "-"))},
        {"label": "Pedidos del dia", "value": len(secuencia)},
    ])

    if not secuencia:
        render_empty_state(
            "Tu vehiculo no tiene pedidos asignados",
            "Solicita al supervisor que regenere las rutas.",
        )
        render_footer()
        return

    st.write("")
    tab_mapa, tab_paradas = st.tabs(["Mapa de la ruta", "Paradas y navegacion"])

    with tab_mapa:
        mapa = mapa_rutas(rutas, pedidos, vehiculo_id=seleccionado, modo="ruta")
        st_folium(mapa, height=520, use_container_width=True, returned_objects=[])

    with tab_paradas:
        paradas = waze_links_for_route(secuencia, pedidos)
        if not paradas:
            st.info("No hay paradas para mostrar.")
        else:
            for p in paradas:
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.markdown(f"""
                    <div class="dss-card" style="margin-bottom:0.5rem;">
                      <div class="dss-eyebrow">Parada {p['orden']:02d}</div>
                      <div class="dss-card-title">{p['pedido_id']}  &middot;  {p['cliente']}</div>
                      <div class="dss-card-desc">
                        {p['direccion']}  &middot;  {p['distrito']}<br>
                        Ventana <strong>{p['ventana']}</strong>  &middot;  Tipo {p['tipo_servicio']}
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_b:
                    st.link_button("Abrir en Waze", p["url_waze"], use_container_width=True)

    render_divider()
    if secondary("Cambiar de rol", key="drv_back_2"):
        st.session_state.vista = VISTA_DEMO_ROLE_SELECTION
        st.rerun()

    render_footer()
