"""Evolucion del servicio durante la jornada."""
import streamlit as st
import pandas as pd

from components.charts import chart_otd_evolution, chart_estados_distribucion


def render_service_evolution(evolucion: pd.DataFrame, entregas: pd.DataFrame = None):
    """Renderiza el grafico obligatorio de evolucion del OTD."""
    if evolucion is None or evolucion.empty:
        st.info("Aun no hay evolucion del OTD para mostrar.")
        return

    st.plotly_chart(chart_otd_evolution(evolucion),
                    use_container_width=True, key="se_otd_evol")
    st.caption(
        "OTD(t) = entregas a tiempo acumuladas / entregas completadas acumuladas x 100"
    )

    if entregas is not None and not entregas.empty:
        st.plotly_chart(chart_estados_distribucion(entregas),
                        use_container_width=True, key="se_estados")
