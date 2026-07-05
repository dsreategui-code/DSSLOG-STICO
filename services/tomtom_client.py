"""Cliente de TRAFICO (TomTom Traffic Flow) para el factor de congestion del contexto.

MODO FACTORES (no matriz): a TomTom se le pide, en unos POCOS puntos representativos por
macrozona, el ratio de congestion `currentTravelTime / freeFlowTravelTime` (cuanto mas lento
esta el transito vs. flujo libre). Ese factor escala el F_trafico de la matriz contextual. El
consumo es O(puntos x macrozonas x franjas), INDEPENDIENTE del nº de pedidos, y se PRE-DESCARGA
UNA vez a una tabla (`trafico_real.csv`); el motor lee la tabla, no llama en vivo.

Requiere API key gratis (free tier, sin tarjeta): env TOMTOM_API_KEY o st.secrets. SIN key ->
respaldo (factor 1.0, no llama la API, no rompe). Patron OSRM: cache + respaldo degradado.
OSRM da el tiempo BASE; TomTom solo aporta la congestion.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from config.cortex_settings import CACHE_DIR, resolver_tomtom_key

BASE_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
TIMEOUT_S = 8
TOMTOM_CACHE_DIR = CACHE_DIR / "tomtom"
TOMTOM_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def factor_desde_flujo(current_tt: float, freeflow_tt: float) -> float:
    """Factor de congestion (>=1.0) desde los tiempos de TomTom: current / freeFlow. El trafico
    solo puede ENLENTECER (>=1); acotado a 3.0 como los demas factores."""
    if not freeflow_tt or float(freeflow_tt) <= 0:
        return 1.0
    return round(min(3.0, max(1.0, float(current_tt) / float(freeflow_tt))), 3)


class TomTomClient:
    """Factor de congestion por punto (TomTom Flow) con key + cache + respaldo (1.0)."""

    def __init__(self, base_url: str = BASE_URL, cache_dir: Optional[Path] = None,
                 api_key: Optional[str] = None, timeout_s: int = TIMEOUT_S, pausa_s: float = 0.2):
        self.base_url = base_url
        self.cache_dir = Path(cache_dir or TOMTOM_CACHE_DIR)
        self.api_key = api_key if api_key is not None else resolver_tomtom_key()
        self.timeout_s = int(timeout_s)
        self.pausa_s = float(pausa_s)

    def factor_trafico(self, lat: float, lon: float, usar_cache: bool = True) -> float:
        """Factor de congestion en el punto. SIN key -> 1.0 (respaldo). cache-first; si la API
        falla -> 1.0 (no rompe)."""
        if not self.api_key:
            return 1.0
        clave = f"{round(float(lat), 4)}_{round(float(lon), 4)}"
        cp = self.cache_dir / f"{clave}.json"
        if usar_cache and cp.exists():
            try:
                return float(json.loads(cp.read_text(encoding="utf-8"))["factor"])
            except Exception:  # noqa: BLE001
                pass
        try:
            q = urllib.parse.urlencode({"point": f"{lat},{lon}", "key": self.api_key})
            with urllib.request.urlopen(f"{self.base_url}?{q}", timeout=self.timeout_s) as r:
                d = json.load(r)
            time.sleep(self.pausa_s)
            fsd = d.get("flowSegmentData", {})
            factor = factor_desde_flujo(fsd.get("currentTravelTime", 0),
                                        fsd.get("freeFlowTravelTime", 0))
            if usar_cache:
                try:
                    cp.write_text(json.dumps({"factor": factor}), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            return factor
        except Exception:  # noqa: BLE001  (sin internet / key invalida / cuota)
            return 1.0


def factores_por_macrozona(puntos_por_macrozona: Dict[str, List[tuple]],
                           client: Optional[TomTomClient] = None) -> Dict[str, float]:
    """PRE-DESCARGA: promedio del factor de congestion en los puntos representativos de cada
    macrozona (en el momento actual = franja actual). {macrozona: factor}."""
    client = client or TomTomClient()
    out = {}
    for mz, pts in puntos_por_macrozona.items():
        fs = [client.factor_trafico(lat, lon) for lat, lon in pts]
        if fs:
            out[mz] = round(sum(fs) / len(fs), 3)
    return out
