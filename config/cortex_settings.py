"""Configuracion de infraestructura del motor CORTEX-LM.

Separado de `config/settings.py` (que ya opera) para no alterar lo existente. Aqui van
rutas de cache y el endpoint de OSRM local. Los parametros OPERATIVOS (iteraciones Monte
Carlo, umbrales, pesos de perfil, etc.) NO se hardcodean aqui: provienen de
`parametros.xlsx` / `perfiles_decision.xlsx` (ver core.data_models).
"""
from pathlib import Path

from config.settings import DATA_DIR, PROJECT_ROOT

# --- Cache de artefactos pesados (matrices OSRM, geometrias, resultados) ---
CACHE_DIR = DATA_DIR / "cache"
OSRM_CACHE_DIR = CACHE_DIR / "osrm"
CLIMA_CACHE_DIR = CACHE_DIR / "clima"       # factor climatico (Open-Meteo) por fecha/ubicacion
for _d in (CACHE_DIR, OSRM_CACHE_DIR, CLIMA_CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- OSRM local (UNICA API geoespacial permitida) ---
# Endpoint del servidor OSRM ejecutado localmente (p. ej. via Docker:
#   docker run -p 5000:5000 osrm/osrm-backend osrm-routed --algorithm mld /data/peru.osrm)
# Se puede sobrescribir con la variable de entorno OSRM_BASE_URL.
import os

# NOTA: no se debe tocar st.secrets al IMPORTAR este modulo (correria antes de
# st.set_page_config y Streamlit falla). Al importar solo se usa la variable de entorno; el
# secret de Streamlit Cloud se resuelve en tiempo de EJECUCION via resolver_osrm_url().
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "http://localhost:5000")


def resolver_osrm_url() -> str:
    """URL de OSRM en tiempo de ejecucion (llamar al crear el cliente, no al importar).
    Prioridad: env OSRM_BASE_URL -> st.secrets['OSRM_BASE_URL'] (Streamlit Cloud) -> default.

    Solo consulta st.secrets si EXISTE un secrets.toml, para no emitir el aviso
    'No secrets files found' cuando se corre local sin secrets (p. ej. con OSRM en localhost)."""
    v = os.environ.get("OSRM_BASE_URL")
    if v:
        return v
    from pathlib import Path
    rutas = [Path.home() / ".streamlit" / "secrets.toml",
             Path.cwd() / ".streamlit" / "secrets.toml"]
    if any(p.exists() for p in rutas):
        try:
            import streamlit as st
            if "OSRM_BASE_URL" in st.secrets:
                return str(st.secrets["OSRM_BASE_URL"])
        except Exception:  # noqa: BLE001
            pass
    return OSRM_BASE_URL
OSRM_PROFILE = os.environ.get("OSRM_PROFILE", "driving")


def resolver_tomtom_key() -> str:
    """API key de TomTom (trafico) en tiempo de ejecucion. Prioridad: env TOMTOM_API_KEY ->
    st.secrets['TOMTOM_API_KEY'] (Streamlit Cloud) -> '' (sin key -> respaldo, no llama la API).
    Solo consulta st.secrets si existe un secrets.toml (evita el aviso local sin secrets)."""
    v = os.environ.get("TOMTOM_API_KEY")
    if v:
        return v
    from pathlib import Path
    rutas = [Path.home() / ".streamlit" / "secrets.toml",
             Path.cwd() / ".streamlit" / "secrets.toml"]
    if any(p.exists() for p in rutas):
        try:
            import streamlit as st
            if "TOMTOM_API_KEY" in st.secrets:
                return str(st.secrets["TOMTOM_API_KEY"])
        except Exception:  # noqa: BLE001
            pass
    return ""
OSRM_TIMEOUT_S = 30
# Velocidad de respaldo (km/h) SOLO para construir una matriz aproximada cuando no hay
# OSRM ni cache y el usuario lo autoriza explicitamente (modo degradado, documentado).
VELOCIDAD_RESPALDO_KMH = 18.0
# Factor de circuito (rodeo): la distancia real por calle es mayor que la linea recta
# (haversine). ~1.4 es tipico en malla urbana. Aproxima OSRM cuando no esta disponible;
# con OSRM real este factor no se usa (la geometria de calle ya es exacta).
FACTOR_CIRCUITO = float(os.environ.get("FACTOR_CIRCUITO", "1.4"))

# --- Plantillas de entrada nuevas del motor (ver data/plantillas) ---
PLANTILLAS_DIR = DATA_DIR / "plantillas"
PLANTILLAS_DIR.mkdir(parents=True, exist_ok=True)
