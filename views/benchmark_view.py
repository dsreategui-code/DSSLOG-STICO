"""Vista Streamlit del modo Benchmark literatura (ALM RRC).

Aislada del flujo DSS. Usa los componentes visuales existentes (sin CSS nuevo).
Si el cache no esta preparado, muestra instrucciones claras y no rompe la app.
"""
import streamlit as st
import pandas as pd

from components.layout import (
    render_view_title, render_divider, render_footer, render_empty_state,
)
from components.buttons import primary, secondary
from components.cards import kpi_row
from utils.constants import VISTA_HOME
from utils.formatters import fmt_pct, fmt_num
from benchmark import paths, alm_loader, runner, metrics


def _volver_inicio():
    st.session_state.vista = VISTA_HOME
    st.session_state.modo = None
    st.session_state.rol = None
    st.rerun()


def render():
    render_view_title(
        "Benchmark con literatura",
        "Compara el motor de ruteo del DSS contra rutas reales del Amazon Last Mile "
        "Routing Research Challenge (ALM RRC 2021). Evalua secuenciacion y tiempos sobre "
        "la matriz real de cada ruta, sin mezclar variables locales de Lima.",
        eyebrow="ALM RRC 2021  /  Validacion externa",
    )

    # 1) Dataset transformado ausente.
    if not paths.benchmark_disponible():
        render_empty_state(
            "Dataset ALM RRC no encontrado",
            "Coloca el dataset transformado en data_benchmark/processed_csv/ "
            "(06_dss_pedidos_base.csv y 05_travel_times_long.csv, entre otros).",
        )
        render_divider()
        if secondary("Inicio", key="bm_back_1"):
            _volver_inicio()
        render_footer()
        return

    # 2) Cache no preparado.
    if not alm_loader.cache_listo():
        render_empty_state(
            "Cache de benchmark no preparado",
            "Ejecuta una sola vez en la terminal: "
            "python -m benchmark.prepare_cache --n-rutas 30",
        )
        st.caption(
            "El archivo de tiempos pesa ~9.5 GB; la preparacion extrae una muestra "
            "compacta para que la app no cargue ese archivo en tiempo de ejecucion."
        )
        render_divider()
        if secondary("Inicio", key="bm_back_2"):
            _volver_inicio()
        render_footer()
        return

    # 3) Cache listo: seleccion + ejecucion.
    indice = alm_loader.cargar_indice()
    st.caption(f"Rutas disponibles en el cache: {len(indice)}  |  "
               f"Fuente: ALM RRC 2021 (transformado).")

    col_a, col_b, col_c = st.columns([3, 1, 1])
    with col_a:
        opciones = indice["route_id"].tolist()
        seleccion = st.multiselect(
            "Rutas a evaluar (vacio = todas las del cache)",
            options=opciones,
            default=st.session_state.get("benchmark_seleccion") or opciones[:min(10, len(opciones))],
            format_func=lambda r: f"{r[:18]}...  ({_paradas(indice, r)} paradas)",
        )
    with col_b:
        motor = st.selectbox("Motor", ["auto", "ortools", "greedy"], index=0)
    with col_c:
        time_limit = st.slider("Limite (s)", 2, 30, 10)

    usar_ventanas = st.toggle(
        "Aplicar ventanas horarias confiables como restriccion", value=False,
        help="Por defecto desactivado: el benchmark compara calidad de ruteo/secuencia.",
    )

    if primary("Ejecutar benchmark", key="bm_run"):
        rutas = seleccion or opciones
        st.session_state.benchmark_seleccion = seleccion
        barra = st.progress(0)
        estado = st.empty()

        def _cb(i, total, rid):
            barra.progress(i / max(total, 1))
            estado.caption(f"Procesando {i}/{total}: {rid[:24]}...")

        df = runner.correr_benchmark(
            route_ids=rutas, motor=motor, time_limit_seconds=time_limit,
            usar_ventanas=usar_ventanas, progress_callback=_cb,
        )
        st.session_state.benchmark_resultados = df
        estado.empty()
        barra.empty()
        st.success(f"Benchmark completado sobre {len(df)} rutas.")

    df = st.session_state.get("benchmark_resultados")
    if df is not None and not df.empty:
        _render_resultados(df)

    render_divider()
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Inicio", key="bm_back_3", use_container_width=True):
            _volver_inicio()
    with col_r:
        if df is not None and not df.empty:
            st.download_button(
                "Descargar CSV", data=df.to_csv(index=False).encode("utf-8"),
                file_name="benchmark_almrrc.csv", mime="text/csv",
                use_container_width=True,
            )

    render_footer()


def _paradas(indice: pd.DataFrame, rid: str) -> int:
    fila = indice[indice["route_id"] == rid]
    return int(fila["total_paradas"].iloc[0]) if not fila.empty else 0


def _render_resultados(df: pd.DataFrame):
    resumen = metrics.resumen_global(df.to_dict("records"))
    if resumen:
        st.markdown("#### Resumen global (rutas High Quality)")
        kpi_row([
            {"label": "Rutas evaluadas", "value": resumen.get("rutas_evaluadas", 0)},
            {"label": "SDstop prom.",
             "value": fmt_num(resumen.get("sd_stop_promedio"), 3)},
            {"label": "SDzone prom.",
             "value": fmt_num(resumen.get("sd_zone_promedio"), 3)},
            {"label": "ERPratio prom. (min)",
             "value": fmt_num(resumen.get("erp_ratio_promedio_min"), 2)},
        ])
        kpi_row([
            {"label": "Score aprox. prom.",
             "value": fmt_num(resumen.get("score_aprox_promedio"), 4)},
            {"label": "Brecha tiempo prom.",
             "value": fmt_pct(resumen.get("brecha_pct_promedio"))},
            {"label": "Tiempo real prom. (min)",
             "value": fmt_num(resumen.get("tiempo_real_min_promedio"), 1)},
            {"label": "Computo prom. (s)",
             "value": fmt_num(resumen.get("tiempo_computo_seg_promedio"), 2)},
        ])
        st.caption(
            "SDstop / SDzone: desviacion de secuencia de paradas / de zonas frente a la "
            "ruta real (0 = mismo orden; mayor = mas distinto). "
            "ERPratio: penalizacion promedio por desviacion en minutos sobre la matriz real. "
            "Score aprox. = SDstop x ERPratio (proxy del score ALM RRC, no el oficial). "
            "Brecha = (tiempo DSS - tiempo real)/tiempo real; negativa = DSS mas rapido."
        )
        st.write("")

    errores = df[df["status"].astype(str).str.startswith("error")]
    if not errores.empty:
        st.warning(f"{len(errores)} ruta(s) con error; se muestran con status de error.")

    st.markdown("#### Detalle por ruta")
    st.dataframe(df, hide_index=True, use_container_width=True, height=420)
