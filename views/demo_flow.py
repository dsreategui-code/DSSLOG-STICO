"""Demostracion interactiva - flujo guiado de 5 pasos (CORTEX-LM).

  1 Datos  ->  2 Parametros  ->  3 Motor (rutas iniciales)  ->  4 Gemelo Digital  ->  5 Export

El Motor de Decision es transversal: en el paso 3 genera candidatas por criterio, las evalua
(DRO) y recomienda; el usuario elige una y el paso 4 la anima en el gemelo. Los resultados
(generales / por camion / incidencias / comparacion) viven en la pestaña Resultados del gemelo.
"""
import streamlit as st
import streamlit.components.v1 as components

from components.cards import kpi_row
from components.layout import render_divider, render_footer, render_view_title
from core.metrics import tabla_candidatas, tabla_iri
from core.planner import planificar
from core.telemetry import estado_pedidos_en_tick
from core.twin_sim import (agregados_incidencias, comparar_rutas, mitigar_con_reruteo,
                           resumen_operacion, simular_incidencias, tabla_incidencias,
                           tabla_operacion, tabla_por_camion, variabilidad_operacion)
from dashboards.risk_dashboard import (es_robusto, fig_iri_clasificacion,
                                       fig_ranking_robusto, fig_robustez_por_escenario)
from dashboards.twin_dashboard import (fig_entregas_por_hora, fig_estado_final,
                                       fig_incidencias_por_franja, fig_incidencias_por_tipo,
                                       fig_otd_otif_camion, fig_tardanza_por_vehiculo,
                                       fig_variabilidad)
from geo.pydeck_layers import capa_hub, capa_pedidos, capa_rutas, construir_deck
from geo.twin_component import html_gemelo
from services.cortex_loader import cargar_contexto
from services.data_loader import dataset_exists, generar_dataset_demo
from utils.constants import VISTA_HOME

PASOS = ["Datos", "Parametros", "Rutas iniciales", "Gemelo Digital", "Exportacion"]
PLOT_CFG = {"displayModeBar": False}


def _init():
    ss = st.session_state
    ss.setdefault("df_step", 1)
    ss.setdefault("df_ctx", None)
    ss.setdefault("df_plan", None)
    ss.setdefault("df_perfil", None)
    ss.setdefault("df_tasa", 12)
    ss.setdefault("df_seed", 7)
    ss.setdefault("df_conductor", False)


def _ctx():
    if st.session_state.df_ctx is None:
        st.session_state.df_ctx = cargar_contexto()
    return st.session_state.df_ctx


def _stepper(actual: int):
    piezas = []
    for i, nombre in enumerate(PASOS, start=1):
        if i < actual:
            bg, col, mark = "#027A48", "#fff", "✓"
        elif i == actual:
            bg, col, mark = "#1570EF", "#fff", str(i)
        else:
            bg, col, mark = "#EAECF0", "#667085", str(i)
        piezas.append(
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<span style="width:24px;height:24px;border-radius:50%;background:{bg};color:{col};'
            f'display:inline-flex;align-items:center;justify-content:center;font-size:12px;'
            f'font-weight:700;">{mark}</span>'
            f'<span style="font-size:12.5px;color:{"#0C111D" if i==actual else "#667085"};'
            f'font-weight:{"600" if i==actual else "400"};">{nombre}</span></div>')
        if i < len(PASOS):
            piezas.append('<div style="flex:1;height:2px;background:#EAECF0;min-width:20px;"></div>')
    st.markdown('<div style="display:flex;align-items:center;gap:8px;margin:4px 0 14px;">'
                + "".join(piezas) + "</div>", unsafe_allow_html=True)


def _nav(atras=True, siguiente_label=None, siguiente_ok=True):
    c1, _, c3 = st.columns([1, 3, 1])
    if atras and c1.button("Atras", use_container_width=True, key=f"df_prev_{st.session_state.df_step}"):
        st.session_state.df_step = max(1, st.session_state.df_step - 1)
        st.rerun()
    if siguiente_label and c3.button(siguiente_label, type="primary", use_container_width=True,
                                     disabled=not siguiente_ok,
                                     key=f"df_next_{st.session_state.df_step}"):
        st.session_state.df_step = min(len(PASOS), st.session_state.df_step + 1)
        st.rerun()


# ------------------------------------------------------------------ Paso 1: Datos
def _paso_datos():
    st.markdown("#### Paso 1 · Carga de datos")
    if not dataset_exists():
        st.warning("El dataset demo aun no existe en este entorno. Generalo para continuar.")
        if st.button("Generar dataset demo", type="primary", key="df_gen"):
            with st.spinner("Generando dataset demo..."):
                ok = generar_dataset_demo()
            st.rerun() if ok else st.error("No se pudo generar el dataset.")
        return
    ctx = _ctx()
    if ctx.get("avisos"):
        st.info("Avisos de carga: " + " ".join(ctx["avisos"]))
    peso = sum(float(getattr(p, "peso_kg", 0) or 0) for p in ctx["pedidos"])
    kpi_row([
        {"label": "Pedidos", "value": str(len(ctx["pedidos"]))},
        {"label": "Vehiculos", "value": str(len(ctx["vehiculos"]))},
        {"label": "Zonas operativas", "value": str(len(ctx["zonas"]))},
        {"label": "Peso total", "value": f"{peso:,.0f} kg"},
    ])
    import pandas as pd
    prev = pd.DataFrame([{"pedido": p.pedido_id, "distrito": p.distrito,
                          "ventana_fin": p.ventana_fin, "m3": p.volumen_m3,
                          "kg": p.peso_kg, "tipo": p.tipo_producto}
                         for p in ctx["pedidos"][:12]])
    st.caption("Distribucion de colchones desde el hub de Callao hacia Lima Metropolitana, "
               "jornada 09:00–19:00. Datos sinteticos y reproducibles (vista previa):")
    st.dataframe(prev, use_container_width=True, hide_index=True)
    _nav(atras=False, siguiente_label="Continuar a parametros", siguiente_ok=True)


# ------------------------------------------------------------------ Paso 2: Parametros
def _paso_params():
    st.markdown("#### Paso 2 · Configuracion de parametros del motor")
    ctx = _ctx()
    par = ctx["parametros"]
    n_total = len(ctx["pedidos"])
    c1, c2 = st.columns(2)
    n_plan = c1.slider("Pedidos a planificar", 4, n_total, min(20, n_total), key="df_nplan",
                       help="Subconjunto para una corrida agil (el solver y la simulacion "
                            "escalan con el tamano).")
    fechas = ["(sin evento)"] + sorted({e.fecha for e in ctx["eventos"]})
    fecha = c2.selectbox("Fecha (calendario de eventos)", fechas, key="df_fecha")
    c3, c4, c5 = st.columns(3)
    nivel = c3.slider("Nivel de servicio (α)", 0.80, 0.975, float(par.nivel_servicio), 0.005,
                      key="df_alpha", help="Chance-constraint de las ventanas: mayor α = mas "
                      "colchon de tiempo para cumplir.")
    cv = c4.slider("CV del tiempo de viaje", 0.10, 0.45, float(par.cv_tiempo), 0.01,
                   key="df_cv", help="Variabilidad relativa del tiempo de viaje asumida.")
    radio = c5.selectbox("Radio de ambiguedad (DRO)", ["bajo", "medio", "alto"],
                         index=1, key="df_radio",
                         help="Amplitud del conjunto de escenarios 'Lima peor' contra el que "
                              "se estresa cada candidata.")
    usar_alns = st.toggle("Usar ALNS (metaheuristica de mejora)", value=bool(par.usar_alns),
                          key="df_alns")
    st.session_state.df_cfg = {"n_plan": int(n_plan), "fecha": fecha, "nivel": float(nivel),
                               "cv": float(cv), "radio": radio, "usar_alns": bool(usar_alns)}
    _nav(siguiente_label="Optimizar rutas iniciales →", siguiente_ok=True)


# ------------------------------------------------------------------ Paso 3: Motor
def _mapa_escenario(esc):
    df_ped = estado_pedidos_en_tick(esc, float(esc["jornada_fin_min"]))
    layers = [capa_rutas(esc), capa_pedidos(df_ped), capa_hub(esc["hub"])]
    st.pydeck_chart(construir_deck(layers, esc["hub"]), use_container_width=True)


def _paso_motor():
    st.markdown("#### Paso 3 · Optimizacion de rutas iniciales (Motor CORTEX-LM)")
    ctx = _ctx()
    cfg = st.session_state.get("df_cfg", {})
    if st.button("Ejecutar motor de decision", type="primary", key="df_run"):
        par = ctx["parametros"]
        par.nivel_servicio = cfg.get("nivel", par.nivel_servicio)
        par.cv_tiempo = cfg.get("cv", par.cv_tiempo)
        par.usar_alns = cfg.get("usar_alns", par.usar_alns)
        par.usar_osrm = bool(par.usar_osrm)
        fecha = None if cfg.get("fecha", "(sin evento)") == "(sin evento)" else cfg["fecha"]
        with st.spinner("Generando candidatas + evaluacion robusta (DRO)..."):
            st.session_state.df_plan = planificar(
                ctx, max_pedidos=int(cfg.get("n_plan", 20)), fecha=fecha,
                radio_ambiguedad=cfg.get("radio", "medio"))
        st.session_state.df_perfil = (st.session_state.df_plan or {}).get("perfil_recomendado")

    res = st.session_state.df_plan
    if not res:
        st.info("Pulsa **Ejecutar motor de decision** para generar y comparar las candidatas.")
        _nav(siguiente_label=None)
        return
    if not res.get("factible"):
        st.error("La jornada NO es factible con los datos actuales.")
        for c in res["factibilidad"]["errores"]:
            st.write(f"- **{c['nombre']}**: {c['detalle']}")
        _nav(siguiente_label=None)
        return

    perfiles = list(res.get("escenarios", {}).keys())
    reco = res.get("perfil_recomendado")
    if st.session_state.df_perfil not in perfiles:
        st.session_state.df_perfil = reco if reco in perfiles else (perfiles[0] if perfiles else None)
    cs1, cs2 = st.columns([2, 3])
    sel = cs1.selectbox(
        "Candidata a operar (por criterio)", perfiles,
        index=perfiles.index(st.session_state.df_perfil) if st.session_state.df_perfil in perfiles else 0,
        key="df_selperfil")
    st.session_state.df_perfil = sel
    if reco:
        cs2.caption(f"Recomendada por el motor (DRO): **{reco}**. "
                    f"{'Estas operando la recomendada.' if sel == reco else 'Estas operando otra candidata.'}")

    ev = next((e for e in res["evaluaciones"] if e["perfil"] == sel), None)
    k = (ev or {}).get("kpis", {})
    kpi_row([
        {"label": "Perfil", "value": sel + ("  ★" if sel == reco else "")},
        {"label": "OTD", "value": f"{k.get('otd', 0) * 100:.1f}%",
         "helptext": "Entregas a tiempo esperadas (nominal)"},
        {"label": "OTIF", "value": f"{k.get('otif', 0) * 100:.1f}%",
         "helptext": "A tiempo Y completo (primer intento)"},
        {"label": "Variabilidad OTD", "value": f"±{k.get('variabilidad', 0) * 100:.1f} pts",
         "helptext": "Desv. estandar del OTD entre escenarios Monte Carlo (menor = mejor)"},
        {"label": "OTD peor caso", "value": f"{k.get('otd_peor', 0) * 100:.1f}%",
         "helptext": "Bajo el peor escenario del conjunto de ambiguedad (DRO)"},
    ])
    st.success(f"**Recomendacion:** {res['recomendacion']['explicacion']}")

    mc1, mc2 = st.columns([7, 5], gap="large")
    with mc1:
        st.markdown("**Ruta de la candidata seleccionada**")
        esc = res["escenarios"].get(sel)
        if esc:
            _mapa_escenario(esc)
    with mc2:
        if es_robusto(res) and ev is not None:
            st.plotly_chart(fig_robustez_por_escenario(ev), use_container_width=True, config=PLOT_CFG)

    rc1, rc2 = st.columns(2, gap="large")
    with rc1:
        st.plotly_chart(fig_ranking_robusto(res), use_container_width=True, config=PLOT_CFG)
    with rc2:
        iri = tabla_iri(res)
        if not iri.empty:
            st.plotly_chart(fig_iri_clasificacion(iri), use_container_width=True, config=PLOT_CFG)

    st.markdown("**Comparativa de candidatas**")
    st.dataframe(tabla_candidatas(res).round(3), use_container_width=True, hide_index=True)

    _nav(siguiente_label="Enviar al Gemelo Digital →", siguiente_ok=bool(res.get("escenarios")))


# ------------------------------------------------------------------ Paso 4: Gemelo
def _resultados(esc_ini, esc_inc, esc_fin, incidencias):
    r_inc = resumen_operacion(esc_inc, incidencias)
    r_fin = resumen_operacion(esc_fin, incidencias)
    var = variabilidad_operacion(esc_ini, tasa=st.session_state.df_tasa / 100.0,
                                 n_corridas=25, seed=0)
    tab_g, tab_c, tab_i, tab_cmp = st.tabs(
        ["Generales", "Por camion", "Incidencias", "Inicial vs final"])

    with tab_g:
        d = (r_fin["otd"] - r_inc["otd"]) * 100
        kpi_row([
            {"label": "OTD (con re-ruteo)", "value": f"{r_fin['otd'] * 100:.1f}%",
             "delta": f"{d:+.1f} pts vs base" if abs(d) > 1e-9 else None,
             "delta_dir": "up" if d > 1e-9 else "flat",
             "helptext": "Entregas dentro de ventana tras el re-ruteo recomendado"},
            {"label": "OTIF", "value": f"{r_fin['otif'] * 100:.1f}%",
             "helptext": "A tiempo Y completo (primer intento)"},
            {"label": "Variabilidad", "value": f"±{var['otd_std'] * 100:.1f} pts",
             "helptext": f"σ del OTD en {var['n']} corridas con incidencias"},
            {"label": "Fuera de ventana", "value": str(r_fin["fuera_ventana"])},
            {"label": "Fallidas 1er intento", "value": str(r_fin["fallidas_primer_intento"])},
        ])
        g1, g2 = st.columns(2, gap="large")
        with g1:
            st.plotly_chart(fig_entregas_por_hora(tabla_operacion(esc_fin)),
                            use_container_width=True, config=PLOT_CFG)
        with g2:
            st.plotly_chart(fig_estado_final(tabla_operacion(esc_fin)),
                            use_container_width=True, config=PLOT_CFG)
        st.plotly_chart(fig_variabilidad(var), use_container_width=True, config=PLOT_CFG)

    with tab_c:
        tc = tabla_por_camion(esc_fin)
        st.plotly_chart(fig_otd_otif_camion(tc), use_container_width=True, config=PLOT_CFG)
        st.plotly_chart(fig_tardanza_por_vehiculo(tabla_operacion(esc_fin)),
                        use_container_width=True, config=PLOT_CFG)
        st.dataframe(tc, use_container_width=True, hide_index=True)

    with tab_i:
        ag = agregados_incidencias(incidencias)
        ki1, ki2, ki3 = st.columns(3)
        ki1.metric("Incidencias", ag["n"])
        ki2.metric("Impacto total", f"{ag['impacto_total_min']:.0f} min")
        ki3.metric("Alertas disparadas", r_inc["alertas"])
        i1, i2 = st.columns(2, gap="large")
        with i1:
            st.plotly_chart(fig_incidencias_por_tipo(ag), use_container_width=True, config=PLOT_CFG)
        with i2:
            st.plotly_chart(fig_incidencias_por_franja(ag), use_container_width=True, config=PLOT_CFG)
        ti = tabla_incidencias(incidencias)
        if not ti.empty:
            st.dataframe(ti[["hora", "vehiculo_id", "pedido_id", "descripcion", "severidad",
                             "franja", "distrito", "retraso_min"]],
                         use_container_width=True, hide_index=True)
        else:
            st.caption("Sin incidencias en esta jornada.")

    with tab_cmp:
        cmp = comparar_rutas(esc_inc, esc_fin)
        solo_cambio = st.toggle("Solo camiones con ruta cambiada", value=False, key="df_cmpfilt")
        vista = cmp[cmp["cambiada"]] if solo_cambio else cmp
        n_cambio = int(cmp["cambiada"].sum())
        rec = int(cmp["delta_a_tiempo"].clip(lower=0).sum())
        st.caption(f"{n_cambio} de {len(cmp)} camiones re-secuenciados · "
                   f"+{rec} entregas a tiempo recuperadas por el re-ruteo recomendado.")
        st.dataframe(vista[["vehiculo_id", "cambiada", "orden_inicial", "orden_final",
                            "delta_a_tiempo", "delta_tardanza_min"]],
                     use_container_width=True, hide_index=True)


def _paso_gemelo():
    st.markdown("#### Paso 4 · Gemelo Digital Operativo")
    res = st.session_state.df_plan
    perfil = st.session_state.df_perfil
    esc_ini = (res or {}).get("escenarios", {}).get(perfil) if res else None
    if not esc_ini:
        st.warning("Primero ejecuta el motor y elige una candidata (paso 3).")
        _nav(siguiente_label=None)
        return

    c1, c2, c3 = st.columns([2.4, 1.2, 1.4])
    st.session_state.df_tasa = c1.slider("Intensidad de incidencias (%)", 0, 40,
                                         int(st.session_state.df_tasa), key="df_int")
    st.session_state.df_seed = c2.number_input("Semilla", 0, 9999, int(st.session_state.df_seed),
                                               key="df_seedin")
    st.caption(f"Candidata en operacion: **{perfil}**  ·  gemelo simulado, no tiempo real.")

    esc_inc, incidencias = simular_incidencias(
        esc_ini, tasa=st.session_state.df_tasa / 100.0, seed=int(st.session_state.df_seed))
    esc_fin, _ = mitigar_con_reruteo(esc_inc)

    tab_op, tab_res = st.tabs(["Operacion (en vivo)", "Resultados"])
    with tab_op:
        components.html(html_gemelo(esc_inc, altura=460), height=900, scrolling=False)
    with tab_res:
        _resultados(esc_ini, esc_inc, esc_fin, incidencias)

    st.session_state["df_esc_export"] = {"ini": esc_inc, "fin": esc_fin, "inc": incidencias}
    render_divider()
    cc1, cc2, cc3 = st.columns(3)
    if cc1.button("← Atras", use_container_width=True, key="df_g_prev"):
        st.session_state.df_step = 3
        st.rerun()
    if cc2.button("Ver hoja de ruta del conductor", use_container_width=True, key="df_condbtn"):
        st.session_state.df_conductor = True
        st.rerun()
    if cc3.button("Ir a exportacion →", type="primary", use_container_width=True, key="df_tolast"):
        st.session_state.df_step = 5
        st.rerun()


# ------------------------------------------------------------------ Conductor
def _vista_conductor():
    render_view_title("Hoja de ruta del conductor",
                      "Ruta final (re-planificada) que debe seguir cada vehiculo: orden de "
                      "paradas, ETA, ventana y distrito.", eyebrow="Demostracion / Conductor")
    data = st.session_state.get("df_esc_export")
    if not data:
        st.info("Genera la operacion en el gemelo (paso 4) para ver la hoja de ruta.")
    else:
        esc = data["fin"]
        veh = st.selectbox("Vehiculo", list(esc["rutas"].keys()), key="df_condveh")
        paradas = esc["rutas"][veh]
        import pandas as pd
        filas = [{"orden": i + 1, "pedido": p["pedido_id"], "distrito": p.get("distrito", "-"),
                  "ETA": f"{int(p['eta_min'])//60:02d}:{int(p['eta_min'])%60:02d}",
                  "ventana_fin": f"{int(p['ventana_fin_min'])//60:02d}:{int(p['ventana_fin_min'])%60:02d}",
                  "estado": "A tiempo" if p.get("tardanza_min", 0) <= 0 else "Fuera de ventana"}
                 for i, p in enumerate(paradas)]
        cambiada = any(p.get("incidencia") for p in paradas)
        if cambiada:
            st.warning("La ruta de este vehiculo fue re-secuenciada por una incidencia.")
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    render_divider()
    if st.button("Volver al gemelo", key="df_condback"):
        st.session_state.df_conductor = False
        st.rerun()
    render_footer()


# ------------------------------------------------------------------ Paso 5: Export
def _paso_export():
    st.markdown("#### Paso 5 · Exportacion")
    res = st.session_state.df_plan
    data = st.session_state.get("df_esc_export")
    if res:
        st.download_button("Candidatas (CSV)",
                           tabla_candidatas(res).to_csv(index=False).encode("utf-8"),
                           "cortex_candidatas.csv", "text/csv", use_container_width=True)
        iri = tabla_iri(res)
        st.download_button("IRI por pedido (CSV)", iri.to_csv(index=False).encode("utf-8"),
                           "cortex_iri.csv", "text/csv", use_container_width=True)
    if data:
        st.download_button("Resultados de operacion (CSV)",
                           tabla_operacion(data["fin"]).to_csv(index=False).encode("utf-8"),
                           "cortex_operacion.csv", "text/csv", use_container_width=True)
        st.download_button("Incidencias (CSV)",
                           tabla_incidencias(data["inc"]).to_csv(index=False).encode("utf-8"),
                           "cortex_incidencias.csv", "text/csv", use_container_width=True)
        st.download_button("Comparacion inicial vs final (CSV)",
                           comparar_rutas(data["ini"], data["fin"]).to_csv(index=False).encode("utf-8"),
                           "cortex_comparacion.csv", "text/csv", use_container_width=True)
    st.success("Jornada completada. Descarga los reportes para tu analisis o defensa.")
    _nav(siguiente_label=None)


# ------------------------------------------------------------------ Orquestador
def render():
    _init()
    render_view_title(
        "Demostracion interactiva",
        "Flujo guiado: cargar datos, configurar el motor, generar y elegir rutas, operar el "
        "gemelo digital y exportar. El Motor de Decision es transversal a todo el flujo.",
        eyebrow="CORTEX-LM / Demostracion")

    if st.session_state.df_conductor:
        _vista_conductor()
        return

    _stepper(st.session_state.df_step)
    paso = st.session_state.df_step
    if paso == 1:
        _paso_datos()
    elif paso == 2:
        _paso_params()
    elif paso == 3:
        _paso_motor()
    elif paso == 4:
        _paso_gemelo()
    else:
        _paso_export()

    render_divider()
    if st.button("Salir al inicio", key="df_home"):
        st.session_state.vista = VISTA_HOME
        st.session_state.modo = None
        st.rerun()
    render_footer()
