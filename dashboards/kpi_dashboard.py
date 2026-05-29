"""Panel de indicadores principales (KPIs) de una jornada simulada."""
import pandas as pd
import streamlit as st

from components.cards import kpi_row
from utils.formatters import fmt_pct, fmt_minutes, fmt_num, fmt_int


def _fmt_cv(value) -> str:
    """Formatea el coeficiente de variacion. None -> 'No aplicable'."""
    if value is None:
        return "No aplicable"
    try:
        return fmt_pct(float(value))
    except (TypeError, ValueError):
        return "No aplicable"


def render_kpi_dashboard(kpis: dict, replan_stats: dict = None,
                         service_metrics: dict = None):
    """Renderiza filas de KPIs principales, secundarios y de tiempo de servicio.

    Args:
        kpis: dict producido por simulation.metrics.compute_kpis.
        replan_stats: dict producido por compute_replanning_stats (opcional).
        service_metrics: dict producido por compute_service_time_metrics (opcional).
    """
    if not kpis:
        st.info("Aun no hay indicadores calculados con los filtros actuales.")
        return

    fila_1 = [
        {"label": "OTD", "value": fmt_pct(kpis.get("otd")),
         "helptext": "Entregas a tiempo / entregas completadas"},
        {"label": "OTIF", "value": fmt_pct(kpis.get("otif")),
         "helptext": "Entregas a tiempo sobre total de pedidos"},
        {"label": "Exito 1er intento", "value": fmt_pct(kpis.get("exito_primer_intento"))},
        {"label": "A tiempo", "value": fmt_int(kpis.get("entregas_a_tiempo"))},
        {"label": "Fuera de ventana", "value": fmt_int(kpis.get("entregas_fuera_ventana"))},
        {"label": "Fallidas", "value": fmt_int(kpis.get("entregas_fallidas"))},
    ]
    kpi_row(fila_1)
    st.write("")

    fila_2 = [
        {"label": "Tiempo total op.", "value": fmt_minutes(kpis.get("tiempo_total_operacion_min"))},
        {"label": "Tiempo prom. entrega", "value": fmt_minutes(kpis.get("tiempo_promedio_entrega_min"))},
        {"label": "Tiempo prom. parada", "value": fmt_minutes(kpis.get("tiempo_promedio_parada_min"))},
        {"label": "Retraso prom.", "value": fmt_minutes(kpis.get("retraso_promedio_min"))},
        {"label": "Retraso max.", "value": fmt_minutes(kpis.get("retraso_maximo_min"))},
        {"label": "Coef. variacion",
         "value": _fmt_cv(kpis.get("coef_variacion_pct")),
         "helptext": "CV = desv estandar / promedio. No aplicable si el promedio es < 1 min."},
    ]
    kpi_row(fila_2)
    st.write("")

    fila_3 = [
        {"label": "Pedidos totales", "value": fmt_int(kpis.get("total_pedidos"))},
        {"label": "Pedidos pendientes", "value": fmt_int(kpis.get("pedidos_pendientes"))},
        {"label": "Replanificadas", "value": fmt_int(kpis.get("entregas_replanificadas"))},
        {"label": "Alertas", "value": fmt_int(kpis.get("alertas_generadas"))},
        {"label": "Sugeridas", "value": fmt_int((replan_stats or {}).get("sugeridas", 0))},
        {"label": "Aprobadas", "value": fmt_int((replan_stats or {}).get("aprobadas", 0))},
    ]
    kpi_row(fila_3)

    # Bloque de tiempo de servicio (si se proporciona)
    if service_metrics:
        st.write("")
        st.markdown("**Tiempo de servicio**")
        fila_serv = [
            {"label": "Servicio total",
             "value": fmt_minutes(service_metrics.get("servicio_total_min"))},
            {"label": "Servicio promedio",
             "value": fmt_minutes(service_metrics.get("servicio_promedio_min"))},
            {"label": "% jornada en servicio",
             "value": fmt_pct(service_metrics.get("servicio_pct_jornada"))},
        ]
        kpi_row(fila_serv)


def render_service_time_breakdown(service_metrics: dict):
    """Renderiza tablas de tiempo de servicio por vehiculo y por tipo + OTD."""
    if not service_metrics:
        st.info("No hay metricas de tiempo de servicio disponibles.")
        return

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Tiempo de servicio por vehiculo**")
        df_v = service_metrics.get("por_vehiculo")
        if df_v is None or (hasattr(df_v, "empty") and df_v.empty):
            st.caption("Sin datos de servicio por vehiculo.")
        else:
            view = df_v.rename(columns={
                "vehiculo_id": "Vehiculo",
                "servicio_total": "Servicio total (min)",
                "servicio_prom": "Promedio (min)",
                "n": "Paradas",
            })
            st.dataframe(view, hide_index=True, use_container_width=True, height=260)

    with col_r:
        st.markdown("**Tiempo de servicio y OTD por tipo**")
        df_t = service_metrics.get("por_tipo")
        if df_t is None or (hasattr(df_t, "empty") and df_t.empty):
            st.caption("Sin datos de servicio por tipo.")
        else:
            view = df_t.rename(columns={
                "tipo_servicio": "Tipo",
                "servicio_total": "Servicio total (min)",
                "servicio_prom": "Promedio (min)",
                "n": "Paradas",
                "otd_pct": "OTD (%)",
            })
            st.dataframe(view, hide_index=True, use_container_width=True, height=260)
