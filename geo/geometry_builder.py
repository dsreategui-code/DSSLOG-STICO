"""Construccion de geometrias de ruta para el gemelo digital operativo (PyDeck).

Por defecto usa tramos rectos entre paradas (robusto, sin dependencias externas), lo que
da una interpolacion de posicion limpia por tiempo. Si hay un cliente OSRM disponible, se
puede superponer la geometria REAL de calle (Route Service) para dibujar el trazado; la
interpolacion de la posicion del vehiculo sigue usando los tramos rectos por simplicidad.

Convencion: el dominio usa (lat, lon); GeoJSON/PyDeck usan [lon, lat].
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

Coord = Tuple[float, float]  # (lat, lon)


def _a_lonlat(c: Coord) -> List[float]:
    return [float(c[1]), float(c[0])]


def geometria_recta(stops_latlon: Sequence[Coord]) -> dict:
    """Tramos rectos entre paradas consecutivas. Devuelve path (para dibujar) y tramos
    (para interpolar la posicion)."""
    path = [_a_lonlat(c) for c in stops_latlon]
    tramos = [(stops_latlon[i], stops_latlon[i + 1]) for i in range(len(stops_latlon) - 1)]
    return {"path_lonlat": path, "tramos_latlon": tramos, "origen": "recta"}


def geometria_de_ruta(stops_latlon: Sequence[Coord], osrm=None,
                      usar_osrm: bool = False) -> dict:
    """Geometria de una ruta que pasa por `stops_latlon` (incluye HUB al inicio).

    Los tramos para interpolacion son siempre rectos; el `path_lonlat` para dibujar usa la
    geometria real de OSRM si esta disponible y se solicita, con respaldo a la poligonal
    recta. NUNCA usa servicios externos distintos de OSRM.
    """
    base = geometria_recta(stops_latlon)
    if usar_osrm and osrm is not None and len(stops_latlon) >= 2:
        try:
            g = osrm.geometria_ruta(stops_latlon)
            coords = g.get("geojson", {}).get("coordinates")
            if coords:
                base["path_lonlat"] = [[float(x), float(y)] for x, y in coords]
                base["origen"] = g.get("origen", "osrm")
        except Exception:  # noqa: BLE001  (degradado: queda la poligonal recta)
            pass
    return base
