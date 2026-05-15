"""Componentes tipo card y KPI - estetica SaaS premium, sin emojis."""
import streamlit as st
from utils.constants import COLOR_ESTADO


def kpi(label: str, value, delta: str = None, delta_dir: str = "flat", helptext: str = ""):
    """Renderiza una tarjeta KPI tipograficamente sobria."""
    delta_html = ""
    if delta is not None:
        cls = delta_dir if delta_dir in ("up", "down", "flat") else "flat"
        delta_html = f'<div class="dss-kpi-delta {cls}">{delta}</div>'
    title_attr = f' title="{helptext}"' if helptext else ""
    st.markdown(f"""
    <div class="dss-kpi">
      <div class="dss-kpi-label"{title_attr}>{label}</div>
      <div class="dss-kpi-value">{value}</div>
      {delta_html}
    </div>
    """, unsafe_allow_html=True)


def kpi_row(items: list):
    if not items:
        return
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        with col:
            kpi(**item)


def info_card(title: str, description: str = "", eyebrow: str = ""):
    """Card informativa minimalista con eyebrow opcional."""
    eyebrow_html = f'<div class="dss-eyebrow">{eyebrow}</div>' if eyebrow else ""
    st.markdown(f"""
    <div class="dss-card">
      {eyebrow_html}
      <div class="dss-card-title">{title}</div>
      <div class="dss-card-desc">{description}</div>
    </div>
    """, unsafe_allow_html=True)


def feature_card(eyebrow: str, title: str, description: str):
    """Card grande para landing / seleccion de modo o rol."""
    st.markdown(f"""
    <div class="dss-card-feature">
      <div class="dss-eyebrow">{eyebrow}</div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
    """, unsafe_allow_html=True)


def status_badge(estado: str) -> str:
    """Devuelve HTML de badge para un estado de entrega."""
    color = COLOR_ESTADO.get(estado, "#667085")
    bg = color + "14"
    return f'<span class="dss-badge" style="color:{color}; background:{bg}; border-color:{color}33;">{estado}</span>'


def render_dataset_summary_card(dataset: dict):
    if not dataset:
        return
    pedidos = dataset.get("pedidos")
    vehiculos = dataset.get("vehiculos")
    zonas = dataset.get("zonas_operativas")
    n_pedidos = len(pedidos) if pedidos is not None else 0
    n_veh = len(vehiculos) if vehiculos is not None else 0
    n_zonas = len(zonas) if zonas is not None else 0
    peso_total = 0
    if pedidos is not None and "peso_kg" in pedidos.columns:
        peso_total = float(pedidos["peso_kg"].sum())

    kpi_row([
        {"label": "Pedidos", "value": n_pedidos},
        {"label": "Vehiculos", "value": n_veh},
        {"label": "Zonas operativas", "value": n_zonas},
        {"label": "Peso total", "value": f"{peso_total:,.0f} kg"},
    ])
