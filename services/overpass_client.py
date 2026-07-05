"""Cliente de POIs (Overpass / OpenStreetMap): densidad de puntos de interes COMERCIALES para
derivar el FACTOR DE ZONA (acceso / estacionamiento). Mas comercios = zona mas densa = acceso y
estacionamiento mas dificiles (mayor factor).

Gratis, rate-limited (timeouts en areas grandes). Patron: se PRE-DESCARGA por distrito a una tabla
(`data/plantillas/pois_zona.csv`) UNA vez; el motor LEE la tabla, no llama en vivo. Cache +
respaldo (si falla -> None). Para volumen/velocidad se auto-hospeda como OSRM.
"""
from __future__ import annotations

import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from config.cortex_settings import CACHE_DIR

BASE_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "CORTEX-LM-DSS/1.0 (tesis logistica Lima)"
TIMEOUT_S = 30
OVERPASS_CACHE_DIR = CACHE_DIR / "overpass"
OVERPASS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class OverpassClient:
    """Cuenta POIs comerciales (shop + marketplace) alrededor de un punto, con cache + respaldo."""

    def __init__(self, base_url: str = BASE_URL, cache_dir: Optional[Path] = None,
                 timeout_s: int = TIMEOUT_S, pausa_s: float = 1.0):
        self.base_url = base_url
        self.cache_dir = Path(cache_dir or OVERPASS_CACHE_DIR)
        self.timeout_s = int(timeout_s)
        self.pausa_s = float(pausa_s)

    def densidad_pois(self, lat: float, lon: float, radio: int = 500,
                      usar_cache: bool = True) -> Optional[int]:
        """Nº de POIs comerciales dentro de `radio` m del punto. cache-first; sin red -> None."""
        clave = f"{round(float(lat), 4)}_{round(float(lon), 4)}_{int(radio)}"
        cp = self.cache_dir / f"{clave}.json"
        if usar_cache and cp.exists():
            try:
                return int(json.loads(cp.read_text(encoding="utf-8"))["total"])
            except Exception:  # noqa: BLE001
                pass
        try:
            data = (f"[out:json][timeout:{self.timeout_s}];"
                    f"(node[shop](around:{radio},{lat},{lon});"
                    f"node[amenity=marketplace](around:{radio},{lat},{lon}););out count;")
            req = urllib.request.Request(self.base_url, data=data.encode("utf-8"),
                                         headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout_s + 5) as r:
                o = json.load(r)
            time.sleep(self.pausa_s)            # cortesia con el servidor publico
            total = int(o.get("elements", [{}])[0].get("tags", {}).get("total", 0))
            if usar_cache:
                try:
                    cp.write_text(json.dumps({"total": total}), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            return total
        except Exception:  # noqa: BLE001  (sin internet / rate-limit / timeout)
            return None


def factores_zona_desde_densidad(densidades: Dict[str, float], acc_min: float = 1.0,
                                 acc_max: float = 1.35, est_min: float = 1.0,
                                 est_max: float = 1.30) -> Dict[str, dict]:
    """{distrito: densidad_pois} -> {distrito: {'acceso', 'estacionamiento'}} normalizado. Mas
    POIs = acceso y estacionamiento mas dificiles (relativo entre distritos)."""
    vals = [float(v) for v in densidades.values()]
    if not vals:
        return {}
    lo, hi = min(vals), max(vals)
    out = {}
    for d, v in densidades.items():
        norm = 0.5 if hi - lo < 1e-9 else (float(v) - lo) / (hi - lo)
        out[d] = {"acceso": round(acc_min + (acc_max - acc_min) * norm, 3),
                  "estacionamiento": round(est_min + (est_max - est_min) * norm, 3)}
    return out


def densidades_por_distrito(pedidos, radio: int = 500,
                            client: Optional[OverpassClient] = None) -> Dict[str, int]:
    """PRE-DESCARGA: centroide de los pedidos por distrito -> densidad de POIs (Overpass).
    Devuelve {distrito: densidad}. Se guarda en pois_zona.csv y el loader lo lee."""
    client = client or OverpassClient()
    pts: Dict[str, List[tuple]] = defaultdict(list)
    for p in pedidos:
        if getattr(p, "distrito", None):
            pts[p.distrito].append((float(p.lat), float(p.lon)))
    out = {}
    for distrito, coords in pts.items():
        lat = sum(c[0] for c in coords) / len(coords)
        lon = sum(c[1] for c in coords) / len(coords)
        dens = client.densidad_pois(lat, lon, radio=radio)
        if dens is not None:
            out[distrito] = dens
    return out
