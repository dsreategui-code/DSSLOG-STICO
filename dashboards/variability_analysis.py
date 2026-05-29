"""Analisis de variabilidad y estabilidad operativa."""
import streamlit as st
import pandas as pd

from components.charts import chart_boxplot_delivery_times, chart_variability_otd
from utils.formatters import fmt_pct, fmt_minutes


def render_variability_analysis(entregas: pd.DataFrame, iteraciones: pd.DataFrame = None,
                                kpis: dict = None):
    """Boxplots de retrasos por vehiculo/escenario + estadisticas de estabilidad."""
    if entregas is None or entregas.empty:
        st.info("Sin entregas registradas para analizar variabilidad.")
        return

    st.plotly_chart(chart_boxplot_delivery_times(entregas),
                    use_container_width=True, key="va_boxplot")

    if iteraciones is not None and not iteraciones.empty:
        st.plotly_chart(chart_variability_otd(iteraciones),
                        use_container_width=True, key="va_var_otd")

    if kpis:
        cv = kpis.get("coef_variacion_pct")
        cv_str = "No aplicable" if cv is None else fmt_pct(cv)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Desviacion estandar", fmt_minutes(kpis.get("desviacion_estandar_min")))
        with col2:
            st.metric("Coeficiente de variacion", cv_str,
                      help="CV = desv estandar / promedio. No aplicable cuando el "
                           "promedio del retraso es menor a 1 minuto.")
        with col3:
            st.metric("Retraso maximo", fmt_minutes(kpis.get("retraso_maximo_min")))

    st.markdown("**Resumen estadistico del retraso por vehiculo**")
    resumen = entregas.groupby("vehiculo_id")["retraso_min"].describe()[
        ["count", "mean", "std", "min", "50%", "max"]
    ].rename(columns={
        "count": "Entregas",
        "mean": "Retraso prom",
        "std": "Desv. estandar",
        "min": "Min",
        "50%": "Mediana",
        "max": "Max",
    }).round(1).reset_index().rename(columns={"vehiculo_id": "Vehiculo"})
    st.dataframe(resumen, hide_index=True, use_container_width=True)
