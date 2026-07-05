"""Cliente de CLIMA (Open-Meteo) para el factor climatico del contexto de Lima.

Lima casi no llueve, pero la GARUA/NEBLINA de invierno (mayo-noviembre) reduce la visibilidad y
enlentece el transito. El factor climatico combina PRECIPITACION + VISIBILIDAD, de modo que un
dia de neblina cerrada pone mas lento el reparto (como un factor sistemico del dia). En Lima la
visibilidad (neblina) es el driver, no la lluvia.

API gratuita, SIN key (open-meteo.com). Sigue el patron de OSRM: cache-first + respaldo
degradado (sin internet o si la API falla -> factor 1.0, NUNCA rompe). En la nube conviene
PRE-DESCARGAR el factor del dia (queda cacheado); el motor lo lee.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from config.cortex_settings import CLIMA_CACHE_DIR

BASE_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 6
FACTOR_MAX = 1.4          # tope del factor climatico (acotado como los demas factores)


def factor_desde_clima(precip_mm_max: float, visibilidad_min_m: float) -> float:
    """Factor climatico (>=1.0) desde la precipitacion MAXIMA (mm) y la visibilidad MINIMA (m)
    de la jornada. En Lima la NEBLINA (visibilidad baja) pesa mas que la lluvia (rara)."""
    f = 1.0
    f += min(0.30, 0.05 * max(0.0, float(precip_mm_max)))        # lluvia (poco frecuente en Lima)
    v = float(visibilidad_min_m)
    if v < 1000:      f += 0.25                                   # neblina muy cerrada
    elif v < 2000:    f += 0.15
    elif v < 5000:    f += 0.08                                   # garua / neblina
    elif v < 10000:   f += 0.03
    return round(min(FACTOR_MAX, f), 3)


def _min_dia(hhmm: str) -> int:
    hh, mm = hhmm.split(":")[:2]
    return int(hh) * 60 + int(mm)


class ClimaClient:
    """Cliente Open-Meteo con cache + respaldo. `factor_clima(...)` devuelve un dict trazable."""

    def __init__(self, base_url: str = BASE_URL, cache_dir: Optional[Path] = None,
                 timeout_s: int = TIMEOUT_S):
        self.base_url = base_url
        self.cache_dir = Path(cache_dir or CLIMA_CACHE_DIR)
        self.timeout_s = int(timeout_s)

    def factor_clima(self, fecha: Optional[str], lat: float, lon: float,
                     hora_ini: str = "09:00", hora_fin: str = "19:00",
                     usar_cache: bool = True) -> dict:
        """Devuelve {'factor', 'precip_mm', 'visibilidad_min_m', 'fuente'}. cache-first; si no hay
        internet o la API falla -> factor 1.0 (respaldo neutro, no rompe la planificacion)."""
        clave = f"{fecha or 'hoy'}_{round(float(lat), 2)}_{round(float(lon), 2)}_{hora_ini}_{hora_fin}"
        cp = self.cache_dir / f"{clave}.json"
        if usar_cache and cp.exists():
            try:
                return json.loads(cp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        try:
            res = self._consultar(fecha, lat, lon, hora_ini, hora_fin)
            if usar_cache:
                try:
                    cp.write_text(json.dumps(res), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            return res
        except Exception:  # noqa: BLE001  (sin internet / API caida / fecha fuera de rango)
            return {"factor": 1.0, "precip_mm": None, "visibilidad_min_m": None, "fuente": "respaldo"}

    def _consultar(self, fecha, lat, lon, hora_ini, hora_fin) -> dict:
        params = {"latitude": float(lat), "longitude": float(lon),
                  "hourly": "precipitation,visibility", "timezone": "America/Lima"}
        if fecha:
            params["start_date"] = str(fecha)
            params["end_date"] = str(fecha)
        else:
            params["forecast_days"] = 1
        url = self.base_url + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=self.timeout_s) as r:
            d = json.load(r)
        h = d["hourly"]
        h0, h1 = _min_dia(hora_ini), _min_dia(hora_fin)
        pmax, vmin = 0.0, float("inf")
        for t, p, v in zip(h["time"], h["precipitation"], h["visibility"]):
            hhmm = t.split("T")[1][:5] if "T" in t else None
            if hhmm is None or not (h0 <= _min_dia(hhmm) <= h1):
                continue
            if p is not None:
                pmax = max(pmax, float(p))
            if v is not None:
                vmin = min(vmin, float(v))
        if vmin == float("inf"):
            vmin = 20000.0                                        # sin dato -> visibilidad clara
        return {"factor": factor_desde_clima(pmax, vmin), "precip_mm": round(pmax, 2),
                "visibilidad_min_m": round(vmin, 0), "fuente": "open-meteo"}
