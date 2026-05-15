"""Configuracion global del proyecto DSS Logistico."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATASETS_DIR = DATA_DIR / "datasets"
OUTPUTS_DIR = DATA_DIR / "outputs"
DEMO_DATASET_DIR = DATASETS_DIR / "dataset_demo_callao_80pedidos"

for d in (DATA_DIR, DATASETS_DIR, OUTPUTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

APP_NAME = "Ultima Milla"
APP_SUBTITLE = "Decision Support System"
APP_TAGLINE = "Distribucion de colchones desde Callao"
APP_VERSION = "0.2.0"

# Paleta premium SaaS - mono + un solo acento
COLOR_PRIMARY = "#0C111D"      # ink, casi negro
COLOR_SECONDARY = "#1D2939"     # dark slate
COLOR_ACCENT = "#1570EF"        # acento azul refinado
COLOR_SUCCESS = "#027A48"
COLOR_WARNING = "#B54708"
COLOR_DANGER = "#B42318"
COLOR_NEUTRAL = "#667085"
COLOR_BG = "#FCFCFD"
COLOR_CARD = "#FFFFFF"
COLOR_BORDER = "#EAECF0"
COLOR_BORDER_STRONG = "#D0D5DD"
COLOR_TEXT = "#101828"
COLOR_MUTED = "#475467"
COLOR_SUBTLE = "#98A2B3"

ALMACEN = {
    "nombre": "Almacen Callao",
    "distrito": "Callao",
    "latitud": -12.0500,
    "longitud": -77.1200,
}

JORNADA_INICIO = "09:00"
JORNADA_FIN = "19:00"
NUM_VEHICULOS = 10
NUM_PEDIDOS = 80
RANDOM_SEED = 42
