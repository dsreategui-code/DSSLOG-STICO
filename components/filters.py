"""Filtros reutilizables para vistas de resultados."""
import streamlit as st
import pandas as pd

from utils.constants import ESTADOS_ENTREGA, ZONAS_OPERATIVAS, TIPOS_SERVICIO


def render_filters(entregas: pd.DataFrame, escenarios: list = None,
                   key_prefix: str = "flt", show_escenario: bool = False,
                   show_iteracion: bool = False) -> dict:
    """Renderiza una barra de filtros y devuelve un dict con las selecciones.

    Cada filtro usa una opcion "Todos" para no acotar.
    """
    filtros = {}
    cols = st.columns(6)

    with cols[0]:
        if show_escenario and escenarios:
            filtros["escenario"] = st.selectbox(
                "Escenario", ["Todos"] + escenarios, key=f"{key_prefix}_escenario"
            )
        else:
            filtros["escenario"] = "Todos"

    with cols[1]:
        if entregas is not None and "vehiculo_id" in entregas.columns:
            vehiculos = sorted(entregas["vehiculo_id"].dropna().unique().tolist())
        else:
            vehiculos = []
        filtros["vehiculo"] = st.selectbox(
            "Vehiculo", ["Todos"] + vehiculos, key=f"{key_prefix}_vehiculo"
        )

    with cols[2]:
        if show_iteracion and entregas is not None and "iteracion" in entregas.columns:
            iters = sorted(entregas["iteracion"].dropna().unique().tolist())
            filtros["iteracion"] = st.selectbox(
                "Iteracion", ["Todas"] + iters, key=f"{key_prefix}_iteracion"
            )
        else:
            filtros["iteracion"] = "Todas"

    with cols[3]:
        zonas_disp = ZONAS_OPERATIVAS
        if entregas is not None and "zona" in entregas.columns:
            zonas_disp = sorted(entregas["zona"].dropna().unique().tolist()) or ZONAS_OPERATIVAS
        filtros["zona"] = st.selectbox(
            "Zona", ["Todas"] + zonas_disp, key=f"{key_prefix}_zona"
        )

    with cols[4]:
        tipos = TIPOS_SERVICIO
        if entregas is not None and "tipo_servicio" in entregas.columns:
            tipos = sorted(entregas["tipo_servicio"].dropna().unique().tolist()) or TIPOS_SERVICIO
        filtros["tipo_servicio"] = st.selectbox(
            "Tipo de servicio", ["Todos"] + tipos, key=f"{key_prefix}_tipo"
        )

    with cols[5]:
        filtros["estado"] = st.selectbox(
            "Estado de entrega", ["Todos"] + ESTADOS_ENTREGA, key=f"{key_prefix}_estado"
        )

    return filtros


def apply_filters(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """Aplica los filtros sobre un dataframe de entregas."""
    if df is None or df.empty:
        return df
    out = df.copy()
    mapping = {
        "vehiculo": "vehiculo_id",
        "iteracion": "iteracion",
        "zona": "zona",
        "tipo_servicio": "tipo_servicio",
        "estado": "estado",
        "escenario": "escenario",
    }
    for fkey, col in mapping.items():
        val = filtros.get(fkey)
        if val and val not in ("Todos", "Todas") and col in out.columns:
            out = out[out[col] == val]
    return out
