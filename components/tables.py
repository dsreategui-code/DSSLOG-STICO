"""Tablas profesionales y resumenes tabulares."""
import streamlit as st
import pandas as pd


def render_dataframe(df: pd.DataFrame, height: int = 360, use_container_width: bool = True):
    if df is None or df.empty:
        st.info("No hay datos para mostrar.")
        return
    st.dataframe(df, height=height, use_container_width=use_container_width, hide_index=True)


def render_summary_table(rows: list):
    """Tabla compacta clave/valor."""
    if not rows:
        return
    body = "".join(
        f"<tr><td style='color:#64748B; width:35%;'>{r['clave']}</td>"
        f"<td><strong>{r['valor']}</strong></td></tr>"
        for r in rows
    )
    st.markdown(f"""
    <table class="dss-table">
      <tbody>{body}</tbody>
    </table>
    """, unsafe_allow_html=True)


def render_pedidos_resumen(pedidos: pd.DataFrame, vehiculos: pd.DataFrame = None):
    """Resumen agrupado por zona y por tipo de servicio."""
    if pedidos is None or pedidos.empty:
        st.info("No hay pedidos para mostrar.")
        return

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Pedidos por zona**")
        zona = (
            pedidos.groupby("zona")
            .agg(pedidos=("pedido_id", "count"), peso_total_kg=("peso_kg", "sum"))
            .reset_index()
            .sort_values("pedidos", ascending=False)
        )
        zona["peso_total_kg"] = zona["peso_total_kg"].round(0).astype(int)
        st.dataframe(zona, hide_index=True, use_container_width=True)

    with col_b:
        st.markdown("**Pedidos por tipo de servicio**")
        tipo = (
            pedidos.groupby("tipo_servicio")
            .agg(pedidos=("pedido_id", "count"), tiempo_prom_min=("tiempo_servicio_min", "mean"))
            .reset_index()
            .sort_values("pedidos", ascending=False)
        )
        tipo["tiempo_prom_min"] = tipo["tiempo_prom_min"].round(1)
        st.dataframe(tipo, hide_index=True, use_container_width=True)


def render_pedidos_expandida(pedidos: pd.DataFrame):
    """Tabla expandida con columnas operativas relevantes."""
    if pedidos is None or pedidos.empty:
        st.info("No hay pedidos para mostrar.")
        return
    cols = [
        "pedido_id", "cliente", "distrito", "zona", "modelo", "peso_kg",
        "tipo_servicio", "tiempo_servicio_min", "ventana_inicio", "ventana_fin",
    ]
    cols = [c for c in cols if c in pedidos.columns]
    st.dataframe(pedidos[cols], height=420, use_container_width=True, hide_index=True)


def render_vehiculos(vehiculos: pd.DataFrame):
    if vehiculos is None or vehiculos.empty:
        st.info("No hay vehiculos para mostrar.")
        return
    cols = ["vehiculo_id", "placa", "conductor", "zona_preferente",
            "capacidad_unidades", "capacidad_kg"]
    cols = [c for c in cols if c in vehiculos.columns]
    st.dataframe(vehiculos[cols], use_container_width=True, hide_index=True)
