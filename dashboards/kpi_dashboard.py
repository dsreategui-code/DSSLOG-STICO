"""Panel de indicadores principales (KPIs) de una jornada simulada."""
import streamlit as st
from components.cards import kpi_row
from utils.formatters import fmt_pct, fmt_minutes, fmt_num, fmt_int


def render_kpi_dashboard(kpis: dict, replan_stats: dict = None):
    """Renderiza la fila de KPIs principales y, debajo, los secundarios."""
    if not kpis:
        st.info("Aun no hay indicadores calculados.")
        return

    fila_1 = [
        {"label": "OTD", "value": fmt_pct(kpis.get("otd")),
         "helptext": "Entregas a tiempo / entregas completadas"},
        {"label": "OTIF", "value": fmt_pct(kpis.get("otif")),
         "helptext": "Entregas perfectas sobre total de pedidos"},
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
        {"label": "Coef. variacion", "value": fmt_pct(kpis.get("coef_variacion_pct"))},
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
