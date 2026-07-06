"""Validacion - Resultados con bloques navegables.

Los filtros se aplican sobre el dataframe combinado de entregas y los KPIs,
la evolucion del OTD, el desempeno por vehiculo y la tabla de detalle se
recalculan en tiempo real con `compute_kpis` y `compute_otd_evolution`.
"""
import streamlit as st
import pandas as pd

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.filters import render_filters, apply_filters
from dashboards.kpi_dashboard import render_kpi_dashboard, render_service_time_breakdown
from dashboards.scenario_comparison import render_scenario_comparison
from components.cards import kpi_row
from utils.formatters import fmt_pct, fmt_int, fmt_minutes
from dashboards.service_evolution import render_service_evolution
from dashboards.vehicle_performance import render_vehicle_performance
from dashboards.variability_analysis import render_variability_analysis
from simulation.metrics import (
    compute_kpis, compute_otd_evolution,
    compute_replanning_stats, compute_service_time_metrics,
)
from services.validation_service import label_escenario, ESCENARIOS_DEFAULT
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
        "desempeno por vehiculo y analisis de variabilidad. Los filtros actualizan "
        "cards, graficos y tablas en tiempo real."
    )
    render_step_breadcrumb()

    res = st.session_state.get("resultados")
    dataset = st.session_state.get("dataset")
    if not res or not dataset:
        st.warning("Aun no hay resultados. Ejecuta la simulacion.")
        render_footer()
        return

    escenarios = res.get("escenarios_lista", [])
    escenarios_labels = {e["id"]: e["nombre"] for e in ESCENARIOS_DEFAULT}
    entregas_all = _entregas_concatenadas(res)

    filtros = render_filters(
        entregas_all, escenarios=escenarios,
        escenarios_labels=escenarios_labels,
        key_prefix="val_res", show_escenario=True,
    )

    esc_sel = filtros.get("escenario", "Todos")
    if esc_sel == "Todos":
        # Para indicadores y evolucion necesitamos un escenario representativo
        esc_target = "dss_completo" if "dss_completo" in escenarios else \
                     (escenarios[-1] if escenarios else None)
    else:
        esc_target = esc_sel

    sub = res["escenarios"].get(esc_target, {}) if esc_target else {}
    entregas_esc = sub.get("entregas", pd.DataFrame())

    # entregas_filtradas: las del escenario objetivo aplicando filtros secundarios
    entregas_filtradas = (
        apply_filters(entregas_esc, filtros) if not entregas_esc.empty else entregas_esc
    )

    # Recalcular KPIs y evolucion sobre las entregas filtradas (no precomputadas)
    kpis_filtrados = compute_kpis(entregas_filtradas, alertas=sub.get("alertas", []))
    evolucion_filtrada = compute_otd_evolution(entregas_filtradas)
    service_metrics = compute_service_time_metrics(entregas_filtradas)

    # Escenario activo (caption comun a la narrativa).
    if esc_sel == "Todos" and esc_target:
        st.caption(f"Escenario representativo: **{label_escenario(esc_target)}** "
                   f"(usa el filtro Escenario para ver otro).")
    elif esc_target:
        st.caption(f"Escenario activo: **{label_escenario(esc_target)}**")

    replan = compute_replanning_stats(sub.get("decisiones", []))
    _sigma = sub.get("otd_std_iter")

    # Resultados como NARRATIVA de 5 capitulos (mismo guion que el gemelo) + la comparacion de
    # escenarios propia de validacion.
    t1, t2, t3, t4, t5, tcomp = st.tabs([
        "1 · Resultado", "2 · Detalle", "3 · Robustez", "4 · Reaccion", "5 · Costo",
        "Comparacion de escenarios"])

    # Cap 1 - El resultado: ¿cumplimos la promesa?
    with t1:
        st.caption("**¿Cumplimos la promesa?**")
        kpi_row([
            {"label": "OTD", "value": fmt_pct(kpis_filtrados.get("otd")),
             "helptext": "Entregas a tiempo / entregas completadas"},
            {"label": "OTIF", "value": fmt_pct(kpis_filtrados.get("otif")),
             "helptext": "A tiempo sobre el total de pedidos"},
            {"label": "Éxito 1er intento",
             "value": fmt_pct(kpis_filtrados.get("exito_primer_intento")),
             "helptext": "Entregas logradas sin reintento (ausencia)"},
        ])

    # Cap 2 - El detalle: ¿que tan bien y donde fallo?
    with t2:
        st.caption("**¿Qué tan bien y dónde falló?**")
        kpi_row([
            {"label": "A tiempo", "value": fmt_int(kpis_filtrados.get("entregas_a_tiempo"))},
            {"label": "Fuera de ventana", "value": fmt_int(kpis_filtrados.get("entregas_fuera_ventana"))},
            {"label": "Fallidas", "value": fmt_int(kpis_filtrados.get("entregas_fallidas"))},
            {"label": "Retraso prom.", "value": fmt_minutes(kpis_filtrados.get("retraso_promedio_min"))},
            {"label": "Retraso máx.", "value": fmt_minutes(kpis_filtrados.get("retraso_maximo_min"))},
        ])
        st.write("")
        render_service_evolution(evolucion_filtrada, entregas_filtradas)
        st.write("")
        render_vehicle_performance(entregas_filtradas, dataset.get("vehiculos"))

    # Cap 3 - La robustez (CLIMAX): ¿y en los peores dias?
    with t3:
        st.caption("**¿Y en los peores días?** Un plan robusto se mide por su cola, no por su "
                   "promedio.")
        kpi_row([
            {"label": "CVaR tardanza ★", "value": fmt_minutes(sub.get("cvar_tardanza_min")),
             "helptext": "Tardanza total en el PEOR 10% de días (riesgo de cola)"},
            {"label": "Pedidos en riesgo", "value": fmt_int(sub.get("pedidos_en_riesgo")),
             "helptext": "Pedidos con alto IRI (probabilidad de incumplir su ventana)"},
            {"label": "Variabilidad OTD ★",
             "value": (f"±{float(_sigma):.1f} pts" if _sigma is not None else "-"),
             "helptext": "Desv. estándar del OTD entre iteraciones (menor = más consistente)"},
        ])
        st.write("")
        render_variability_analysis(entregas_filtradas, res.get("iteraciones"), kpis_filtrados)

    # Cap 4 - La reaccion: ¿como respondio al caos?
    with t4:
        st.caption("**¿Cómo respondió al caos?** Alertas y re-ruteo.")
        kpi_row([
            {"label": "Alertas", "value": fmt_int(kpis_filtrados.get("alertas_generadas"))},
            {"label": "Replanificadas", "value": fmt_int(kpis_filtrados.get("entregas_replanificadas"))},
            {"label": "Re-ruteos sugeridos", "value": fmt_int(replan.get("sugeridas", 0))},
            {"label": "Aprobados", "value": fmt_int(replan.get("aprobadas", 0))},
            {"label": "Pedidos recuperados", "value": fmt_int(replan.get("pedidos_recuperados", 0))},
        ])

    # Cap 5 - El costo: ¿a que precio?
    with t5:
        st.caption("**¿A qué precio?** El tiempo operativo del plan.")
        kpi_row([
            {"label": "Tiempo total op.",
             "value": fmt_minutes(kpis_filtrados.get("tiempo_total_operacion_min"))},
            {"label": "Tiempo prom. entrega",
             "value": fmt_minutes(kpis_filtrados.get("tiempo_promedio_entrega_min"))},
            {"label": "Tiempo prom. parada",
             "value": fmt_minutes(kpis_filtrados.get("tiempo_promedio_parada_min"))},
        ])
        st.write("")
        render_service_time_breakdown(service_metrics)

    # Extra propio de validacion: comparacion entre escenarios (agregada, no se filtra).
    with tcomp:
        render_scenario_comparison(res.get("kpis_por_escenario"), res.get("iteraciones"),
                                   res.get("resumen"))

    with st.expander("Detalle operativo (tabla de entregas)"):
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
