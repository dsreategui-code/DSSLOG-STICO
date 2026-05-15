"""Validacion - Carga de datos."""
import sys
import subprocess
import streamlit as st

from components.layout import (
    render_view_title, render_divider, render_footer, render_empty_state,
)
from components.navigation import render_step_breadcrumb, navigate_to, back_home
from components.buttons import primary, secondary
from components.cards import render_dataset_summary_card
from components.tables import (
    render_pedidos_resumen, render_pedidos_expandida,
    render_vehiculos, render_summary_table,
)
from services.data_loader import dataset_exists, load_dataset, get_dataset_meta
from utils.validators import validate_dataset_dir, validate_dataframes
from utils.state import log_bitacora
from utils.constants import VISTA_VALIDATION_CONFIG
from config.settings import DEMO_DATASET_DIR, PROJECT_ROOT


def _generar_dataset() -> bool:
    """Ejecuta generar_dataset_sintetico.py como subproceso."""
    script = PROJECT_ROOT / "generar_dataset_sintetico.py"
    if not script.exists():
        st.error("No se encontro generar_dataset_sintetico.py en la raiz del proyecto.")
        return False
    with st.spinner("Generando dataset sintetico..."):
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
    if result.returncode != 0:
        st.error("Error generando el dataset.")
        with st.expander("Detalle tecnico"):
            st.code((result.stderr or result.stdout) or "Sin salida.")
        return False
    return True


def _cargar_dataset():
    res_dir = validate_dataset_dir(DEMO_DATASET_DIR)
    if not res_dir.ok:
        for e in res_dir.errors:
            st.error(e)
        return
    try:
        ds = load_dataset(DEMO_DATASET_DIR)
    except Exception as e:
        st.error(f"No se pudo cargar el dataset: {e}")
        return

    res = validate_dataframes(ds)
    st.session_state.dataset = ds
    st.session_state.dataset_path = str(DEMO_DATASET_DIR)
    st.session_state.dataset_validado = res.ok

    for w in res.warnings:
        st.warning(w)
    for e in res.errors:
        st.error(e)
    if res.ok:
        st.success("Dataset cargado y validado correctamente.")
        n_p = len(ds.get("pedidos", []))
        n_v = len(ds.get("vehiculos", []))
        log_bitacora("Validacion - carga de dataset", f"{n_p} pedidos · {n_v} vehiculos")


def render():
    render_view_title(
        "Carga de datos",
        "Genera o carga el dataset sintetico, valida su estructura y previsualiza los "
        "pedidos y la flota antes de configurar la simulacion."
    )
    render_step_breadcrumb()

    meta = get_dataset_meta(DEMO_DATASET_DIR)

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if primary("Generar dataset sintetico", key="val_gen_ds",
                   use_container_width=True):
            if _generar_dataset():
                st.success("Dataset generado correctamente.")
                log_bitacora("Validacion - generacion de dataset", f"Ruta: {DEMO_DATASET_DIR}")
                st.rerun()
    with col2:
        if primary("Cargar dataset", key="val_load_ds",
                   disabled=not dataset_exists(DEMO_DATASET_DIR),
                   use_container_width=True):
            _cargar_dataset()
    with col3:
        if meta.get("existe"):
            render_summary_table([
                {"clave": "Ruta", "valor": meta["ruta"]},
                {"clave": "Archivos", "valor": meta["archivos"]},
                {"clave": "Tamano", "valor": f"{meta['tamano_kb']} KB"},
            ])
        else:
            st.caption("Aun no se ha generado el dataset.")

    render_divider()

    ds = st.session_state.get("dataset")
    if ds:
        render_dataset_summary_card(ds)
        st.write("")
        tab_resumen, tab_pedidos, tab_vehiculos = st.tabs(
            ["Resumen", "Pedidos", "Vehiculos"]
        )
        with tab_resumen:
            render_pedidos_resumen(ds.get("pedidos"), ds.get("vehiculos"))
        with tab_pedidos:
            render_pedidos_expandida(ds.get("pedidos"))
        with tab_vehiculos:
            render_vehiculos(ds.get("vehiculos"))
    else:
        render_empty_state(
            "Aun no has cargado el dataset",
            "Genera el dataset sintetico o, si ya existe, presiona Cargar dataset.",
        )

    render_divider()
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        if secondary("Inicio", key="val_data_home",
                     use_container_width=True):
            back_home()
    with col_r:
        if primary("Configuracion", key="val_data_next",
                   use_container_width=True,
                   disabled=not st.session_state.get("dataset_validado")):
            navigate_to(VISTA_VALIDATION_CONFIG)

    render_footer()
