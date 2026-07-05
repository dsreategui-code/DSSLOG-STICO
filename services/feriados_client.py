"""Cliente de FERIADOS (Nager.Date) para el calendario de eventos del contexto.

Un feriado nacional cambia el patron de reparto en Lima: menos trafico de commuters en las vias
principales (viaje algo mas rapido), pero muchos clientes comerciales cerrados. Se modela como un
EventoCalendario de tipo 'feriado' con factor de trafico < 1.0 (dia no laborable) y menor demanda.
Solo aplica al planificar PARA esa fecha (ver contextual_matrix).

API gratuita, SIN key (date.nager.at). Patron OSRM: cache + respaldo degradado (sin internet o si
la API falla -> lista vacia, NUNCA rompe). Conviene pre-descargar el ano y cachearlo.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import List, Optional

from config.cortex_settings import CACHE_DIR
from core.data_models import EventoCalendario

BASE_URL = "https://date.nager.at/api/v3/PublicHolidays"
TIMEOUT_S = 6
FERIADOS_CACHE_DIR = CACHE_DIR / "feriados"
FERIADOS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class FeriadosClient:
    """Feriados oficiales por pais/ano (Nager.Date) con cache + respaldo."""

    def __init__(self, base_url: str = BASE_URL, cache_dir: Optional[Path] = None,
                 timeout_s: int = TIMEOUT_S):
        self.base_url = base_url
        self.cache_dir = Path(cache_dir or FERIADOS_CACHE_DIR)
        self.timeout_s = int(timeout_s)

    def feriados(self, anio: int, pais: str = "PE", usar_cache: bool = True) -> List[dict]:
        """[{'fecha': 'YYYY-MM-DD', 'nombre': ...}] deduplicado por fecha. cache-first; si no hay
        internet o la API falla -> [] (respaldo, no rompe)."""
        cp = self.cache_dir / f"{pais}_{int(anio)}.json"
        if usar_cache and cp.exists():
            try:
                return json.loads(cp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        try:
            url = f"{self.base_url}/{int(anio)}/{pais}"
            with urllib.request.urlopen(url, timeout=self.timeout_s) as r:
                data = json.load(r)
            vistos, out = set(), []
            for h in data:
                f = h.get("date")
                if f and f not in vistos:
                    vistos.add(f)
                    out.append({"fecha": f, "nombre": h.get("localName") or h.get("name") or "Feriado"})
            if usar_cache:
                try:
                    cp.write_text(json.dumps(out), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            return out
        except Exception:  # noqa: BLE001  (sin internet / API caida)
            return []


def eventos_desde_feriados(feriados: List[dict], factor_trafico: float = 0.9,
                           factor_demanda: float = 0.7) -> List[EventoCalendario]:
    """Convierte feriados en EventoCalendario ('feriado', global): dia no laborable -> menos
    trafico de commuters (factor < 1) y menor demanda comercial."""
    return [EventoCalendario(fecha=f["fecha"], tipo_evento="feriado",
                             descripcion=str(f.get("nombre", "Feriado")),
                             factor_trafico=float(factor_trafico),
                             factor_demanda=float(factor_demanda),
                             zonas_afectadas="todas")
            for f in (feriados or [])]
