"""Supervisor - Resultados de la jornada (bloques navegables)."""
import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.filters import render_filters, apply_filters
from dashboards.kpi_dashboard import render_kpi_dashboard
from dashboards.service_evolution import render_service_evolution
from dashboards.vehicle_performance import render_vehicle_performance
from dashboards.variability_analysis import render_variability_analysis
from components.charts import chart_replanificaciones, chart_alerts_by_type
from maps.route_maps import mapa_comparativo
from simulation.metrics import compute_replanning_stats
from utils.constants import (
    VISTA_SUPERVISOR_SIMULATION, VISTA_SUPERVISOR_EXPORT,
)


def render():
    render_view_title(
        "Resultados de la jornada",
        "Indicadores de la operacion, comparacion ruta inicial vs final, evolucion "
        "del OTD, desempeno por vehiculo y registro de replanificaciones."
    )
    render_step_breadcrumb()

    res = st.session_state.get("resultados")
    dataset = st.session_state.get("dataset")
    if not res or not dataset:
        st.warning("Aun no hay resultados. Ejecuta la jornada.")
        render_footer()
        return

    entregas = res.get("entregas", pd.DataFrame())
    filtros = render_filters(entregas, key_prefix="sup_res")
    entregas_filtradas = apply_filters(entregas, filtros) if not entregas.empty else entregas

    tabs = st.tabs([
        "1. Indicadores",
        "2. Ruta inicial vs final",
        "3. Evolucion del servicio",
        "4. Desempeno por vehiculo",
        "5. Alertas y replanificaciones",
        "6. Detalle de entregas",
    ])

    decisiones = st.session_state.get("decisiones_supervisor", [])
    replan_stats = compute_replanning_stats(decisiones)

    with tabs[0]:
        render_kpi_dashboard(res.get("kpis", {}), replan_stats)

    with tabs[1]:
        rutas_ini = st.session_state.get("rutas_iniciales") or res.get("rutas_iniciales")
        rutas_fin = st.session_state.get("rutas_finales") or res.get("rutas_finales")
        if rutas_ini and rutas_fin:
            opciones = list(rutas_ini.keys())
            sel = st.selectbox("Vehiculo a comparar", ["Todos"] + opciones,
                               key="sup_res_compare")
            veh_id = None if sel == "Todos" else sel
            mapa = mapa_comparativo(rutas_ini, rutas_fin, dataset["pedidos"], vehiculo_id=veh_id)
            st_folium(mapa, height=480, use_container_width=True, returned_objects=[])
            st.caption("Linea continua = ruta inicial · Linea punteada = ruta final (post replanificacion).")
        else:
            st.info("No hay comparacion de rutas disponible.")

    with tabs[2]:
        render_service_evolution(res.get("evolucion_otd"), entregas_filtradas)

    with tabs[3]:
        render_vehicle_performance(entregas_filtradas, dataset.get("vehiculos"))

    with tabs[4]:
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(chart_replanificaciones(replan_stats),
                            use_container_width=True, key="sr_replan")
        with col_b:
            if res.get("alertas"):
                df_alertas = pd.DataFrame([{"tipo": "Replanificacion intravehiculo"} for _ in res["alertas"]])
                st.plotly_chart(chart_alerts_by_type(df_alertas),
                                use_container_width=True, key="sr_alerts_type")
            else:
                st.info("No se generaron alertas durante la jornada.")
        if decisiones:
            st.markdown("**Decisiones registradas**")
            df_dec = pd.DataFrame(decisiones)
            st.dataframe(df_dec, hide_index=True, use_container_width=True)

    with tabs[5]:
        if entregas_filtradas is None or entregas_filtradas.empty:
            st.info("No hay entregas que coincidan con los filtros aplicados.")
        else:
            cols = ["pedido_id", "vehiculo_id", "cliente", "zona", "tipo_servicio",
                    "ventana_inicio", "ventana_fin", "inicio_servicio_min",
                    "fin_servicio_min", "retraso_min", "estado", "incidencia"]
            cols = [c for c in cols if c in entregas_filtradas.columns]
            st.dataframe(entregas_filtradas[cols], hide_index=True,
                         use_container_width=True, height=460)

    render_divider()
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Simulacion", key="sup_res_back",
                     use_container_width=True):
            st.session_state.vista = VISTA_SUPERVISOR_SIMULATION
            st.rerun()
    with col_r:
        if primary("Exportacion", key="sup_res_next",
                   use_container_width=True):
            navigate_to(VISTA_SUPERVISOR_EXPORT)

    render_footer()
