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
from core.twin_sim import (aplicar_propuestas, proponer_reruteo, resumen_operacion,
                           simular_incidencias, tabla_alertas, tabla_operacion)
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
    ss.setdefault("dt_sig", None)
    ss.setdefault("dt_dec", {})


def _escenario():
    if st.session_state.dt_escenario is None:
        st.session_state.dt_escenario = construir_escenario_demo(num_vehiculos=6)
    return st.session_state.dt_escenario


def _orden_str(ids, k=6):
    s = " → ".join(ids[:k])
    return s + (f" … (+{len(ids) - k})" if len(ids) > k else "")


def _decidir(veh, val):
    st.session_state.dt_dec[veh] = val


def _decidir_todas(veh_ids, val):
    for v in veh_ids:
        st.session_state.dt_dec[v] = val


def _tarjeta_propuesta(p, dec):
    """Tarjeta de decision: ruta actual vs re-secuenciada, con sustento y botones."""
    veh = p["vehiculo_id"]
    estado = dec.get(veh)
    with st.container(border=True):
        top = st.columns([3, 1])
        top[0].markdown(f"**⚠ {veh} — {p['n_pendientes']} paradas pendientes en riesgo**")
        badge = {"aprobada": "✓ Re-ruteo aprobado",
                 "rechazada": "Ruta original mantenida"}.get(estado, "Pendiente de decision")
        top[1].markdown(f"<div style='text-align:right;color:#475467;font-size:13px;'>"
                        f"{badge}</div>", unsafe_allow_html=True)
        st.caption(f"Incidencia {p['incidencia_hora']} en {p['incidencia_distrito']} "
                   f"(+{p['incidencia_min']:.0f} min), que arrastra las paradas siguientes.")
        ca, cb = st.columns(2)
        with ca:
            st.markdown("**Ruta actual**")
            st.metric("Fuera de ventana", p["tarde_actual"])
            st.metric("Tardanza acumulada", f"{p['tard_actual_min']:.0f} min")
            st.caption("orden: " + _orden_str(p["orden_actual"]))
        with cb:
            st.markdown("**Ruta re-secuenciada (propuesta)**")
            st.metric("Fuera de ventana", p["tarde_propuesto"],
                      delta=(-p["recuperadas"] if p["recuperadas"] else None),
                      delta_color="inverse")
            st.metric("Tardanza acumulada", f"{p['tard_propuesto_min']:.0f} min",
                      delta=(f"-{p['reduccion_min']:.0f} min" if p["reduccion_min"] > 0
                             else None), delta_color="inverse")
            st.caption("orden: " + _orden_str(p["orden_propuesto"]))
        recup = (f"recupera **{p['recuperadas']}** entrega(s) y " if p["recuperadas"] > 0
                 else "")
        st.info(f"Sustento: reordenar priorizando la ventana mas proxima {recup}reduce la "
                f"tardanza acumulada en **{p['reduccion_min']:.0f} min**, manteniendo los "
                f"mismos pedidos (sin transferencias entre vehiculos).")
        b1, b2 = st.columns(2)
        b1.button("Aprobar re-ruteo", key=f"dt_ap_{veh}", type="primary",
                  use_container_width=True, disabled=(estado == "aprobada"),
                  on_click=_decidir, args=(veh, "aprobada"))
        b2.button("Mantener ruta actual", key=f"dt_re_{veh}",
                  use_container_width=True, disabled=(estado == "rechazada"),
                  on_click=_decidir, args=(veh, "rechazada"))


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

    modo_clasico = st.checkbox(
        "Mapa clasico por ticks (respaldo)", value=False,
        help="El mapa fluido se anima en el navegador sin recargar la pagina. Si no se "
             "visualiza bien, activa el mapa clasico.")

    # Inyeccion de incidencias aleatorias (reproducible con la semilla)
    esc_sin, incidencias = simular_incidencias(esc_base, tasa=intensidad / 100.0,
                                               seed=int(semilla))
    # Propuestas de re-ruteo (NO se aplican solas: las decide el usuario)
    propuestas = proponer_reruteo(esc_sin)
    sig = f"{int(semilla)}:{int(intensidad)}"
    if st.session_state.get("dt_sig") != sig:
        st.session_state.dt_sig = sig
        st.session_state.dt_dec = {}          # reset de decisiones si cambia la jornada
    dec = st.session_state.setdefault("dt_dec", {})
    # En el mapa fluido la decision es interactiva DENTRO de la animacion (por vehiculo);
    # el escenario base alimenta los dashboards. En clasico, se decide con tarjetas server-side.
    if modo_clasico:
        aprobadas = [p["vehiculo_id"] for p in propuestas
                     if dec.get(p["vehiculo_id"]) == "aprobada"]
        esc = aplicar_propuestas(esc_sin, propuestas, aprobadas)
    else:
        aprobadas, esc = [], esc_sin

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

    if modo_clasico:
        st.caption("Gemelo operativo **SIMULADO**. Trazos rectos = respaldo haversine (sin "
                   "OSRM); con **OSRM local** seguiran las calles. Decide el re-ruteo en las "
                   "tarjetas de mas abajo.")
    else:
        st.caption("Gemelo operativo **SIMULADO** e interactivo: cuando un vehiculo llega a su "
                   "incidencia se **paraliza** y muestra su tarjeta en el mapa (Aprobar / "
                   "Mantener) mientras los demas siguen. Trazos rectos = respaldo haversine; "
                   "con **OSRM local** seguiran las calles.")

    # --- KPIs de la jornada ---
    r_sin = resumen_operacion(esc_sin, incidencias)
    if propuestas:
        esc_pot = aplicar_propuestas(esc_sin, propuestas,
                                     [p["vehiculo_id"] for p in propuestas])
        r_pot = resumen_operacion(esc_pot, incidencias)
    else:
        r_pot = r_sin

    if modo_clasico:
        r = resumen_operacion(esc, incidencias)
        pendientes = [p for p in propuestas if dec.get(p["vehiculo_id"]) is None]
        delta_otd = (r["otd"] - r_sin["otd"]) * 100
        if pendientes:
            st.warning(f"⚠ **{r['alertas']} alertas** · **{len(pendientes)} propuesta(s)** "
                       f"esperan tu decision mas abajo.")
        elif propuestas:
            st.success(f"Decisiones aplicadas: OTD {r_sin['otd']*100:.1f}% → "
                       f"**{r['otd']*100:.1f}%** ({len(aprobadas)}/{len(propuestas)} "
                       f"aprobadas).")
        elif r["alertas"] > 0:
            st.warning(f"⚠ **{r['alertas']} alertas**, pero el re-ruteo no halla mejora.")
        else:
            st.success("Sin alertas: todas las entregas proyectadas dentro de ventana.")
        kpi_row([
            {"label": "OTD simulado", "value": f"{r['otd'] * 100:.1f}%",
             "delta": (f"{delta_otd:+.1f} pts vs base" if aprobadas and abs(delta_otd) > 1e-9
                       else None),
             "delta_dir": "up" if delta_otd > 1e-9 else "flat",
             "helptext": "Entregas dentro de ventana con las decisiones aplicadas"},
            {"label": "Alertas", "value": str(r["alertas"])},
            {"label": "Incidencias", "value": str(r["incidencias"])},
            {"label": "Tardanza maxima", "value": f"{r['tardanza_max_min']:.0f} min"},
        ])
    else:
        delta_pot = (r_pot["otd"] - r_sin["otd"]) * 100
        if propuestas:
            st.info(f"⚠ **{r_sin['alertas']} alertas** · **{len(propuestas)} vehiculo(s)** con "
                    f"propuesta. Cuando cada uno se paralice en el mapa, decide **Aprobar** o "
                    f"**Mantener**. OTD base {r_sin['otd']*100:.1f}% → **{r_pot['otd']*100:.1f}%** "
                    f"si apruebas todas.")
        elif r_sin["alertas"] > 0:
            st.warning(f"⚠ **{r_sin['alertas']} alertas**, pero el re-ruteo no halla un "
                       f"reordenamiento que mejore (ventanas sin holgura).")
        else:
            st.success("Sin alertas: todas las entregas proyectadas dentro de ventana.")
        kpi_row([
            {"label": "OTD base", "value": f"{r_sin['otd'] * 100:.1f}%",
             "helptext": "Sin aplicar re-ruteo (peor caso de la jornada)"},
            {"label": "OTD potencial", "value": f"{r_pot['otd'] * 100:.1f}%",
             "delta": (f"{delta_pot:+.1f} pts" if abs(delta_pot) > 1e-9 else None),
             "delta_dir": "up" if delta_pot > 1e-9 else "flat",
             "helptext": "Si apruebas todas las propuestas de re-ruteo en el mapa"},
            {"label": "Alertas", "value": str(r_sin["alertas"])},
            {"label": "Incidencias", "value": str(r_sin["incidencias"])},
        ])

    # --- Tarjetas server-side (solo en modo clasico; en fluido se decide en el mapa) ---
    if modo_clasico and propuestas:
        render_divider()
        hc1, hc2 = st.columns([3, 2])
        hc1.markdown("#### Alertas con propuesta de re-ruteo")
        gb1, gb2 = hc2.columns(2)
        veh_ids = [p["vehiculo_id"] for p in propuestas]
        gb1.button("Aprobar todas", use_container_width=True,
                   on_click=_decidir_todas, args=(veh_ids, "aprobada"))
        gb2.button("Mantener todas", use_container_width=True,
                   on_click=_decidir_todas, args=(veh_ids, "rechazada"))
        st.caption("El cerebro propone; **la decision es tuya**. Cada tarjeta compara la ruta "
                   "actual del vehiculo contra la re-secuenciada por ventana mas proxima.")
        for p in propuestas:
            _tarjeta_propuesta(p, dec)

    # --- Dashboards de resultados de la operacion ---
    render_divider()
    st.markdown("#### Resultados de la operacion (simulada)")
    if not modo_clasico:
        st.caption("Reflejan la jornada **base** (sin re-ruteo). Las decisiones interactivas se "
                   "toman en el mapa de arriba, por vehiculo.")
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
