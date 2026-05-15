"""Botones jerarquizados sobrios, sin iconografia emoji."""
import streamlit as st


def primary(label: str, key: str = None, disabled: bool = False,
            use_container_width: bool = False) -> bool:
    return st.button(
        label, key=key, type="primary",
        disabled=disabled, use_container_width=use_container_width,
    )


def secondary(label: str, key: str = None, disabled: bool = False,
              use_container_width: bool = False) -> bool:
    return st.button(
        label, key=key, type="secondary",
        disabled=disabled, use_container_width=use_container_width,
    )


def link_button(label: str, url: str) -> None:
    st.link_button(label, url, use_container_width=False)


def nav_bar(prev_label: str = "Volver", next_label: str = "Continuar",
            prev_disabled: bool = False, next_disabled: bool = False,
            prev_key: str = "btn_prev", next_key: str = "btn_next") -> tuple:
    """Barra de navegacion inferior."""
    col_l, _, col_r = st.columns([1, 4, 1])
    with col_l:
        prev = secondary(prev_label, key=prev_key, disabled=prev_disabled,
                         use_container_width=True)
    with col_r:
        nxt = primary(next_label, key=next_key, disabled=next_disabled,
                      use_container_width=True)
    return prev, nxt
