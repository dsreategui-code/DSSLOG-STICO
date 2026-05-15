"""Modales para confirmaciones y detalle de alertas - sin emojis."""
import streamlit as st


def confirm_dialog(title: str, message: str, confirm_label: str = "Confirmar",
                   cancel_label: str = "Cancelar", key: str = "confirm") -> bool:
    """Bloque de confirmacion inline."""
    with st.container():
        st.markdown(f"""
        <div class="dss-card" style="border-color: var(--c-primary);">
          <div class="dss-eyebrow">Confirmacion</div>
          <div class="dss-card-title">{title}</div>
          <div class="dss-card-desc">{message}</div>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        col_a, col_b = st.columns([1, 1])
        with col_a:
            confirmed = st.button(confirm_label, key=f"{key}_yes", type="primary",
                                  use_container_width=True)
        with col_b:
            st.button(cancel_label, key=f"{key}_no", use_container_width=True)
    return confirmed


def render_replanificacion_modal(alerta: dict, key: str = "alert"):
    """Detalle de una replanificacion sugerida con accion aprobar / rechazar."""
    st.markdown(f"""
    <div class="dss-card" style="border-color: var(--c-warning);">
      <div class="dss-eyebrow">Replanificacion sugerida</div>
      <div class="dss-card-title">Vehiculo {alerta.get('vehiculo_id', '-')}</div>
      <div class="dss-card-desc">{alerta.get('motivo', '')}</div>
    </div>
    """, unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Ruta actual**")
        st.code(" > ".join(alerta.get("ruta_actual", [])) or "-", language="text")
        st.caption(
            f"Tiempo estimado: {alerta.get('tiempo_actual_min', 0):.0f} min  "
            f"|  OTD proyectado: {alerta.get('otd_actual', 0):.1f}%"
        )
    with col_b:
        st.markdown("**Ruta propuesta**")
        st.code(" > ".join(alerta.get("ruta_propuesta", [])) or "-", language="text")
        st.caption(
            f"Tiempo estimado: {alerta.get('tiempo_propuesto_min', 0):.0f} min  "
            f"|  OTD proyectado: {alerta.get('otd_propuesto', 0):.1f}%"
        )

    st.write("")
    cA, cB, _ = st.columns([1, 1, 3])
    aprobado, rechazado = False, False
    with cA:
        aprobado = st.button("Aprobar", key=f"{key}_aprobar", type="primary",
                             use_container_width=True)
    with cB:
        rechazado = st.button("Rechazar", key=f"{key}_rechazar",
                              use_container_width=True)
    return aprobado, rechazado


def render_info_modal(title: str, message: str):
    st.markdown(f"""
    <div class="dss-card">
      <div class="dss-card-title">{title}</div>
      <div class="dss-card-desc">{message}</div>
    </div>
    """, unsafe_allow_html=True)
