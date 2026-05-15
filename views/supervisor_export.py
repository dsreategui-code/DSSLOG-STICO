"""Supervisor - Exportacion de resultados, alertas y bitacora."""
from datetime import datetime
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb
from components.buttons import secondary
from services.export_service import (
    export_resultados_xlsx, export_dataframe_csv,
    export_alertas_csv, export_bitacora_csv, save_outputs_to_disk,
)
from utils.constants import VISTA_SUPERVISOR_RESULTS


def render():
    render_view_title(
        "Exportacion",
        "Descarga los resultados de la jornada, las alertas registradas y la bitacora "
        "de decisiones del supervisor en CSV o XLSX."
    )
    render_step_breadcrumb()

    res = st.session_state.get("resultados")
    if not res:
        st.warning("Aun no hay resultados para exportar.")
        render_footer()
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    paquete = {
        "kpis": res.get("kpis", {}),
        "entregas": res.get("entregas"),
        "evolucion_otd": res.get("evolucion_otd"),
        "alertas": st.session_state.get("alertas", []),
        "bitacora": st.session_state.get("bitacora", []),
        "rutas_iniciales": st.session_state.get("rutas_iniciales"),
        "rutas_finales": st.session_state.get("rutas_finales"),
    }

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.download_button(
            "Descargar XLSX consolidado",
            data=export_resultados_xlsx(paquete),
            file_name=f"jornada_resultados_{ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_b:
        st.download_button(
            "Descargar entregas (CSV)",
            data=export_dataframe_csv(paquete["entregas"]),
            file_name=f"jornada_entregas_{ts}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_c:
        st.download_button(
            "Descargar evolucion OTD (CSV)",
            data=export_dataframe_csv(paquete["evolucion_otd"]),
            file_name=f"jornada_evolucion_otd_{ts}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.write("")
    col_d, col_e = st.columns(2)
    with col_d:
        st.download_button(
            "Descargar alertas (CSV)",
            data=export_alertas_csv(paquete["alertas"]),
            file_name=f"jornada_alertas_{ts}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not paquete["alertas"],
        )
    with col_e:
        st.download_button(
            "Descargar bitacora (CSV)",
            data=export_bitacora_csv(paquete["bitacora"]),
            file_name=f"jornada_bitacora_{ts}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not paquete["bitacora"],
        )

    if st.button("Guardar copia en data/outputs/", use_container_width=False):
        ruta = save_outputs_to_disk(paquete, prefix="jornada")
        st.success(f"Guardado en {ruta}")

    render_divider()
    if secondary("Resultados", key="sup_exp_back"):
        st.session_state.vista = VISTA_SUPERVISOR_RESULTS
        st.rerun()

    render_footer()
