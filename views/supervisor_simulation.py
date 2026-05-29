"""Supervisor - Ejecucion de la jornada simulada con bitacora de eventos."""
from dataclasses import asdict
import pandas as pd
import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.navigation import render_step_breadcrumb, navigate_to
from components.buttons import primary, secondary
from optimization.route_optimizer import Ruta
from simulation.sim_engine import simular_jornada
from utils.state import log_bitacora
from utils.formatters import minutes_to_hhmm
from utils.constants import (
    VISTA_SUPERVISOR_ROUTES, VISTA_SUPERVISOR_ALERTS, VISTA_SUPERVISOR_RESULTS,
)


# Mapa de etiquetas legibles por tipo de evento
_LABEL_TIPO = {
    "salida":                       "Salida de almacen",
    "llegada":                      "Llegada a parada",
    "inicio_servicio":              "Inicio de servicio",
    "fin_servicio":                 "Fin de servicio",
    "incidencia":                   "Incidencia",
    "alerta_riesgo":                "Alerta de riesgo",
    "replanificacion":              "Replanificacion",
    "replanificacion_descartada":   "Replanificacion descartada",
}


def _rutas_dict_to_obj(rutas_dict: dict) -> dict:
    return {v: Ruta(**r) for v, r in rutas_dict.items()}


def _build_bitacora(res: dict) -> pd.DataFrame:
    """Construye la bitacora visible a partir de res['eventos'].

    Columnas: hora, vehiculo, pedido, tipo, descripcion, impacto_min,
    estado, genero_alerta, genero_replanificacion.
    """
    eventos = res.get("eventos")
    if eventos is None or (hasattr(eventos, "empty") and eventos.empty):
        return pd.DataFrame()

    df = eventos.copy()

    # Hora HH:MM
    df["hora"] = df["timestamp_min"].apply(
        lambda m: minutes_to_hhmm(int(m)) if pd.notna(m) else "-"
    )
    # Etiqueta legible
    df["tipo_evento"] = df["tipo"].map(_LABEL_TIPO).fillna(df["tipo"])
    # Pedido (None -> "-")
    df["pedido"] = df.get("pedido_id", pd.Series([None] * len(df))).fillna("-")
    df.loc[df["pedido"].astype(str) == "None", "pedido"] = "-"
    # Impacto en minutos: solo en incidencias
    if "demora_min" in df.columns:
        df["impacto_min"] = df["demora_min"].fillna(0).round(1)
    else:
        df["impacto_min"] = 0.0
    df.loc[df["tipo"] != "incidencia", "impacto_min"] = 0.0
    # Estado
    if "estado" in df.columns:
        df["estado_entrega"] = df["estado"].fillna("-")
    else:
        df["estado_entrega"] = "-"
    df.loc[df["tipo"] != "fin_servicio", "estado_entrega"] = "-"
    # Flags
    df["genero_alerta"] = df["tipo"].eq("alerta_riesgo")
    df["genero_replanificacion"] = df["tipo"].eq("replanificacion")

    out = df[[
        "hora", "vehiculo_id", "pedido", "tipo_evento", "detalle",
        "impacto_min", "estado_entrega",
        "genero_alerta", "genero_replanificacion",
    ]].rename(columns={
        "vehiculo_id": "vehiculo",
        "detalle": "descripcion",
        "estado_entrega": "estado",
    })
    return out.reset_index(drop=True)


def render():
    render_view_title(
        "Simulacion de la jornada",
        "Ejecuta la jornada estocastica (09:00 a 19:00) con la flota y rutas asignadas. "
        "La bitacora detalla cada evento: incidencias, alertas y replanificaciones."
    )
    render_step_breadcrumb()

    dataset = st.session_state.get("dataset")
    cfg = st.session_state.get("configuracion") or {}
    rutas_dict = st.session_state.get("rutas_iniciales")
    if not dataset or not cfg or not rutas_dict:
        st.warning("Faltan datos, configuracion o rutas iniciales.")
        render_footer()
        return

    if primary("Ejecutar jornada", key="sup_run_sim"):
        with st.spinner("Simulando jornada..."):
            rutas_obj = _rutas_dict_to_obj(rutas_dict)
            # Replanificacion intravehiculo siempre activa; aprobacion manual.
            res = simular_jornada(
                dataset,
                rutas=rutas_obj,
                configuracion=cfg,
                replanifica=True,
                aprobacion_automatica=False,
                seed=int(cfg.get("semilla", 42)),
            )
        st.session_state.resultados = res
        st.session_state.rutas_finales = res.get("rutas_finales")
        st.session_state.alertas = res.get("alertas", [])
        st.session_state.decisiones_supervisor = res.get("decisiones", [])

        # Contadores para la bitacora del usuario
        n_alertas = len(res.get("alertas", []))
        n_incidencias = 0
        eventos = res.get("eventos")
        if eventos is not None and not eventos.empty:
            n_incidencias = int((eventos["tipo"] == "incidencia").sum())
        log_bitacora(
            "Supervisor - simulacion ejecutada",
            f"{n_incidencias} incidencias - {n_alertas} alertas de riesgo",
        )
        st.success("Jornada simulada correctamente.")

    res = st.session_state.get("resultados")
    if res:
        st.markdown("#### Bitacora de eventos")
        bitacora = _build_bitacora(res)
        if bitacora.empty:
            st.info("La simulacion no produjo eventos registrables.")
        else:
            # Pequeno contador encima de la tabla
            n_total = len(bitacora)
            n_inc = int((bitacora["tipo_evento"] == "Incidencia").sum())
            n_alt = int(bitacora["genero_alerta"].sum())
            n_rep = int(bitacora["genero_replanificacion"].sum())
            st.caption(
                f"{n_total} eventos  |  {n_inc} incidencias  |  "
                f"{n_alt} alertas de riesgo  |  {n_rep} replanificaciones"
            )
            st.dataframe(
                bitacora,
                hide_index=True,
                use_container_width=True,
                height=420,
                column_config={
                    "hora": st.column_config.TextColumn("Hora", width="small"),
                    "vehiculo": st.column_config.TextColumn("Vehiculo", width="small"),
                    "pedido": st.column_config.TextColumn("Pedido", width="small"),
                    "tipo_evento": st.column_config.TextColumn("Tipo", width="medium"),
                    "descripcion": st.column_config.TextColumn("Descripcion", width="large"),
                    "impacto_min": st.column_config.NumberColumn(
                        "Impacto (min)", format="%.1f", width="small",
                    ),
                    "estado": st.column_config.TextColumn("Estado", width="small"),
                    "genero_alerta": st.column_config.CheckboxColumn(
                        "Alerta", width="small",
                    ),
                    "genero_replanificacion": st.column_config.CheckboxColumn(
                        "Replanificacion", width="small",
                    ),
                },
            )

    render_divider()
    col_l, c_alert, c_res = st.columns([1, 1, 1])
    with col_l:
        if secondary("Rutas iniciales", key="sup_sim_back",
                     use_container_width=True):
            st.session_state.vista = VISTA_SUPERVISOR_ROUTES
            st.rerun()
    with c_alert:
        if primary("Alertas", key="sup_sim_to_alerts",
                   use_container_width=True,
                   disabled=not st.session_state.get("resultados")):
            navigate_to(VISTA_SUPERVISOR_ALERTS)
    with c_res:
        if primary("Resultados", key="sup_sim_to_res",
                   use_container_width=True,
                   disabled=not st.session_state.get("resultados")):
            navigate_to(VISTA_SUPERVISOR_RESULTS)

    render_footer()
