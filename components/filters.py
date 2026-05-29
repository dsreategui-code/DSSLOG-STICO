"""Filtros reutilizables para vistas de resultados.

Orden de prioridad de filtros:
    1. Escenario  (solo Validacion; oculto en Demostracion)
    2. Vehiculo
    3. Zona
    4. Tipo de servicio
    5. Estado de entrega
"""
import streamlit as st
import pandas as pd

from utils.constants import ESTADOS_ENTREGA, ZONAS_OPERATIVAS, TIPOS_SERVICIO


def render_filters(entregas: pd.DataFrame, escenarios: list = None,
                   escenarios_labels: dict = None,
                   key_prefix: str = "flt",
                   show_escenario: bool = False) -> dict:
    """Renderiza la barra de filtros y devuelve un dict con las selecciones.

    Args:
        entregas: dataframe de referencia para poblar opciones dinamicas.
        escenarios: lista de ids de escenario (solo si show_escenario=True).
        escenarios_labels: mapping id -> etiqueta visible (solo Validacion).
        show_escenario: True en Validacion, False en Demostracion.
    """
    filtros = {"escenario": "Todos", "iteracion": "Todas"}

    # Columnas dinamicas segun si se muestra escenario
    n_cols = 5 if show_escenario else 4
    cols = st.columns(n_cols)
    idx = 0

    # 1) Escenario (solo Validacion)
    if show_escenario and escenarios:
        with cols[idx]:
            labels = escenarios_labels or {}

            def _fmt(x):
                return "Todos" if x == "Todos" else labels.get(x, x)

            filtros["escenario"] = st.selectbox(
                "Escenario", ["Todos"] + list(escenarios),
                format_func=_fmt, key=f"{key_prefix}_escenario",
            )
        idx += 1

    # 2) Vehiculo
    with cols[idx]:
        if entregas is not None and "vehiculo_id" in entregas.columns:
            vehiculos = sorted(entregas["vehiculo_id"].dropna().unique().tolist())
        else:
            vehiculos = []
        filtros["vehiculo"] = st.selectbox(
            "Vehiculo", ["Todos"] + vehiculos, key=f"{key_prefix}_vehiculo",
        )
    idx += 1

    # 3) Zona
    with cols[idx]:
        zonas_disp = ZONAS_OPERATIVAS
        if entregas is not None and "zona" in entregas.columns:
            opciones = sorted(entregas["zona"].dropna().unique().tolist())
            if opciones:
                zonas_disp = opciones
        filtros["zona"] = st.selectbox(
            "Zona", ["Todas"] + list(zonas_disp), key=f"{key_prefix}_zona",
        )
    idx += 1

    # 4) Tipo de servicio
    with cols[idx]:
        tipos = TIPOS_SERVICIO
        if entregas is not None and "tipo_servicio" in entregas.columns:
            opciones = sorted(entregas["tipo_servicio"].dropna().unique().tolist())
            if opciones:
                tipos = opciones
        filtros["tipo_servicio"] = st.selectbox(
            "Tipo de servicio", ["Todos"] + list(tipos), key=f"{key_prefix}_tipo",
        )
    idx += 1

    # 5) Estado de entrega
    with cols[idx]:
        filtros["estado"] = st.selectbox(
            "Estado de entrega", ["Todos"] + list(ESTADOS_ENTREGA),
            key=f"{key_prefix}_estado",
        )

    return filtros


# Orden en el que se aplican (escenario y vehiculo primero, como pide el spec)
_APPLY_ORDER = [
    ("escenario",     "escenario"),
    ("vehiculo",      "vehiculo_id"),
    ("zona",          "zona"),
    ("tipo_servicio", "tipo_servicio"),
    ("estado",        "estado"),
]


def apply_filters(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """Aplica los filtros sobre un dataframe de entregas."""
    if df is None or df.empty:
        return df
    out = df
    for fkey, col in _APPLY_ORDER:
        val = filtros.get(fkey)
        if val and val not in ("Todos", "Todas") and col in out.columns:
            out = out[out[col] == val]
    return out
