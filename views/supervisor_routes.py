"""Supervisor - Generacion y revision de rutas iniciales.

El filtro de vehiculo es coherente entre mapa, KPI cards y tabla de secuencia:
- "Todos" muestra resumen global, mapa completo y tabla con toda la flota.
- Un vehiculo concreto muestra solo sus KPIs, su ruta en el mapa y su tabla.
"""
from dataclasses import asdict
import streamlit as st
from streamlit_folium import st_folium

from components.layout import (
    render_view_title, render_divider, render_footer, render_empty_state,
)
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.cards import kpi_row
from optimization.route_optimizer import (
    Ruta, construir_rutas_iniciales, rutas_to_dataframe,
)
from maps.route_maps import mapa_rutas
from utils.state import log_bitacora
from utils.formatters import fmt_km, fmt_minutes, fmt_kg
from utils.constants import (
    VISTA_SUPERVISOR_CONFIG, VISTA_SUPERVISOR_SIMULATION,
)


def _to_ruta_objs(rutas_dict: dict) -> dict:
    """Convierte el dict de session_state (dicts) en objetos Ruta."""
    out = {}
    for v, r in rutas_dict.items():
        if isinstance(r, dict):
            out[v] = Ruta(
                vehiculo_id=r.get("vehiculo_id", v),
                secuencia=list(r.get("secuencia", [])),
                distancia_km=float(r.get("distancia_km", 0.0)),
                tiempo_min=float(r.get("tiempo_min", 0.0)),
                carga_unidades=int(r.get("carga_unidades", 0)),
                carga_kg=float(r.get("carga_kg", 0.0)),
            )
        else:
            out[v] = r
    return out


def _kpis_global(rutas: dict) -> list:
    total_dist = sum(r.get("distancia_km", 0) for r in rutas.values())
    total_tiempo = sum(r.get("tiempo_min", 0) for r in rutas.values())
    total_carga = sum(r.get("carga_unidades", 0) for r in rutas.values())
    asignados = sum(1 for r in rutas.values() if r.get("secuencia"))
    return [
        {"label": "Vehiculos asignados", "value": f"{asignados} / {len(rutas)}"},
        {"label": "Pedidos asignados", "value": total_carga},
        {"label": "Distancia total", "value": fmt_km(total_dist)},
        {"label": "Tiempo estimado (suma)", "value": fmt_minutes(total_tiempo)},
    ]


def _kpis_vehiculo(rutas: dict, veh_id: str, vehiculos_df) -> list:
    r = rutas.get(veh_id, {})
    info = vehiculos_df[vehiculos_df["vehiculo_id"] == veh_id]
    placa = str(info["placa"].iloc[0]) if not info.empty else veh_id
    return [
        {"label": "Vehiculo", "value": placa},
        {"label": "Pedidos asignados", "value": r.get("carga_unidades", 0)},
        {"label": "Carga", "value": fmt_kg(r.get("carga_kg", 0))},
        {"label": "Distancia / tiempo",
         "value": f"{fmt_km(r.get('distancia_km', 0))}  /  {fmt_minutes(r.get('tiempo_min', 0))}"},
    ]


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
            with st.spinner("Optimizando rutas con OR-Tools..."):
                rutas = construir_rutas_iniciales(
                    pedidos, vehiculos,
                    velocidad_kmh=float(cfg.get("velocidad_kmh", 18.0)),
                    motor="auto",
                    jornada_inicio=cfg.get("jornada_inicio", "09:00"),
                    jornada_fin=cfg.get("jornada_fin", "19:00"),
                )
            st.session_state.rutas_iniciales = {v: asdict(r) for v, r in rutas.items()}
            log_bitacora(
                "Supervisor - rutas iniciales generadas",
                f"{sum(1 for r in rutas.values() if r.secuencia)} de {len(rutas)} "
                f"vehiculos con pedidos asignados",
            )
            st.success("Rutas iniciales generadas.")

    rutas = st.session_state.get("rutas_iniciales")
    if not rutas:
        render_empty_state(
            "Aun no hay rutas generadas",
            "Presiona Generar rutas iniciales para comenzar.",
        )
        render_divider()
        if secondary("Configuracion", key="sup_rutas_back"):
            st.session_state.vista = VISTA_SUPERVISOR_CONFIG
            st.rerun()
        render_footer()
        return

    # Selector de vehiculo - controla mapa, KPIs y tabla simultaneamente
    opciones = list(rutas.keys())
    seleccion = st.selectbox(
        "Vehiculo a visualizar",
        ["Todos"] + opciones,
        key="sup_rutas_sel",
        help="Filtra el mapa, las metricas y la tabla por el vehiculo seleccionado.",
    )
    veh_id = None if seleccion == "Todos" else seleccion

    # KPIs sincronizados con la seleccion
    if veh_id is None:
        kpi_row(_kpis_global(rutas))
    else:
        kpi_row(_kpis_vehiculo(rutas, veh_id, vehiculos))

    st.write("")

    # Mapa sincronizado
    mapa = mapa_rutas(rutas, pedidos, vehiculo_id=veh_id, modo="iniciales")
    st_folium(mapa, height=520, use_container_width=True, returned_objects=[])

    # Tabla sincronizada
    titulo_tabla = "Detalle por vehiculo" if veh_id is None else f"Detalle de {veh_id}"
    st.markdown(f"**{titulo_tabla}**")

    rutas_obj = _to_ruta_objs(rutas)
    df_rutas = rutas_to_dataframe(rutas_obj)
    if not df_rutas.empty:
        if veh_id is not None:
            df_rutas = df_rutas[df_rutas["vehiculo_id"] == veh_id]
        ped_info = pedidos[["pedido_id", "cliente", "distrito", "zona",
                            "tipo_servicio", "ventana_inicio", "ventana_fin"]]
        df_rutas = df_rutas.merge(ped_info, on="pedido_id", how="left")
        st.dataframe(df_rutas, hide_index=True, use_container_width=True, height=320)
    else:
        st.info("Ningun vehiculo tiene pedidos asignados.")

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
