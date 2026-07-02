"""Vista 'Gemelo Digital Operativo' del DSS CORTEX-LM.

Reconstruccion SIMULADA del avance de la operacion de ultima milla (gemelo operativo simulado,
no tiempo real fisico ni GPS). El mapa fluido (deck.gl) anima en el navegador sin recargar la
pagina; las incidencias aparecen de forma ALEATORIA segun una intensidad configurable (con
semilla reproducible) y se propagan sobre las ETAs. Debajo se muestran los dashboards de
resultados de la jornada. El mapa clasico por ticks queda como respaldo.
"""
import time

import streamlit as st
import streamlit.components.v1 as components

from components.layout import render_view_title, render_divider, render_footer
from components.cards import kpi_row
from core.demo_scenario import construir_escenario_demo
from core.telemetry import construir_telemetria, estado_pedidos_en_tick
from core.twin_sim import (mitigar_con_reruteo, resumen_operacion, simular_incidencias,
                           tabla_alertas, tabla_operacion)
from dashboards.risk_dashboard import fig_iri_clasificacion
from dashboards.twin_dashboard import (fig_entregas_por_hora, fig_estado_final,
                                       fig_tardanza_por_vehiculo)
from geo.pydeck_layers import (capa_etiquetas_vehiculos, capa_hub, capa_pedidos,
                               capa_rutas, capa_vehiculos, construir_deck)
from geo.twin_component import html_gemelo
from services.data_loader import dataset_exists, generar_dataset_demo
from utils.constants import VISTA_HOME

VELOCIDADES = {"0.5x": 1.2, "1x": 0.6, "2x": 0.3, "4x": 0.12}


def _init():
    ss = st.session_state
    ss.setdefault("dt_tick", 0)
    ss.setdefault("dt_play", False)
    ss.setdefault("dt_paso", 5.0)
    ss.setdefault("dt_veloc", "1x")
    ss.setdefault("dt_escenario", None)
    ss.setdefault("dt_bump", 0)


def _escenario():
    if st.session_state.dt_escenario is None:
        st.session_state.dt_escenario = construir_escenario_demo(num_vehiculos=6)
    return st.session_state.dt_escenario


def render():
    render_view_title(
        "Gemelo Digital Operativo",
        "Reconstruccion simulada del avance de la jornada de ultima milla. Las incidencias "
        "(trafico, acceso, ausencia) aparecen de forma aleatoria segun la intensidad que "
        "configures y se propagan sobre los tiempos. Es un gemelo operativo simulado, no "
        "tiempo real fisico.",
        eyebrow="CORTEX-LM  /  Demostracion",
    )
    _init()
    # El escenario puede venir de Planificacion (session_state) o del dataset demo.
    if st.session_state.dt_escenario is None and not dataset_exists():
        st.warning("El dataset demo aun no existe en este entorno. Genéralo o usa "
                   "'Planificacion' para enviar un escenario al gemelo.")
        if st.button("Generar dataset demo", type="primary", key="dt_gen_ds"):
            with st.spinner("Generando dataset demo..."):
                ok = generar_dataset_demo()
            if ok:
                st.rerun()
            else:
                st.error("No se pudo generar el dataset.")
        render_divider()
        if st.button("Volver al inicio", key="dt_nodata_back"):
            st.session_state.vista = VISTA_HOME
            st.rerun()
        render_footer()
        return

    esc_base = _escenario()

    # --- Configuracion de la simulacion (incidencias aleatorias) ---
    cfg1, cfg2, cfg3 = st.columns([2.4, 1.2, 1.4])
    intensidad = cfg1.slider(
        "Intensidad de incidencias (probabilidad por parada, %)", 0, 40, 12,
        help="Probabilidad de que cada parada sufra una incidencia aleatoria (trafico, "
             "acceso, ausencia). La operacion es simulada y estocastica.")
    semilla_base = cfg2.number_input(
        "Semilla", min_value=0, max_value=9999, value=7, step=1, key="dt_seed_input",
        help="Fija la aleatoriedad para reproducir la misma jornada.")
    if cfg3.button("Nueva jornada (re-sortear)", use_container_width=True):
        st.session_state.dt_bump = int(st.session_state.dt_bump) + 1
    semilla = (int(semilla_base) + int(st.session_state.dt_bump)) % 10000

    o1, o2 = st.columns([2.6, 2.4])
    reruteo = o1.toggle(
        "Re-ruteo automatico del cerebro ante alertas", value=True,
        help="Cuando una incidencia dispara alertas, el cerebro re-secuencia los pendientes "
             "de los vehiculos afectados (regla de ventana mas proxima) para recuperar OTD.")
    modo_clasico = o2.checkbox(
        "Mapa clasico por ticks (respaldo)", value=False,
        help="El mapa fluido se anima en el navegador sin recargar la pagina. Si no se "
             "visualiza bien, activa el mapa clasico.")

    # Inyeccion de incidencias aleatorias (reproducible con la semilla)
    esc_sin, incidencias = simular_incidencias(esc_base, tasa=intensidad / 100.0,
                                               seed=int(semilla))
    if reruteo:
        esc, acciones = mitigar_con_reruteo(esc_sin)
    else:
        esc, acciones = esc_sin, []

    tick, max_tick = 0, 0
    if modo_clasico:
        paso = float(st.session_state.dt_paso)
        tele = construir_telemetria(esc, paso_tick_min=paso)
        max_tick = int(tele["tick"].max()) if not tele.empty else 0
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1.6])
        if c1.button("Iniciar", use_container_width=True):
            st.session_state.dt_play = True
        if c2.button("Pausar", use_container_width=True):
            st.session_state.dt_play = False
        if c3.button("Avanzar", use_container_width=True):
            st.session_state.dt_tick = min(max_tick, st.session_state.dt_tick + 1)
        st.session_state.dt_veloc = c4.selectbox(
            "Velocidad", list(VELOCIDADES.keys()),
            index=list(VELOCIDADES).index(st.session_state.dt_veloc))
        st.session_state.dt_tick = st.slider("Tick", 0, max_tick,
                                             min(int(st.session_state.dt_tick), max_tick))
        tick = int(st.session_state.dt_tick)
        t_sim = esc["t_inicio_min"] + tick * paso
        df_tick = tele[tele["tick"] == tick]
        df_ped = estado_pedidos_en_tick(esc, t_sim)
        layers = [capa_rutas(esc), capa_pedidos(df_ped), capa_hub(esc["hub"]),
                  capa_vehiculos(df_tick), capa_etiquetas_vehiculos(df_tick)]
        st.pydeck_chart(construir_deck(layers, esc["hub"]), use_container_width=True)
        st.caption(f"Hora simulada: {int(t_sim)//60:02d}:{int(t_sim)%60:02d}  ·  "
                   f"tick {tick}/{max_tick}")
    else:
        components.html(html_gemelo(esc, altura=540), height=760, scrolling=False)

    st.caption("Gemelo operativo **SIMULADO**. Los trazos son rectos porque sin OSRM se usa "
               "la distancia base (haversine); al activar **OSRM local** las rutas siguen las "
               "calles reales. Las incidencias surgen de forma aleatoria segun la intensidad.")

    # --- Alertas de la operacion (saltan con la cascada de incidencias) ---
    r = resumen_operacion(esc, incidencias)
    r_sin = resumen_operacion(esc_sin, incidencias)
    recuperadas = sum(a["recuperadas"] for a in acciones)
    min_reducidos = sum(a["tard_antes_min"] - a["tard_despues_min"] for a in acciones)
    if r["alertas"] > 0:
        base = (f"⚠ **{r['alertas']} alertas**: {r['incidencias']} incidencias ponen en "
                f"riesgo de incumplir ventana a esas entregas.")
        if reruteo and recuperadas > 0:
            st.warning(base + f" El cerebro re-secuencio **{len(acciones)} vehiculo(s)** y "
                       f"recupero **{recuperadas} entrega(s)** "
                       f"(OTD {r_sin['otd']*100:.1f}% → {r['otd']*100:.1f}%).")
        elif reruteo and acciones:
            st.warning(base + f" El cerebro re-secuencio **{len(acciones)} vehiculo(s)** y "
                       f"redujo la tardanza acumulada en **{min_reducidos:.0f} min**.")
        elif reruteo:
            st.warning(base + " El re-ruteo no encontro un reordenamiento que mejore (las "
                       "ventanas ya no dan holgura).")
        else:
            st.warning(base + " Re-ruteo automatico **desactivado**: las alertas no se "
                       "mitigan y el OTD cae.")
    else:
        st.success("Sin alertas: todas las entregas proyectadas dentro de ventana.")

    # --- KPIs de la jornada ---
    delta_otd = (r["otd"] - r_sin["otd"]) * 100
    kpi_row([
        {"label": "OTD simulado", "value": f"{r['otd'] * 100:.1f}%",
         "delta": (f"{delta_otd:+.1f} pts vs sin re-ruteo" if reruteo and abs(delta_otd) > 1e-9
                   else None),
         "delta_dir": "up" if delta_otd > 1e-9 else "flat",
         "helptext": "Entregas dentro de ventana en esta jornada simulada"},
        {"label": "Alertas", "value": str(r["alertas"]),
         "helptext": "Entregas que la cascada de incidencias pone en riesgo de incumplir ventana"},
        {"label": "Incidencias", "value": str(r["incidencias"]),
         "helptext": "Eventos aleatorios ocurridos en la jornada"},
        {"label": "Tardanza maxima", "value": f"{r['tardanza_max_min']:.0f} min"},
    ])

    # --- Dashboards de resultados de la operacion ---
    render_divider()
    st.markdown("#### Resultados de la operacion (simulada)")
    df_op = tabla_operacion(esc)
    d1, d2 = st.columns(2, gap="large")
    with d1:
        st.plotly_chart(fig_entregas_por_hora(df_op), use_container_width=True,
                        config={"displayModeBar": False})
    with d2:
        st.plotly_chart(fig_tardanza_por_vehiculo(df_op), use_container_width=True,
                        config={"displayModeBar": False})
    d3, d4 = st.columns(2, gap="large")
    with d3:
        st.plotly_chart(fig_iri_clasificacion(df_op), use_container_width=True,
                        config={"displayModeBar": False})
    with d4:
        st.plotly_chart(fig_estado_final(df_op), use_container_width=True,
                        config={"displayModeBar": False})

    df_alertas = tabla_alertas(esc)
    if incidencias:
        import pandas as pd
        e1, e2 = st.columns(2)
        with e1.expander(f"Detalle de incidencias ({len(incidencias)})"):
            st.dataframe(pd.DataFrame(incidencias)[["hora", "vehiculo_id", "pedido_id",
                                                    "distrito", "retraso_min"]],
                         use_container_width=True, hide_index=True)
        with e2.expander(f"Alertas disparadas ({len(df_alertas)})"):
            if not df_alertas.empty:
                st.dataframe(df_alertas[["hora_alerta", "vehiculo_id", "pedido_id",
                                         "distrito", "tardanza_min"]],
                             use_container_width=True, hide_index=True)
            else:
                st.caption("Las incidencias no llegaron a poner entregas fuera de ventana.")
    else:
        st.caption("Sin incidencias en esta jornada (sube la intensidad o cambia la semilla).")

    render_divider()
    if st.button("Volver al inicio", key="dt_back"):
        st.session_state.dt_play = False
        st.session_state.vista = VISTA_HOME
        st.rerun()
    render_footer()

    # --- Bucle de animacion por ticks (solo modo clasico) ---
    if modo_clasico and st.session_state.dt_play and tick < max_tick:
        time.sleep(VELOCIDADES[st.session_state.dt_veloc])
        st.session_state.dt_tick = tick + 1
        st.rerun()
    elif modo_clasico and tick >= max_tick:
        st.session_state.dt_play = False
