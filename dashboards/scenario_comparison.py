"""Comparacion de escenarios (sin DSS / ruta optimizada / DSS completo)."""
import streamlit as st
import pandas as pd

from components.charts import chart_scenario_comparison, chart_variability_otd
from utils.formatters import fmt_pct, fmt_num


def render_scenario_comparison(kpis_por_escenario: pd.DataFrame,
                               iteraciones: pd.DataFrame,
                               resumen: pd.DataFrame):
    """Renderiza graficos y tabla con la comparacion de escenarios."""
    if kpis_por_escenario is None or kpis_por_escenario.empty:
        st.info("Aun no hay resultados por escenario para comparar.")
        return

    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.plotly_chart(
            chart_scenario_comparison(kpis_por_escenario, "otd", "OTD (%)"),
            use_container_width=True, key="sc_otd",
        )
    with col_r:
        st.plotly_chart(
            chart_scenario_comparison(kpis_por_escenario, "coef_variacion_pct",
                                       "Coef. variacion (%)"),
            use_container_width=True, key="sc_cv",
        )

    if iteraciones is not None and not iteraciones.empty:
        st.plotly_chart(chart_variability_otd(iteraciones),
                        use_container_width=True, key="sc_var_otd")

    if resumen is not None and not resumen.empty:
        st.markdown("**Resumen por escenario (promedio sobre iteraciones)**")
        view = resumen.rename(columns={
            "escenario": "Escenario",
            "otd_prom": "OTD prom (%)",
            "otd_std": "OTD desv (%)",
            "otif_prom": "OTIF prom (%)",
            "retraso_prom": "Retraso prom (min)",
            "cv_prom": "CV prom (%)",
            "cv_otd_pct": "CV OTD (%)",
            "n": "Iteraciones",
        })
        st.dataframe(view, hide_index=True, use_container_width=True)
