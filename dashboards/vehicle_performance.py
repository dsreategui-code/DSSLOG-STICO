"""Desempeno por vehiculo."""
import streamlit as st
import pandas as pd

from components.charts import (
    chart_vehicle_ranking, chart_capacity_usage, chart_orders_per_vehicle,
)
from simulation.metrics import compute_vehicle_performance


def render_vehicle_performance(entregas: pd.DataFrame, vehiculos: pd.DataFrame):
    df_veh = compute_vehicle_performance(entregas, vehiculos)
    if df_veh.empty:
        st.info("Sin datos de vehiculos con los filtros actuales.")
        return

    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(chart_vehicle_ranking(df_veh),
                        use_container_width=True, key="vp_ranking")
    with col_r:
        st.plotly_chart(chart_capacity_usage(df_veh),
                        use_container_width=True, key="vp_capacity")

    st.plotly_chart(chart_orders_per_vehicle(df_veh),
                    use_container_width=True, key="vp_orders")

    st.markdown("**Detalle por vehiculo**")
    cols = ["vehiculo_id", "pedidos_asignados", "a_tiempo", "completadas",
            "fallidas", "otd", "retraso_prom",
            "tiempo_servicio_total", "tiempo_servicio_prom",
            "uso_capacidad_pct", "uso_capacidad_kg_pct"]
    cols = [c for c in cols if c in df_veh.columns]
    view = df_veh[cols].rename(columns={
        "vehiculo_id": "Vehiculo",
        "pedidos_asignados": "Pedidos",
        "a_tiempo": "A tiempo",
        "completadas": "Completadas",
        "fallidas": "Fallidas",
        "otd": "OTD (%)",
        "retraso_prom": "Retraso prom (min)",
        "tiempo_servicio_total": "Servicio total (min)",
        "tiempo_servicio_prom": "Servicio prom (min)",
        "uso_capacidad_pct": "Uso unid. (%)",
        "uso_capacidad_kg_pct": "Uso kg (%)",
    })
    st.dataframe(view, hide_index=True, use_container_width=True)
