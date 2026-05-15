"""Validacion - Exportacion de resultados."""
from datetime import datetime
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb
from components.buttons import secondary
from services.export_service import (
    export_resultados_xlsx, export_dataframe_csv, export_kpis_csv,
    save_outputs_to_disk,
)
from services.validation_service import label_escenario
from utils.constants import VISTA_VALIDATION_RESULTS


def render():
    render_view_title(
        "Exportacion de resultados",
        "Descarga los resultados consolidados (KPIs, entregas, evolucion OTD, "
        "iteraciones y resumen por escenario) en CSV o XLSX."
    )
    render_step_breadcrumb()

    res = st.session_state.get("resultados")
    if not res:
        st.warning("Aun no hay resultados para exportar.")
        render_footer()
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    paquete = {
        "kpis": (res.get("escenarios", {}).get("dss_completo") or
                 next(iter(res.get("escenarios", {}).values()), {})).get("kpis", {}),
        "entregas": _entregas_all(res),
        "evolucion_otd": res.get("evolucion_otd"),
        "iteraciones": res.get("iteraciones"),
        "resumen": res.get("resumen"),
        "alertas": _alertas_all(res),
        "bitacora": st.session_state.get("bitacora"),
        "rutas_iniciales": _rutas_first(res, "rutas_iniciales"),
        "rutas_finales": _rutas_first(res, "rutas_finales"),
    }

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.download_button(
            "Descargar XLSX consolidado",
            data=export_resultados_xlsx(paquete),
            file_name=f"validacion_resultados_{ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_b:
        st.download_button(
            "Descargar entregas (CSV)",
            data=export_dataframe_csv(paquete["entregas"]),
            file_name=f"validacion_entregas_{ts}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_c:
        st.download_button(
            "Descargar resumen escenarios (CSV)",
            data=export_dataframe_csv(paquete["resumen"]),
            file_name=f"validacion_resumen_{ts}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if st.button("Guardar copia en data/outputs/", use_container_width=False):
        ruta = save_outputs_to_disk(paquete, prefix="validacion")
        st.success(f"Guardado en {ruta}")

    render_divider()
    if secondary("Resultados", key="val_exp_back"):
        st.session_state.vista = VISTA_VALIDATION_RESULTS
        st.rerun()

    render_footer()


def _entregas_all(res: dict):
    import pandas as pd
    rows = []
    for esc_id, sub in res.get("escenarios", {}).items():
        e = sub.get("entregas")
        if e is None or e.empty:
            continue
        tmp = e.copy()
        tmp["escenario"] = esc_id
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True) if rows else None


def _alertas_all(res: dict):
    out = []
    for esc_id, sub in res.get("escenarios", {}).items():
        for a in sub.get("alertas", []) or []:
            d = dict(a)
            d["escenario"] = esc_id
            out.append(d)
    return out


def _rutas_first(res: dict, key: str):
    for sub in res.get("escenarios", {}).values():
        r = sub.get(key)
        if r:
            return r
    return None
