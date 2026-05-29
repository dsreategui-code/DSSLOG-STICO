"""Supervisor - Alertas y replanificaciones intravehiculo sugeridas."""
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer, render_empty_state
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from components.cards import kpi_row
from components.modals import render_replanificacion_modal
from optimization.route_optimizer import Ruta
from simulation.replanning import PropuestaReplanificacion, aplicar_replanificacion
from utils.formatters import fmt_int, fmt_pct, fmt_minutes
from utils.state import log_bitacora
from utils.constants import (
    VISTA_SUPERVISOR_SIMULATION, VISTA_SUPERVISOR_RESULTS,
)


def render():
    render_view_title(
        "Alertas",
        "Revisa las replanificaciones intravehiculo sugeridas durante la jornada. "
        "Solo aparecen aqui las propuestas que mejoran el OTD (o mantienen el OTD "
        "y reducen el tiempo total). Las que no mejoran se descartan y quedan "
        "en la bitacora de eventos."
    )
    render_step_breadcrumb()

    alertas = st.session_state.get("alertas") or []
    decisiones = st.session_state.get("decisiones_supervisor") or []

    if not alertas:
        render_empty_state(
            "No hay alertas registradas",
            "La jornada actual no produjo replanificaciones sugeridas. "
            "Puedes continuar a Resultados.",
        )
        render_divider()
        col_l, _, col_r = st.columns([1, 4, 1])
        with col_l:
            if secondary("Simulacion", key="sup_alt_back",
                         use_container_width=True):
                st.session_state.vista = VISTA_SUPERVISOR_SIMULATION
                st.rerun()
        with col_r:
            if primary("Resultados", key="sup_alt_next",
                       use_container_width=True):
                navigate_to(VISTA_SUPERVISOR_RESULTS)
        render_footer()
        return

    sugeridas = len(alertas)
    aprobadas = sum(1 for d in decisiones if d.get("decision") == "aprobada")
    rechazadas = sum(1 for d in decisiones if d.get("decision") == "rechazada")
    pendientes = sugeridas - aprobadas - rechazadas
    kpi_row([
        {"label": "Sugeridas", "value": fmt_int(sugeridas)},
        {"label": "Pendientes", "value": fmt_int(pendientes)},
        {"label": "Aprobadas", "value": fmt_int(aprobadas)},
        {"label": "Rechazadas", "value": fmt_int(rechazadas)},
    ])
    st.write("")

    decididas_idx = {d.get("alerta_idx") for d in decisiones if d.get("alerta_idx") is not None}

    for i, alerta in enumerate(alertas):
        if i in decididas_idx:
            continue
        with st.container():
            aprobado, rechazado = render_replanificacion_modal(alerta, key=f"alt_{i}")
            if aprobado or rechazado:
                _registrar_decision(i, alerta, "aprobada" if aprobado else "rechazada")
                st.rerun()
        st.write("")

    render_divider()
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Simulacion", key="sup_alt_back_2",
                     use_container_width=True):
            st.session_state.vista = VISTA_SUPERVISOR_SIMULATION
            st.rerun()
    with col_r:
        if primary("Resultados", key="sup_alt_next_2",
                   use_container_width=True):
            navigate_to(VISTA_SUPERVISOR_RESULTS)

    render_footer()


def _registrar_decision(idx: int, alerta: dict, decision: str):
    """Aplica la decision del supervisor y actualiza la bitacora + estado."""
    decisiones = st.session_state.get("decisiones_supervisor") or []
    decisiones.append({
        "alerta_idx": idx,
        "vehiculo_id": alerta.get("vehiculo_id"),
        "decision": decision,
        "delta_otd": (alerta.get("otd_propuesto", 0) - alerta.get("otd_actual", 0)),
        "pedidos_recuperados": alerta.get("pedidos_recuperados", 0),
        "timestamp_min": alerta.get("timestamp_min"),
    })
    st.session_state.decisiones_supervisor = decisiones

    if decision == "aprobada":
        rutas = st.session_state.get("rutas_finales") or {}
        if rutas and alerta.get("vehiculo_id") in rutas:
            actual = rutas[alerta["vehiculo_id"]]
            if isinstance(actual, dict):
                actual_obj = Ruta(**actual)
            else:
                actual_obj = actual
            propuesta = PropuestaReplanificacion(
                vehiculo_id=alerta["vehiculo_id"],
                motivo=alerta.get("motivo", ""),
                ruta_actual=alerta.get("ruta_actual", []),
                ruta_propuesta=alerta.get("ruta_propuesta", []),
                tiempo_actual_min=alerta.get("tiempo_actual_min", 0),
                tiempo_propuesto_min=alerta.get("tiempo_propuesto_min", 0),
                otd_actual=alerta.get("otd_actual", 0),
                otd_propuesto=alerta.get("otd_propuesto", 0),
                pedidos_recuperados=alerta.get("pedidos_recuperados", 0),
                impacto_distancia_km=alerta.get("impacto_distancia_km", 0),
            )
            from dataclasses import asdict
            nuevas = aplicar_replanificacion({alerta["vehiculo_id"]: actual_obj}, propuesta)
            rutas[alerta["vehiculo_id"]] = asdict(nuevas[alerta["vehiculo_id"]])
            st.session_state.rutas_finales = rutas
    log_bitacora(
        f"Supervisor - replanificacion {decision}",
        f"Vehiculo {alerta.get('vehiculo_id')} · "
        f"delta OTD: {alerta.get('otd_propuesto', 0) - alerta.get('otd_actual', 0):.1f}%",
    )
