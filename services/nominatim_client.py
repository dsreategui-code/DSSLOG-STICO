"""Cliente de GEOCODIFICACION (Nominatim / OpenStreetMap): direccion -> coordenada + distrito.

Es la PUERTA DE ENTRADA para datos REALES: cuando los pedidos llegan como DIRECCIONES de texto,
este cliente las convierte en (lat, lon) + distrito, y luego OSRM las pega a la calle. Con datos
sinteticos (que ya traen coordenadas) no se usa; queda listo para el dataset real.

Gratis, SIN key. Politica del servidor publico: max 1 req/seg y User-Agent obligatorio. Cache +
respaldo (si falla o no encuentra -> None, no rompe). Para volumen se auto-hospeda como OSRM.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

from config.cortex_settings import CACHE_DIR

BASE_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "CORTEX-LM-DSS/1.0 (tesis logistica ultima milla Lima)"
TIMEOUT_S = 12
NOMINATIM_CACHE_DIR = CACHE_DIR / "nominatim"
NOMINATIM_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# En Lima el distrito puede venir en distintos campos de OSM segun el punto.
_CAMPOS_DISTRITO = ("city_district", "suburb", "municipality", "quarter", "neighbourhood",
                    "county", "town", "city")


class NominatimClient:
    """Geocodificacion directa (direccion -> coord + distrito) con cache + respaldo."""

    def __init__(self, base_url: str = BASE_URL, cache_dir: Optional[Path] = None,
                 user_agent: str = USER_AGENT, timeout_s: int = TIMEOUT_S, pausa_s: float = 1.0):
        self.base_url = base_url
        self.cache_dir = Path(cache_dir or NOMINATIM_CACHE_DIR)
        self.user_agent = user_agent
        self.timeout_s = int(timeout_s)
        self.pausa_s = float(pausa_s)          # respeta la politica de 1 req/seg

    @staticmethod
    def _distrito(address: dict) -> str:
        for k in _CAMPOS_DISTRITO:
            if address.get(k):
                return str(address[k])
        return ""

    def geocodificar(self, direccion: str, pais: str = "pe",
                     usar_cache: bool = True) -> Optional[dict]:
        """Devuelve {'lat','lon','distrito','direccion_norm'} o None. cache-first; sin red o sin
        resultado -> None (respaldo: el caller usa el centroide del distrito o marca revision)."""
        clave = hashlib.md5(f"{pais}|{direccion}".lower().encode("utf-8")).hexdigest()
        cp = self.cache_dir / f"{clave}.json"
        if usar_cache and cp.exists():
            try:
                return json.loads(cp.read_text(encoding="utf-8")) or None
            except Exception:  # noqa: BLE001
                pass
        try:
            q = urllib.parse.urlencode({"q": direccion, "format": "json", "countrycodes": pais,
                                        "addressdetails": "1", "limit": "1"})
            req = urllib.request.Request(f"{self.base_url}/search?{q}",
                                         headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                data = json.load(r)
            time.sleep(self.pausa_s)            # cortesia con el servidor publico
            res = None
            if data:
                a = data[0]
                res = {"lat": float(a["lat"]), "lon": float(a["lon"]),
                       "distrito": self._distrito(a.get("address", {})),
                       "direccion_norm": a.get("display_name", "")}
            if usar_cache:
                try:
                    cp.write_text(json.dumps(res or {}), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            return res
        except Exception:  # noqa: BLE001  (sin internet / API caida)
            return None


def geocodificar_direcciones(direcciones: List[str], client: Optional[NominatimClient] = None,
                             pais: str = "pe") -> List[dict]:
    """Geocodifica una lista de direcciones (la puerta de entrada del dataset REAL). Devuelve
    [{'direccion','lat','lon','distrito','ok'}]; los fallos quedan ok=False (para revision o
    fallback al centroide del distrito)."""
    client = client or NominatimClient()
    out = []
    for d in direcciones:
        r = client.geocodificar(d, pais=pais)
        out.append({"direccion": d, "lat": (r or {}).get("lat"), "lon": (r or {}).get("lon"),
                    "distrito": (r or {}).get("distrito", ""), "ok": r is not None})
    return out
