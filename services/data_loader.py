"""Carga del dataset sintetico desde disco."""
from pathlib import Path
import json
import pandas as pd
from config.settings import DEMO_DATASET_DIR
from utils.constants import DATASET_FILES


def dataset_exists(path: Path = None) -> bool:
    path = Path(path) if path else DEMO_DATASET_DIR
    if not path.exists():
        return False
    return all((path / f).exists() for f in DATASET_FILES)


def load_dataset(path: Path = None) -> dict:
    """Carga todos los archivos del dataset y los devuelve como dict."""
    path = Path(path) if path else DEMO_DATASET_DIR
    if not path.exists():
        raise FileNotFoundError(f"Dataset no encontrado en {path}")

    out = {}
    for f in DATASET_FILES:
        full = path / f
        if not full.exists():
            raise FileNotFoundError(f"Archivo faltante: {f}")
        key = f.replace(".csv", "").replace(".json", "")
        if f.endswith(".csv"):
            df = pd.read_csv(full)
            for c in df.select_dtypes(include="object").columns:
                df[c] = df[c].astype(str).str.strip()
            out[key] = df
        elif f.endswith(".json"):
            with open(full, "r", encoding="utf-8") as fp:
                out[key] = json.load(fp)
    return out


def get_dataset_meta(path: Path = None) -> dict:
    """Metadatos rapidos: ruta, tamano total, cantidad de archivos."""
    path = Path(path) if path else DEMO_DATASET_DIR
    if not path.exists():
        return {"existe": False}
    files = [f for f in path.glob("*") if f.is_file()]
    total_bytes = sum(f.stat().st_size for f in files)
    return {
        "existe": True,
        "ruta": str(path),
        "archivos": len(files),
        "tamano_kb": round(total_bytes / 1024, 1),
    }
