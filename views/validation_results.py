"""Validacion - Resultados con bloques navegables."""
import streamlit as st
import pandas as pd

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.filters import render_filters, apply_filters
from dashboards.kpi_dashboard import render_kpi_dashboard
from dashboards.scenario_comparison import render_scenario_comparison
from dashboards.service_evolution import render_service_evolution
from dashboards.vehicle_performance import render_vehicle_performance
from dashboards.variability_analysis import render_variability_analysis
from simulation.metrics import compute_replanning_stats
from services.validation_service import label_escenario
from utils.constants import (
    VISTA_VALIDATION_SIMULATION, VISTA_VALIDATION_EXPORT,
)


def _entregas_concatenadas(resultados: dict) -> pd.DataFrame:
    rows = []
    for esc_id, res in resultados.get("escenarios", {}).items():
        e = res.get("entregas")
        if e is None or e.empty:
            continue
        tmp = e.copy()
        tmp["escenario"] = esc_id
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def render():
    render_view_title(
        "Resultados",
        "Indicadores principales, comparacion de escenarios, evolucion del servicio, "
        "desempeno por vehiculo y analisis de variabilidad."
    )
    render_step_breadcrumb()

    res = st.session_state.get("resultados")
    dataset = st.session_state.get("dataset")
    if not res or not dataset:
        st.warning("Aun no hay resultados. Ejecuta la simulacion.")
        render_footer()
        return

    escenarios = res.get("escenarios_lista", [])
    entregas_all = _entregas_concatenadas(res)
    filtros = render_filters(entregas_all, escenarios, key_prefix="val_res",
                             show_escenario=True, show_iteracion=False)

    esc_sel = filtros.get("escenario", "Todos")
    if esc_sel == "Todos" and escenarios:
        esc_target = "dss_completo" if "dss_completo" in escenarios else escenarios[-1]
    else:
        esc_target = esc_sel

    sub = res["escenarios"].get(esc_target, {})
    entregas_esc = sub.get("entregas", pd.DataFrame())
    entregas_filtradas = apply_filters(entregas_esc, filtros) if not entregas_esc.empty else entregas_esc

    tabs = st.tabs([
        "1. Indicadores",
        "2. Comparacion de escenarios",
        "3. Evolucion del servicio",
        "4. Desempeno por vehiculo",
        "5. Variabilidad",
        "6. Detalle operativo",
    ])

    with tabs[0]:
        st.caption(f"Escenario representativo: **{label_escenario(esc_target)}**")
        replan = compute_replanning_stats(sub.get("decisiones", []))
        render_kpi_dashboard(sub.get("kpis", {}), replan)

    with tabs[1]:
        render_scenario_comparison(
            res.get("kpis_por_escenario"),
            res.get("iteraciones"),
            res.get("resumen"),
        )

    with tabs[2]:
        render_service_evolution(res.get("evolucion_otd"), entregas_filtradas)

    with tabs[3]:
        render_vehicle_performance(entregas_filtradas, dataset.get("vehiculos"))

    with tabs[4]:
        render_variability_analysis(entregas_filtradas, res.get("iteraciones"), sub.get("kpis"))

    with tabs[5]:
        if entregas_filtradas is None or entregas_filtradas.empty:
            st.info("No hay entregas que coincidan con los filtros aplicados.")
        else:
            cols = ["pedido_id", "vehiculo_id", "zona", "tipo_servicio",
                    "ventana_inicio", "ventana_fin", "inicio_servicio_min",
                    "fin_servicio_min", "retraso_min", "estado", "incidencia"]
            cols = [c for c in cols if c in entregas_filtradas.columns]
            st.dataframe(entregas_filtradas[cols], hide_index=True,
                         use_container_width=True, height=440)

    render_divider()
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Simulacion", key="val_res_back",
                     use_container_width=True):
            st.session_state.vista = VISTA_VALIDATION_SIMULATION
            st.rerun()
    with col_r:
        if primary("Exportacion", key="val_res_next",
                   use_container_width=True):
            navigate_to(VISTA_VALIDATION_EXPORT)

    render_footer()
