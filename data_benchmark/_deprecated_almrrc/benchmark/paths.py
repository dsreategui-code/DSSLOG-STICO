"""Localizacion automatica de los archivos del benchmark ALM RRC.

No asume rutas fijas: busca la carpeta `data_benchmark/` a partir de la raiz del
proyecto y, si no esta ahi, hacia arriba en el arbol de directorios. El cache vive
en `data_benchmark/cache/` y nunca toca los archivos fuente.
"""
from pathlib import Path
from typing import Optional

from config.settings import PROJECT_ROOT


# Nombres canonicos de los archivos transformados (procesados a CSV).
ARCHIVOS_PROCESADOS = {
    "routes": "01_routes.csv",
    "stops": "02_stops.csv",
    "actual_sequences": "03_actual_sequences.csv",
    "packages": "04_packages.csv",
    "travel_times": "05_travel_times_long.csv",
    "dss_pedidos_base": "06_dss_pedidos_base.csv",
    "route_summary": "07_route_summary.csv",
}

_CANDIDATOS_RAIZ = ("data_benchmark", "benchmark_data", "almrrc", "alm_rrc")


def benchmark_root() -> Optional[Path]:
    """Devuelve la carpeta `data_benchmark/` o None si no se encuentra."""
    # 1) Junto a la raiz del proyecto (caso normal).
    for nombre in _CANDIDATOS_RAIZ:
        cand = PROJECT_ROOT / nombre
        if cand.exists() and (cand / "processed_csv").exists():
            return cand
        if cand.exists() and any(cand.glob("**/01_routes.csv")):
            return cand
    # 2) Busqueda hacia arriba (por si el proyecto esta anidado).
    actual = PROJECT_ROOT
    for _ in range(3):
        actual = actual.parent
        for nombre in _CANDIDATOS_RAIZ:
            cand = actual / nombre
            if cand.exists() and (cand / "processed_csv").exists():
                return cand
    return None


def processed_dir() -> Optional[Path]:
    root = benchmark_root()
    if root is None:
        return None
    p = root / "processed_csv"
    return p if p.exists() else root


def processed_csv(clave: str) -> Optional[Path]:
    """Ruta absoluta a un archivo procesado por su clave logica.

    Tolera que el archivo este directamente en `processed_csv/` o anidado.
    """
    pdir = processed_dir()
    if pdir is None:
        return None
    nombre = ARCHIVOS_PROCESADOS.get(clave, clave)
    directo = pdir / nombre
    if directo.exists():
        return directo
    # Busqueda tolerante.
    encontrados = list(pdir.glob(f"**/{nombre}"))
    return encontrados[0] if encontrados else None


def cache_dir() -> Path:
    """Carpeta de cache del benchmark (se crea si no existe)."""
    root = benchmark_root()
    base = (root if root is not None else (PROJECT_ROOT / "data_benchmark"))
    c = base / "cache"
    c.mkdir(parents=True, exist_ok=True)
    (c / "rutas").mkdir(parents=True, exist_ok=True)
    return c


def cache_index_file() -> Path:
    return cache_dir() / "sample_index.csv"


def cache_ruta_dir(route_id: str) -> Path:
    # route_id es un UUID prefijado; lo usamos tal cual como nombre de carpeta.
    d = cache_dir() / "rutas" / _safe_name(route_id)
    return d


def _safe_name(route_id: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(route_id))


def is_prepared() -> bool:
    """True si existe un cache de muestra utilizable."""
    idx = cache_index_file()
    return idx.exists() and idx.stat().st_size > 0


def benchmark_disponible() -> bool:
    """True si el dataset transformado esta presente (haya o no cache)."""
    return processed_csv("dss_pedidos_base") is not None and \
        processed_csv("travel_times") is not None
