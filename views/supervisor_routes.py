"""Supervisor - Generacion y revision de rutas iniciales."""
from dataclasses import asdict
import streamlit as st
from streamlit_folium import st_folium

from components.layout import render_view_title, render_divider, render_footer, render_empty_state
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.cards import kpi_row
from optimization.route_optimizer import construir_rutas_iniciales, rutas_to_dataframe
from maps.route_maps import mapa_rutas
from utils.state import log_bitacora
from utils.formatters import fmt_km, fmt_minutes
from utils.constants import (
    VISTA_SUPERVISOR_CONFIG, VISTA_SUPERVISOR_SIMULATION,
)


def render():
    render_view_title(
        "Rutas iniciales",
        "Genera la asignacion inicial de pedidos por vehiculo y revisala antes "
        "de ejecutar la jornada simulada."
    )
    render_step_breadcrumb()

    dataset = st.session_state.get("dataset")
    cfg = st.session_state.get("configuracion") or {}
    if not dataset or not cfg:
        st.warning("Falta dataset o configuracion. Vuelve a las pantallas anteriores.")
        render_footer()
        return

    pedidos = dataset["pedidos"]
    vehiculos = dataset["vehiculos"]

    col_a, col_b = st.columns([1, 3])
    with col_a:
        if primary("Generar rutas iniciales", key="sup_gen_rutas",
                   use_container_width=True):
            motor = cfg.get("motor_optimizacion", "auto")
            with st.spinner(f"Optimizando rutas ({motor})..."):
                rutas = construir_rutas_iniciales(
                    pedidos, vehiculos,
                    velocidad_kmh=float(cfg.get("velocidad_kmh", 18.0)),
                    motor=motor,
                    jornada_inicio=cfg.get("jornada_inicio", "09:00"),
                    jornada_fin=cfg.get("jornada_fin", "19:00"),
                )
            st.session_state.rutas_iniciales = {v: asdict(r) for v, r in rutas.items()}
            log_bitacora("Supervisor - rutas iniciales generadas",
                         f"{len(rutas)} vehiculos asignados")
            st.success("Rutas iniciales generadas.")

    rutas = st.session_state.get("rutas_iniciales")
    if not rutas:
        render_empty_state(
            "Aun no hay rutas generadas",
            "Presiona &laquo;Generar rutas iniciales&raquo; para comenzar.",
        )
        render_divider()
        if secondary("Configuracion", key="sup_rutas_back"):
            st.session_state.vista = VISTA_SUPERVISOR_CONFIG
            st.rerun()
        render_footer()
        return

    # Resumen agregado
    total_dist = sum(r.get("distancia_km", 0) for r in rutas.values())
    total_tiempo = sum(r.get("tiempo_min", 0) for r in rutas.values())
    total_carga = sum(r.get("carga_unidades", 0) for r in rutas.values())
    kpi_row([
        {"label": "Vehiculos asignados", "value": sum(1 for r in rutas.values() if r.get("secuencia"))},
        {"label": "Pedidos asignados", "value": total_carga},
        {"label": "Distancia total", "value": fmt_km(total_dist)},
        {"label": "Tiempo estimado (suma)", "value": fmt_minutes(total_tiempo)},
    ])

    st.write("")
    opciones = list(rutas.keys())
    seleccion = st.selectbox("Selecciona el vehiculo a visualizar",
                             ["Todos"] + opciones, key="sup_rutas_sel")
    veh_id = None if seleccion == "Todos" else seleccion

    mapa = mapa_rutas(rutas, pedidos, vehiculo_id=veh_id, modo="iniciales")
    st_folium(mapa, height=520, use_container_width=True, returned_objects=[])

    st.markdown("**Detalle por vehiculo**")
    df_rutas = rutas_to_dataframe(
        {v: type("R", (), r)() if isinstance(r, dict) and not hasattr(r, "secuencia")
         else r for v, r in rutas.items()}
    )
    if not df_rutas.empty:
        ped_info = pedidos[["pedido_id", "cliente", "distrito", "zona",
                            "tipo_servicio", "ventana_inicio", "ventana_fin"]]
        df_rutas = df_rutas.merge(ped_info, on="pedido_id", how="left")
        st.dataframe(df_rutas, hide_index=True, use_container_width=True, height=320)

    render_divider()
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Configuracion", key="sup_rutas_back_2",
                     use_container_width=True):
            st.session_state.vista = VISTA_SUPERVISOR_CONFIG
            st.rerun()
    with col_r:
        if primary("Simulacion", key="sup_rutas_next",
                   use_container_width=True):
            navigate_to(VISTA_SUPERVISOR_SIMULATION)

    render_footer()
