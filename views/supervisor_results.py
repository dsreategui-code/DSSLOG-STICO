"""Supervisor - Resultados de la jornada (bloques navegables)."""
import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

from components.layout import (
    render_view_title, render_divider, render_footer, render_empty_state,
)
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.cards import kpi_row, info_card
from components.filters import render_filters, apply_filters
from dashboards.kpi_dashboard import render_kpi_dashboard, render_service_time_breakdown
from dashboards.service_evolution import render_service_evolution
from dashboards.vehicle_performance import render_vehicle_performance
from dashboards.variability_analysis import render_variability_analysis
from components.charts import chart_replanificaciones, chart_alerts_by_type
from maps.route_maps import mapa_rutas
from simulation.metrics import (
    compute_kpis, compute_otd_evolution,
    compute_replanning_stats, compute_service_time_metrics,
)
from simulation.replanning import (
    info_replanificacion_vehiculo, vehiculos_con_replanificacion,
    tabla_comparativa_secuencia,
)
from utils.formatters import fmt_pct, fmt_minutes
from utils.constants import (
    VISTA_SUPERVISOR_SIMULATION, VISTA_SUPERVISOR_EXPORT,
)


def _delta_dir(value, prefer_negative: bool = False) -> str:
    """Devuelve 'up'/'down'/'flat' segun el signo. prefer_negative=True
    cuando el valor menor representa una mejora (ej. delta de tiempo)."""
    if value is None:
        return "flat"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "flat"
    if prefer_negative:
        if v < -0.05:
            return "up"
        if v > 0.05:
            return "down"
        return "flat"
    if v > 0.05:
        return "up"
    if v < -0.05:
        return "down"
    return "flat"


def _render_cards_comparacion(info: dict):
    """Cards de mejora cuando un vehiculo tuvo replanificacion."""
    delta_t = info.get("delta_tiempo_min")
    delta_otd = info.get("delta_otd")
    delta_t_str = (
        f"{delta_t:+.1f} min" if delta_t is not None else "-"
    )
    delta_otd_str = (
        f"{delta_otd:+.1f}%" if delta_otd is not None else "-"
    )

    kpi_row([
        {"label": "Tiempo antes",
         "value": fmt_minutes(info.get("tiempo_antes_min"))},
        {"label": "Tiempo despues",
         "value": fmt_minutes(info.get("tiempo_despues_min"))},
        {"label": "Diferencia de tiempo",
         "value": delta_t_str,
         "delta_dir": _delta_dir(delta_t, prefer_negative=True)},
    ])
    st.write("")
    otd_antes = info.get("otd_antes")
    otd_despues = info.get("otd_despues")
    kpi_row([
        {"label": "OTD antes",
         "value": fmt_pct(otd_antes) if otd_antes is not None else "-"},
        {"label": "OTD despues",
         "value": fmt_pct(otd_despues) if otd_despues is not None else "-",
         "delta": delta_otd_str if delta_otd is not None else None,
         "delta_dir": _delta_dir(delta_otd)},
        {"label": "Pedidos recuperados",
         "value": info.get("pedidos_recuperados", 0)},
    ])


def _render_tab_comparacion(rutas_ini: dict, rutas_fin: dict,
                            pedidos: pd.DataFrame,
                            alertas: list, decisiones: list,
                            entregas: pd.DataFrame):
    """Renderiza la pestania 'Ruta inicial vs final' con dos mapas lado a lado."""
    if not rutas_ini or not rutas_fin:
        st.info("No hay comparacion de rutas disponible.")
        return

    veh_replan = vehiculos_con_replanificacion(rutas_ini, rutas_fin)
    opciones = list(rutas_ini.keys())

    col_sel, col_chip = st.columns([2, 5])
    with col_sel:
        sel = st.selectbox(
            "Vehiculo a comparar", ["Todos"] + opciones,
            key="sup_res_compare",
            help="Filtra para ver la comparacion de un vehiculo especifico.",
        )
    with col_chip:
        if veh_replan:
            st.caption(
                f"Vehiculos con replanificacion intravehiculo aplicada: "
                f"**{len(veh_replan)}** ({', '.join(veh_replan)})"
            )
        else:
            st.caption("Ningun vehiculo tuvo replanificacion aprobada en esta jornada.")

    if sel == "Todos":
        # Vista global: dos mapas con todas las rutas
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("**Rutas iniciales**")
            mapa_i = mapa_rutas(rutas_ini, pedidos, vehiculo_id=None,
                                modo="iniciales")
            st_folium(mapa_i, height=460, use_container_width=True,
                      returned_objects=[], key="sup_res_map_ini_all")
        with col_r:
            st.markdown("**Rutas finales (post replanificacion)**")
            mapa_f = mapa_rutas(rutas_fin, pedidos, vehiculo_id=None,
                                modo="finales", entregas=entregas)
            st_folium(mapa_f, height=460, use_container_width=True,
                      returned_objects=[], key="sup_res_map_fin_all")
        return

    # Vista por vehiculo
    info = info_replanificacion_vehiculo(
        sel, rutas_ini, rutas_fin, alertas=alertas, decisiones=decisiones,
    )

    if not info["tuvo_replanificacion"]:
        # Card explicativa + un solo mapa
        info_card(
            "Sin replanificacion",
            f"El vehiculo {sel} no tuvo replanificacion de ruta. "
            f"Su ruta final coincide con la inicial.",
            eyebrow="Vehiculo sin cambios",
        )
        st.write("")
        st.markdown("**Ruta del vehiculo**")
        mapa_uno = mapa_rutas(rutas_ini, pedidos, vehiculo_id=sel,
                              modo="iniciales", entregas=entregas)
        st_folium(mapa_uno, height=480, use_container_width=True,
                  returned_objects=[], key=f"sup_res_map_solo_{sel}")
        return

    # Vehiculo CON replanificacion: dos mapas + cards + tabla comparativa
    _render_cards_comparacion(info)
    st.write("")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Ruta inicial**")
        mapa_i = mapa_rutas(rutas_ini, pedidos, vehiculo_id=sel,
                            modo="iniciales")
        st_folium(mapa_i, height=440, use_container_width=True,
                  returned_objects=[], key=f"sup_res_map_ini_{sel}")
    with col_r:
        st.markdown("**Ruta replanificada (final)**")
        mapa_f = mapa_rutas(rutas_fin, pedidos, vehiculo_id=sel,
                            modo="finales", entregas=entregas)
        st_folium(mapa_f, height=440, use_container_width=True,
                  returned_objects=[], key=f"sup_res_map_fin_{sel}")

    st.write("")
    st.markdown("**Tabla comparativa de secuencia**")
    tabla = tabla_comparativa_secuencia(
        info["secuencia_inicial"], info["secuencia_final"], pedidos,
    )
    if tabla.empty:
        st.caption("Sin paradas que comparar.")
    else:
        view = tabla.rename(columns={
            "orden": "Orden",
            "pedido_inicial": "Pedido (inicial)",
            "pedido_final": "Pedido (final)",
            "distrito": "Distrito",
            "ventana": "Ventana",
            "cambio": "Cambio",
        })
        st.dataframe(view, hide_index=True, use_container_width=True,
                     height=min(420, 60 + len(view) * 36))


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
    filtros = render_filters(entregas, key_prefix="sup_res", show_escenario=False)
    entregas_filtradas = (
        apply_filters(entregas, filtros) if not entregas.empty else entregas
    )

    kpis_filtrados = compute_kpis(entregas_filtradas, alertas=res.get("alertas", []))
    evolucion_filtrada = compute_otd_evolution(entregas_filtradas)
    service_metrics = compute_service_time_metrics(entregas_filtradas)

    tabs = st.tabs([
        "1. Indicadores",
        "2. Ruta inicial vs final",
        "3. Evolucion del servicio",
        "4. Desempeno por vehiculo",
        "5. Alertas y replanificaciones",
        "6. Detalle de entregas",
    ])

    decisiones = st.session_state.get("decisiones_supervisor", [])
    alertas = st.session_state.get("alertas", []) or res.get("alertas", []) or []
    replan_stats = compute_replanning_stats(decisiones)

    with tabs[0]:
        render_kpi_dashboard(kpis_filtrados, replan_stats,
                             service_metrics=service_metrics)
        st.write("")
        render_service_time_breakdown(service_metrics)

    with tabs[1]:
        rutas_ini = st.session_state.get("rutas_iniciales") or res.get("rutas_iniciales")
        rutas_fin = st.session_state.get("rutas_finales") or res.get("rutas_finales")
        _render_tab_comparacion(rutas_ini, rutas_fin, dataset["pedidos"],
                                alertas, decisiones, entregas_filtradas)

    with tabs[2]:
        render_service_evolution(evolucion_filtrada, entregas_filtradas)

    with tabs[3]:
        render_vehicle_performance(entregas_filtradas, dataset.get("vehiculos"))

    with tabs[4]:
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(chart_replanificaciones(replan_stats),
                            use_container_width=True, key="sr_replan")
        with col_b:
            if alertas:
                df_alertas = pd.DataFrame(
                    [{"tipo": "Replanificacion intravehiculo"} for _ in alertas]
                )
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
