"""Validacion - Ejecucion del experimento Monte Carlo multi-escenario.

La vista muestra una barra de progreso por escenario con tres estados visibles:
pendiente, en ejecucion, completado. No se muestran cards de resultados (esos
viven en la vista de Resultados).
"""
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from services.validation_service import run_validation, label_escenario
from utils.state import log_bitacora
from utils.constants import (
    VISTA_VALIDATION_CONFIG, VISTA_VALIDATION_RESULTS,
)


# Etiquetas de estado por escenario
_STATUS_PENDIENTE  = "Pendiente"
_STATUS_EN_CURSO   = "En ejecucion"
_STATUS_COMPLETADO = "Completado"


def _status_html(label: str) -> str:
    color = {
        _STATUS_PENDIENTE:  "#98A2B3",
        _STATUS_EN_CURSO:   "#1570EF",
        _STATUS_COMPLETADO: "#027A48",
    }.get(label, "#667085")
    return (
        f'<span style="display:inline-block; padding:0.18rem 0.7rem; '
        f'border-radius:999px; font-size:0.74rem; font-weight:500; '
        f'background:{color}14; color:{color}; border:1px solid {color}33;">'
        f'{label}</span>'
    )


def render():
    render_view_title(
        "Simulacion",
        "Ejecuta el experimento sobre los escenarios seleccionados. Cada escenario "
        "corre las iteraciones definidas con variabilidad de trafico, tiempos de "
        "servicio e incidencias."
    )
    render_step_breadcrumb()

    cfg = st.session_state.get("configuracion") or {}
    dataset = st.session_state.get("dataset")
    if not dataset or not cfg:
        st.warning("Falta dataset o configuracion. Vuelve a la pantalla anterior.")
        render_footer()
        return

    escenarios = cfg.get("escenarios_activos", [])
    iteraciones = int(cfg.get("iteraciones", 30))
    total_runs = len(escenarios) * iteraciones

    st.info(
        f"Escenarios: **{len(escenarios)}**  |  Iteraciones por escenario: "
        f"**{iteraciones}**  |  Total de corridas: **{total_runs}**  |  "
        f"Semilla: {cfg.get('semilla', 42)}"
    )

    # Panel de progreso por escenario - se renderiza siempre con estado Pendiente
    st.markdown("#### Progreso por escenario")
    progress_slots = {}
    for esc in escenarios:
        row = st.container()
        with row:
            c_lbl, c_status, c_count, c_bar = st.columns([3, 2, 1, 6])
            c_lbl.markdown(f"**{label_escenario(esc)}**")
            slot_status = c_status.empty()
            slot_count = c_count.empty()
            slot_bar = c_bar.progress(0)
            slot_status.markdown(_status_html(_STATUS_PENDIENTE), unsafe_allow_html=True)
            slot_count.markdown(f"0 / {iteraciones}")
            progress_slots[esc] = {
                "status": slot_status,
                "count": slot_count,
                "bar": slot_bar,
            }

    st.write("")

    if primary("Ejecutar experimento", key="val_run_sim",
               use_container_width=False, disabled=not escenarios):
        def _on_progress(esc, it, total, status):
            s = progress_slots.get(esc)
            if not s:
                return
            if status == "start":
                s["status"].markdown(_status_html(_STATUS_EN_CURSO),
                                     unsafe_allow_html=True)
                s["count"].markdown(f"0 / {total}")
                s["bar"].progress(0)
            elif status == "progress":
                s["bar"].progress(min(1.0, it / max(total, 1)))
                s["count"].markdown(f"{it} / {total}")
            elif status == "done":
                s["status"].markdown(_status_html(_STATUS_COMPLETADO),
                                     unsafe_allow_html=True)
                s["bar"].progress(1.0)
                s["count"].markdown(f"{total} / {total}")

        resultados = run_validation(dataset, cfg, progress_callback=_on_progress)
        st.session_state.resultados = resultados
        log_bitacora(
            "Validacion - simulacion ejecutada",
            f"{len(escenarios)} escenarios - {iteraciones} iter por escenario",
        )
        st.success(
            "Simulacion completada. Los resultados detallados estan en la pantalla siguiente."
        )

    render_divider()
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Configuracion", key="val_sim_back",
                     use_container_width=True):
            st.session_state.vista = VISTA_VALIDATION_CONFIG
            st.rerun()
    with col_r:
        if primary("Resultados", key="val_sim_next",
                   use_container_width=True,
                   disabled=not st.session_state.get("resultados")):
            navigate_to(VISTA_VALIDATION_RESULTS)

    render_footer()
