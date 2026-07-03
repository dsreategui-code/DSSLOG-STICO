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
for _d in (CACHE_DIR, OSRM_CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- OSRM local (UNICA API geoespacial permitida) ---
# Endpoint del servidor OSRM ejecutado localmente (p. ej. via Docker:
#   docker run -p 5000:5000 osrm/osrm-backend osrm-routed --algorithm mld /data/peru.osrm)
# Se puede sobrescribir con la variable de entorno OSRM_BASE_URL.
import os

OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "http://localhost:5000")
OSRM_PROFILE = os.environ.get("OSRM_PROFILE", "driving")
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
