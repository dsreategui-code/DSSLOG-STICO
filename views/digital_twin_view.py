"""Vista 'Gemelo Digital Operativo' (PyDeck) del DSS CORTEX-LM.

Reconstruccion SIMULADA del avance de la operacion (gemelo digital operativo simulado, no
tiempo real fisico ni GPS). Muestra en PyDeck el HUB, los pedidos (coloreados por estado),
las rutas y los vehiculos moviendose por ticks; permite forzar una incidencia y evaluar la
replanificacion intra-vehiculo con el motor CORTEX, aceptandola o rechazandola.
"""
import time

import streamlit as st

from components.layout import render_view_title, render_divider, render_footer
from components.cards import kpi_row
from core.data_models import Parametros
from core.demo_scenario import construir_escenario_demo, replan_vehiculo_demo
from core.telemetry import construir_telemetria, estado_pedidos_en_tick
from geo.pydeck_layers import (capa_etiquetas_vehiculos, capa_hub, capa_pedidos,
                               capa_rutas, capa_vehiculos, construir_deck)
from utils.constants import VISTA_HOME

VELOCIDADES = {"0.5x": 1.2, "1x": 0.6, "2x": 0.3, "4x": 0.12}


def _init():
    ss = st.session_state
    ss.setdefault("dt_tick", 0)
    ss.setdefault("dt_play", False)
    ss.setdefault("dt_paso", 5.0)
    ss.setdefault("dt_veloc", "1x")
    ss.setdefault("dt_replan", None)
    ss.setdefault("dt_escenario", None)


def _escenario():
    if st.session_state.dt_escenario is None:
        st.session_state.dt_escenario = construir_escenario_demo(num_vehiculos=6)
    return st.session_state.dt_escenario


def _reproyectar(esc):
    """Recalcula geometrias tras un cambio de secuencia (ETAs ya actualizadas)."""
    for veh, paradas in esc["rutas"].items():
        esc["geometrias"][veh] = ([[esc["hub"]["lon"], esc["hub"]["lat"]]]
                                  + [[p["coord"][1], p["coord"][0]] for p in paradas])


def _aplicar_replan(esc, veh, res, t_sim):
    """Aplica la secuencia propuesta a los pendientes del vehiculo y reproyecta ETAs."""
    from core.demo_scenario import VELOCIDAD_KMH, _haversine_km
    paradas = esc["rutas"][veh]
    pid_a_parada = {p["pedido_id"]: p for p in paradas}
    completadas = [p for p in paradas if p["eta_min"] + p["servicio_min"] <= t_sim]
    pids_prop = [res["pedido_ids"][k] for k in res["secuencia_propuesta"]]
    pendientes = [pid_a_parada[pid] for pid in pids_prop if pid in pid_a_parada]
    nuevo = completadas + [p for p in pendientes if p not in completadas]
    # reproyectar ETAs de los pendientes desde el momento/posicion actual
    t = float(t_sim)
    prev = (completadas[-1]["coord"] if completadas else (esc["hub"]["lat"], esc["hub"]["lon"]))
    for p in nuevo:
        if p in completadas:
            prev = p["coord"]
            continue
        t += _haversine_km(prev, p["coord"]) / VELOCIDAD_KMH * 60.0
        p["eta_min"] = round(t, 1)
        p["tardanza_min"] = round(max(0.0, t - p["ventana_fin_min"]), 1)
        t += p["servicio_min"]
        prev = p["coord"]
    esc["rutas"][veh] = nuevo
    _reproyectar(esc)


def render():
    render_view_title(
        "Gemelo Digital Operativo",
        "Reconstruccion simulada del avance de la jornada de ultima milla. Visualiza rutas, "
        "vehiculos y estado de los pedidos por ticks; permite forzar una incidencia y evaluar "
        "la replanificacion intra-vehiculo. Es un gemelo operativo simulado, no tiempo real.",
        eyebrow="CORTEX-LM  /  Demostracion",
    )
    _init()
    esc = _escenario()
    paso = float(st.session_state.dt_paso)
    tele = construir_telemetria(esc, paso_tick_min=paso)
    max_tick = int(tele["tick"].max()) if not tele.empty else 0

    # --- Controles ---
    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1.4, 1.4, 1.2])
    if c1.button("▶ Iniciar", use_container_width=True):
        st.session_state.dt_play = True
    if c2.button("⏸ Pausar", use_container_width=True):
        st.session_state.dt_play = False
    if c3.button("⏭ Avanzar", use_container_width=True):
        st.session_state.dt_tick = min(max_tick, st.session_state.dt_tick + 1)
    st.session_state.dt_veloc = c4.selectbox("Velocidad", list(VELOCIDADES.keys()),
                                             index=list(VELOCIDADES).index(st.session_state.dt_veloc))
    veh_sel = c5.selectbox("Vehiculo (incidencia)", esc["vehiculos"])
    forzar = c6.button("⚠ Forzar incidencia", use_container_width=True)

    st.session_state.dt_tick = st.slider("Tick", 0, max_tick, int(st.session_state.dt_tick))
    tick = int(st.session_state.dt_tick)
    t_sim = esc["t_inicio_min"] + tick * paso

    # --- Mapa PyDeck ---
    df_tick = tele[tele["tick"] == tick]
    df_ped = estado_pedidos_en_tick(esc, t_sim)
    layers = [capa_rutas(esc), capa_pedidos(df_ped), capa_hub(esc["hub"]),
              capa_vehiculos(df_tick), capa_etiquetas_vehiculos(df_tick)]
    st.pydeck_chart(construir_deck(layers, esc["hub"]), use_container_width=True)
    st.caption(f"Hora simulada: {int(t_sim)//60:02d}:{int(t_sim)%60:02d}  ·  "
               f"tick {tick}/{max_tick}  ·  {len(esc['vehiculos'])} vehiculos  ·  "
               f"{esc['n_pedidos']} pedidos")

    # --- KPIs del tick ---
    entregados = int((df_ped["estado"] == "entregado").sum())
    en_riesgo = int((df_ped["estado"] == "en_riesgo").sum())
    alertas = int(df_tick["alerta"].sum()) if not df_tick.empty else 0
    kpi_row([
        {"label": "Entregados", "value": f"{entregados}/{len(df_ped)}",
         "helptext": "Pedidos entregados hasta este instante simulado"},
        {"label": "En riesgo", "value": str(en_riesgo),
         "helptext": "Pedidos con riesgo alto/critico de incumplir ventana"},
        {"label": "Vehiculos con alerta", "value": str(alertas),
         "helptext": "Vehiculos con retraso acumulado sobre el umbral"},
        {"label": "Hora simulada", "value": f"{int(t_sim)//60:02d}:{int(t_sim)%60:02d}"},
    ])

    # --- Replanificacion (incidencia) ---
    if forzar:
        completadas_n = int((df_ped[(df_ped.vehiculo_id == veh_sel)]["eta_min"]
                             + 0 <= t_sim).sum())  # aprox: paradas ya vencidas
        res = replan_vehiculo_demo(esc, veh_sel, Parametros(tiempo_solver_seg=3),
                                   t_actual_rel_min=max(0.0, t_sim - esc["t_inicio_min"]),
                                   completadas_n=completadas_n, incidencia_factor=1.5)
        st.session_state.dt_replan = {"veh": veh_sel, "res": res, "t_sim": t_sim}

    replan = st.session_state.dt_replan
    if replan:
        render_divider()
        res = replan["res"]
        st.markdown(f"#### Incidencia en {replan['veh']} — evaluacion de replanificacion")
        comp = res["comparacion"]
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Tardanza actual (proy.)", f"{comp['actual']['tardanza_total_min']:.0f} min")
        cc2.metric("Tardanza propuesta", f"{comp['propuesta']['tardanza_total_min']:.0f} min",
                   delta=f"{comp['propuesta']['tardanza_total_min'] - comp['actual']['tardanza_total_min']:.0f} min",
                   delta_color="inverse")
        cc3.metric("Cambios de secuencia", str(res["cambios_secuencia"]))
        st.info(f"**{res['recomendacion']}.** {res['explicacion']}")
        b1, b2 = st.columns(2)
        if b1.button("✓ Aceptar replanificacion", use_container_width=True,
                     disabled=(res["accion"] != "replanificar")):
            _aplicar_replan(esc, replan["veh"], res, replan["t_sim"])
            st.session_state.dt_replan = None
            st.success("Replanificacion aplicada. Mapa y KPIs actualizados.")
            st.rerun()
        if b2.button("✗ Mantener ruta actual", use_container_width=True):
            st.session_state.dt_replan = None
            st.rerun()

    render_divider()
    if st.button("Volver al inicio", key="dt_back"):
        st.session_state.dt_play = False
        st.session_state.vista = VISTA_HOME
        st.rerun()
    render_footer()

    # --- Bucle de animacion por ticks (gemelo operativo simulado) ---
    if st.session_state.dt_play and tick < max_tick:
        time.sleep(VELOCIDADES[st.session_state.dt_veloc])
        st.session_state.dt_tick = tick + 1
        st.rerun()
    elif tick >= max_tick:
        st.session_state.dt_play = False
