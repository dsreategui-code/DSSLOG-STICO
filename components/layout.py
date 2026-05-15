"""Identidad visual y estilos globales - estetica SaaS premium, sin emojis."""
import streamlit as st
from config.settings import (
    APP_NAME, APP_SUBTITLE, APP_TAGLINE, APP_VERSION,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT, COLOR_BG, COLOR_CARD,
    COLOR_BORDER, COLOR_BORDER_STRONG, COLOR_TEXT, COLOR_MUTED, COLOR_SUBTLE,
    COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, COLOR_NEUTRAL,
)


BRAND_MARK_SVG = (
    '<svg width="28" height="28" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<rect width="28" height="28" rx="7" fill="#0C111D"/>'
    '<path d="M8 11.5L14 8.5L20 11.5V18L14 21L8 18V11.5Z" stroke="#FCFCFD" stroke-width="1.3" stroke-linejoin="round" fill="none"/>'
    '<path d="M8 11.5L14 14.5L20 11.5" stroke="#FCFCFD" stroke-width="1.3" stroke-linejoin="round"/>'
    '<path d="M14 14.5V21" stroke="#FCFCFD" stroke-width="1.3"/>'
    '</svg>'
)

GLOBAL_CSS = f"""
<style>
@import url('https://rsms.me/inter/inter.css');

:root {{
  --c-primary: {COLOR_PRIMARY};
  --c-secondary: {COLOR_SECONDARY};
  --c-accent: {COLOR_ACCENT};
  --c-bg: {COLOR_BG};
  --c-card: {COLOR_CARD};
  --c-border: {COLOR_BORDER};
  --c-border-strong: {COLOR_BORDER_STRONG};
  --c-text: {COLOR_TEXT};
  --c-muted: {COLOR_MUTED};
  --c-subtle: {COLOR_SUBTLE};
  --c-success: {COLOR_SUCCESS};
  --c-warning: {COLOR_WARNING};
  --c-danger: {COLOR_DANGER};
  --c-neutral: {COLOR_NEUTRAL};
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --ease: cubic-bezier(0.4, 0, 0.2, 1);
}}

/* Base */
html, body, [class*="css"], button, input, select, textarea {{
  font-family: 'Inter var', 'Inter', -apple-system, BlinkMacSystemFont,
               'Segoe UI', Roboto, sans-serif !important;
  font-feature-settings: 'cv11', 'ss01', 'ss03';
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--c-text);
}}
body {{ background: var(--c-bg) !important; }}
.stApp {{ background: var(--c-bg); }}

.main .block-container {{
  padding-top: 1.6rem;
  padding-bottom: 4rem;
  max-width: 1180px;
  animation: dss-page-in 280ms var(--ease);
}}

@keyframes dss-page-in {{
  from {{ opacity: 0; transform: translateY(2px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

/* Tipografia */
h1, h2, h3, h4, h5, h6 {{
  letter-spacing: -0.015em;
  color: var(--c-primary);
}}

/* Header */
.dss-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.4rem 0 1.4rem 0;
  border-bottom: 1px solid var(--c-border);
  margin-bottom: 1.6rem;
}}
.dss-brand {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
}}
.dss-brand-text {{
  display: flex; flex-direction: column; line-height: 1.1;
}}
.dss-brand-name {{
  font-size: 0.92rem; font-weight: 600; color: var(--c-primary);
  letter-spacing: -0.01em;
}}
.dss-brand-sub {{
  font-size: 0.74rem; color: var(--c-muted);
  letter-spacing: 0.02em; text-transform: uppercase;
  font-weight: 500;
}}
.dss-context-chip {{
  display: inline-flex; gap: 0.5rem; align-items: center;
  padding: 0.4rem 0.85rem;
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: 999px;
  font-size: 0.76rem;
  color: var(--c-muted);
  letter-spacing: -0.005em;
  transition: border-color 200ms var(--ease);
}}
.dss-context-chip strong {{
  color: var(--c-primary); font-weight: 600;
}}
.dss-context-chip::before {{
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  background: var(--c-success);
  display: inline-block;
}}

/* Titulos de vista */
.dss-view-title {{
  font-size: 1.7rem; font-weight: 600; color: var(--c-primary);
  margin: 0.4rem 0 0.35rem 0;
  letter-spacing: -0.02em;
  line-height: 1.2;
}}
.dss-view-desc {{
  font-size: 0.92rem; color: var(--c-muted);
  margin-bottom: 1.6rem;
  max-width: 760px;
  line-height: 1.55;
}}

.dss-eyebrow {{
  font-size: 0.7rem; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--c-subtle);
  font-weight: 600;
  margin-bottom: 0.35rem;
}}

/* Cards */
.dss-card {{
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  padding: 1.1rem 1.3rem;
  transition: border-color 200ms var(--ease), box-shadow 200ms var(--ease),
              transform 200ms var(--ease);
}}
.dss-card:hover {{
  border-color: var(--c-border-strong);
}}
.dss-card-title {{
  font-size: 0.93rem; font-weight: 600; color: var(--c-primary);
  margin-bottom: 0.35rem;
  letter-spacing: -0.01em;
}}
.dss-card-desc {{
  font-size: 0.86rem; color: var(--c-muted);
  line-height: 1.55;
}}

/* Card grande (home y rol) */
.dss-card-feature {{
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  padding: 1.6rem 1.7rem;
  height: 100%;
  transition: border-color 220ms var(--ease), transform 220ms var(--ease);
}}
.dss-card-feature:hover {{
  border-color: var(--c-primary);
  transform: translateY(-1px);
}}
.dss-card-feature h3 {{
  font-size: 1.15rem; font-weight: 600; color: var(--c-primary);
  margin: 0.25rem 0 0.6rem 0; letter-spacing: -0.015em;
}}
.dss-card-feature p {{
  font-size: 0.9rem; color: var(--c-muted);
  line-height: 1.6; margin-bottom: 1.2rem;
}}

/* KPI cards */
.dss-kpi {{
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  padding: 0.95rem 1.05rem;
  transition: border-color 200ms var(--ease);
}}
.dss-kpi:hover {{ border-color: var(--c-border-strong); }}
.dss-kpi-label {{
  font-size: 0.7rem; color: var(--c-muted);
  text-transform: uppercase; letter-spacing: 0.08em; font-weight: 500;
}}
.dss-kpi-value {{
  font-size: 1.55rem; font-weight: 600; color: var(--c-primary);
  margin-top: 0.3rem;
  letter-spacing: -0.025em;
  font-variant-numeric: tabular-nums;
}}
.dss-kpi-delta {{
  font-size: 0.78rem; margin-top: 0.2rem;
  font-variant-numeric: tabular-nums;
}}
.dss-kpi-delta.up   {{ color: var(--c-success); }}
.dss-kpi-delta.down {{ color: var(--c-danger); }}
.dss-kpi-delta.flat {{ color: var(--c-muted); }}

/* Badges de estado */
.dss-badge {{
  display: inline-block;
  padding: 0.2rem 0.65rem;
  border-radius: 999px;
  font-size: 0.74rem; font-weight: 500;
  border: 1px solid transparent;
  letter-spacing: -0.005em;
}}

/* Tablas */
.dss-table {{
  width: 100%; border-collapse: collapse; font-size: 0.88rem;
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}}
.dss-table th {{
  text-align: left; font-weight: 500; color: var(--c-muted);
  padding: 0.7rem 0.9rem; border-bottom: 1px solid var(--c-border);
  text-transform: uppercase; letter-spacing: 0.07em; font-size: 0.7rem;
  background: #FBFBFC;
}}
.dss-table td {{
  padding: 0.65rem 0.9rem; border-bottom: 1px solid var(--c-border);
  color: var(--c-text);
  font-variant-numeric: tabular-nums;
}}
.dss-table tr:last-child td {{ border-bottom: none; }}

/* Botones */
.stButton > button, .stDownloadButton > button {{
  border-radius: var(--radius-sm) !important;
  font-weight: 500 !important;
  padding: 0.5rem 1rem !important;
  letter-spacing: -0.005em !important;
  font-size: 0.88rem !important;
  transition: background 180ms var(--ease), border-color 180ms var(--ease),
              color 180ms var(--ease), transform 120ms var(--ease) !important;
  border: 1px solid var(--c-border-strong) !important;
  background: var(--c-card) !important;
  color: var(--c-primary) !important;
  box-shadow: none !important;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  border-color: var(--c-primary) !important;
  background: #FAFBFC !important;
}}
.stButton > button:active, .stDownloadButton > button:active {{
  transform: translateY(0.5px);
}}
.stButton > button[kind="primary"] {{
  background: var(--c-primary) !important;
  border-color: var(--c-primary) !important;
  color: #FCFCFD !important;
}}
.stButton > button[kind="primary"]:hover {{
  background: #1D2939 !important;
  border-color: #1D2939 !important;
}}
.stButton > button:disabled {{
  opacity: 0.45 !important;
  cursor: not-allowed !important;
}}

/* Inputs y selects */
.stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"],
.stMultiSelect div[data-baseweb="select"] {{
  border-radius: var(--radius-sm) !important;
  border-color: var(--c-border-strong) !important;
}}

/* Tabs - underline animado */
[data-baseweb="tab-list"] {{
  background: transparent !important;
  border-bottom: 1px solid var(--c-border) !important;
  gap: 1.5rem !important;
  padding-bottom: 0 !important;
}}
[data-baseweb="tab"] {{
  padding: 0.7rem 0 !important;
  background: transparent !important;
  border-radius: 0 !important;
  font-size: 0.88rem !important;
  font-weight: 500 !important;
  color: var(--c-muted) !important;
  letter-spacing: -0.005em !important;
  transition: color 180ms var(--ease) !important;
}}
[data-baseweb="tab"]:hover {{
  color: var(--c-primary) !important;
  background: transparent !important;
}}
[data-baseweb="tab"][aria-selected="true"] {{
  color: var(--c-primary) !important;
  font-weight: 600 !important;
}}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{
  background: var(--c-primary) !important;
  height: 2px !important;
  transition: all 280ms var(--ease) !important;
}}

[role="tabpanel"] {{
  animation: dss-tab-in 260ms var(--ease);
  padding-top: 1.2rem !important;
}}

@keyframes dss-tab-in {{
  from {{ opacity: 0; transform: translateY(3px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

/* Divider sutil */
.dss-divider {{
  height: 1px; background: var(--c-border);
  margin: 1.4rem 0;
}}

/* Empty state */
.dss-empty {{
  border: 1px dashed var(--c-border-strong);
  border-radius: var(--radius-lg);
  padding: 2.4rem 2rem;
  text-align: center;
  background: var(--c-card);
}}
.dss-empty-title {{
  font-size: 0.95rem; font-weight: 600; color: var(--c-primary);
  margin-bottom: 0.35rem; letter-spacing: -0.01em;
}}
.dss-empty-desc {{
  font-size: 0.85rem; color: var(--c-muted);
  max-width: 460px; margin: 0 auto; line-height: 1.55;
}}

/* Footer */
.dss-footer {{
  border-top: 1px solid var(--c-border);
  margin-top: 2.4rem; padding-top: 1rem;
  font-size: 0.73rem; color: var(--c-subtle);
  text-align: center;
  letter-spacing: 0.03em;
}}

/* Sidebar (oculto pero estilizado) */
section[data-testid="stSidebar"] {{
  background: var(--c-card);
  border-right: 1px solid var(--c-border);
}}

/* Alertas Streamlit refinadas */
.stAlert {{
  border-radius: var(--radius-md) !important;
  border: 1px solid var(--c-border) !important;
  background: var(--c-card) !important;
  padding: 0.85rem 1rem !important;
}}
.stAlert p {{ font-size: 0.87rem !important; }}

/* Ocultar elementos por defecto */
#MainMenu, footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}

/* Selectbox / tabs / metricas - tipografia coherente */
[data-testid="stMetric"] {{
  background: var(--c-card);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  padding: 0.95rem 1.05rem;
}}
[data-testid="stMetricValue"] {{
  font-size: 1.4rem !important;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}}
[data-testid="stMetricLabel"] {{
  font-size: 0.72rem !important;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--c-muted) !important;
}}

/* Dataframes refinados */
[data-testid="stDataFrame"] {{
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}}

/* Spinners */
.stSpinner > div {{
  border-top-color: var(--c-primary) !important;
}}

/* Captions y subtle */
.stCaption, [data-testid="stCaptionContainer"] {{
  font-size: 0.78rem !important;
  color: var(--c-muted) !important;
}}

/* Markdown links */
a {{
  color: var(--c-accent);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color 180ms var(--ease);
}}
a:hover {{ border-bottom-color: var(--c-accent); }}

/* Tooltip / popover */
[data-baseweb="popover"] {{
  border-radius: var(--radius-md) !important;
}}
</style>
"""


def apply_page_config():
    st.set_page_config(
        page_title=f"{APP_NAME} - DSS",
        layout="wide",
        initial_sidebar_state="collapsed",
    )


def apply_global_styles():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def render_app_header():
    modo = st.session_state.get("modo")
    rol = st.session_state.get("rol")
    if modo == "validacion":
        chip_text = "Modo <strong>Validacion</strong>"
    elif modo == "demostracion":
        if rol == "supervisor":
            chip_text = "Modo <strong>Demostracion</strong>  &middot;  Rol <strong>Supervisor</strong>"
        elif rol == "conductor":
            chip_text = "Modo <strong>Demostracion</strong>  &middot;  Rol <strong>Conductor</strong>"
        else:
            chip_text = "Modo <strong>Demostracion</strong>"
    else:
        chip_text = "Pantalla inicial"

    html = (
        '<div class="dss-header">'
        '<div class="dss-brand">'
        f'{BRAND_MARK_SVG}'
        '<div class="dss-brand-text">'
        f'<span class="dss-brand-name">{APP_NAME}</span>'
        f'<span class="dss-brand-sub">{APP_SUBTITLE}</span>'
        '</div>'
        '</div>'
        f'<div class="dss-context-chip">{chip_text}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_view_title(title: str, description: str = "", eyebrow: str = ""):
    if eyebrow:
        st.markdown(f'<div class="dss-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="dss-view-title">{title}</div>', unsafe_allow_html=True)
    if description:
        st.markdown(f'<div class="dss-view-desc">{description}</div>', unsafe_allow_html=True)


def render_divider():
    st.markdown('<div class="dss-divider"></div>', unsafe_allow_html=True)


def render_empty_state(title: str, description: str = ""):
    html = (
        '<div class="dss-empty">'
        f'<div class="dss-empty-title">{title}</div>'
        f'<div class="dss-empty-desc">{description}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_footer():
    html = (
        '<div class="dss-footer">'
        f'{APP_NAME}  &middot;  {APP_TAGLINE}  &middot;  v{APP_VERSION}'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
