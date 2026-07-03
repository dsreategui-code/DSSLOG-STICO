"""Cliente de OSRM local: matriz base de tiempos/distancias y geometrias de ruta.

OSRM es la UNICA API geoespacial permitida y se asume ejecutada de forma local. Este
cliente:
  - Consulta el Table Service -> matriz de duracion (min) y distancia (km).
  - Consulta el Route Service -> geometria GeoJSON, duracion y distancia de un recorrido.
  - Cachea las matrices en Parquet y las geometrias en JSON, indexadas por un hash de las
    coordenadas, para evitar recomputar si los pedidos/coordenadas no cambian.
  - Ante OSRM no disponible: usa cache si existe; si no, lanza un error CLARO. NUNCA se
    conecta a APIs externas alternativas.

Convencion de coordenadas: las funciones publicas reciben coordenadas del dominio como
(lat, lon). OSRM requiere (lon, lat); la conversion se hace internamente aqui.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import requests

from config.cortex_settings import (OSRM_BASE_URL, OSRM_CACHE_DIR, OSRM_PROFILE,
                                     OSRM_TIMEOUT_S)

Coord = Tuple[float, float]  # (lat, lon)


class OSRMNoDisponible(RuntimeError):
    """OSRM local no responde y no hay cache utilizable para la consulta solicitada."""


def _clave(coords: Sequence[Coord], profile: str, kind: str) -> str:
    """Hash estable de un conjunto de coordenadas (redondeadas) + perfil + tipo."""
    base = ";".join(f"{round(lat, 6)},{round(lon, 6)}" for lat, lon in coords)
    h = hashlib.sha1(f"{profile}|{kind}|{base}".encode("utf-8")).hexdigest()[:16]
    return h


class OSRMClient:
    """Cliente HTTP fino sobre un servidor OSRM local, con cache en disco."""

    def __init__(self, base_url: str = OSRM_BASE_URL, profile: str = OSRM_PROFILE,
                 timeout: int = OSRM_TIMEOUT_S, cache_dir: Path = OSRM_CACHE_DIR):
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self.timeout = timeout
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------- #
    # Utilidades
    # ----------------------------------------------------------------- #
    @staticmethod
    def _coords_a_osrm(coords: Sequence[Coord]) -> str:
        """(lat, lon) del dominio -> 'lon,lat;lon,lat;...' que exige OSRM."""
        return ";".join(f"{lon},{lat}" for lat, lon in coords)

    def disponible(self) -> bool:
        """True si el servidor OSRM local responde a una consulta trivial."""
        try:
            url = f"{self.base_url}/nearest/v1/{self.profile}/-77.12,-12.05"
            r = requests.get(url, timeout=min(self.timeout, 5))
            return r.status_code == 200 and r.json().get("code") == "Ok"
        except Exception:  # noqa: BLE001
            return False

    def snap(self, coord: Coord) -> Tuple[Coord, float]:
        """Pega una coordenada (lat, lon) al camino transitable mas cercano (servicio nearest).

        Devuelve ((lat, lon) pegada, distancia_m al camino). Si OSRM no responde, devuelve la
        coordenada original y distancia -1. Un `distancia` grande (p. ej. >300 m) indica que el
        punto estaba lejos de toda via (tipicamente en el mar o zona no accesible).
        """
        lat, lon = float(coord[0]), float(coord[1])
        try:
            url = f"{self.base_url}/nearest/v1/{self.profile}/{lon},{lat}?number=1"
            r = requests.get(url, timeout=min(self.timeout, 5))
            d = r.json()
            if d.get("code") == "Ok" and d.get("waypoints"):
                wp = d["waypoints"][0]
                lo, la = wp["location"]                  # OSRM devuelve [lon, lat]
                return (round(float(la), 6), round(float(lo), 6)), float(wp.get("distance", 0.0))
        except Exception:  # noqa: BLE001
            pass
        return (lat, lon), -1.0

    def snap_coords(self, coords: Sequence[Coord]) -> List[Tuple[Coord, float]]:
        """Pega una lista de coordenadas (lat, lon) al camino mas cercano."""
        return [self.snap(c) for c in coords]

    # ----------------------------------------------------------------- #
    # Table Service -> matriz de tiempos y distancias
    # ----------------------------------------------------------------- #
    def _ruta_cache_tabla(self, clave: str) -> Path:
        return self.cache_dir / f"osrm_table_{clave}.parquet"

    def matriz_base(self, coords: Sequence[Coord], usar_cache: bool = True,
                    regenerar: bool = False) -> dict:
        """Devuelve {'duracion_min': ndarray (NxN), 'distancia_km': ndarray (NxN),
        'n': N, 'origen': 'osrm'|'cache'}.

        Nodo 0 = HUB; 1..N-1 = pedidos (en el orden dado).
        """
        coords = [(float(la), float(lo)) for la, lo in coords]
        n = len(coords)
        clave = _clave(coords, self.profile, "table")
        cache_path = self._ruta_cache_tabla(clave)

        if usar_cache and not regenerar and cache_path.exists():
            dur, dist = self._leer_tabla_cache(cache_path, n)
            return {"duracion_min": dur, "distancia_km": dist, "n": n, "origen": "cache"}

        # Consultar OSRM Table Service.
        url = (f"{self.base_url}/table/v1/{self.profile}/{self._coords_a_osrm(coords)}"
               f"?annotations=duration,distance")
        try:
            r = requests.get(url, timeout=self.timeout)
            data = r.json()
        except Exception as e:  # noqa: BLE001
            if usar_cache and cache_path.exists():
                dur, dist = self._leer_tabla_cache(cache_path, n)
                return {"duracion_min": dur, "distancia_km": dist, "n": n, "origen": "cache"}
            raise OSRMNoDisponible(
                f"No se pudo consultar OSRM en {self.base_url} y no hay cache para estas "
                f"coordenadas. Levanta OSRM local o genera la cache. Detalle: {e}")
        if data.get("code") != "Ok":
            raise OSRMNoDisponible(f"OSRM respondio code={data.get('code')}: {data.get('message')}")

        dur = np.asarray(data["durations"], dtype=float) / 60.0          # s -> min
        dist = np.asarray(data["distances"], dtype=float) / 1000.0        # m -> km
        if usar_cache:
            self._escribir_tabla_cache(cache_path, dur, dist)
        return {"duracion_min": dur, "distancia_km": dist, "n": n, "origen": "osrm"}

    @staticmethod
    def _leer_tabla_cache(path: Path, n: int):
        df = pd.read_parquet(path)
        dur = np.zeros((n, n), dtype=float)
        dist = np.zeros((n, n), dtype=float)
        for i, j, dm, dk in zip(df["i"], df["j"], df["duracion_min"], df["distancia_km"]):
            dur[int(i), int(j)] = dm
            dist[int(i), int(j)] = dk
        return dur, dist

    @staticmethod
    def _escribir_tabla_cache(path: Path, dur: np.ndarray, dist: np.ndarray):
        n = dur.shape[0]
        filas = [(i, j, float(dur[i, j]), float(dist[i, j]))
                 for i in range(n) for j in range(n)]
        pd.DataFrame(filas, columns=["i", "j", "duracion_min", "distancia_km"]).to_parquet(path, index=False)

    # ----------------------------------------------------------------- #
    # Route Service -> geometria real del recorrido
    # ----------------------------------------------------------------- #
    def _ruta_cache_geom(self, clave: str) -> Path:
        return self.cache_dir / f"osrm_route_{clave}.json"

    def geometria_ruta(self, coords: Sequence[Coord], usar_cache: bool = True,
                       regenerar: bool = False) -> dict:
        """Geometria real de un recorrido que pasa por `coords` en orden.

        Devuelve {'geojson': {...}, 'duracion_min': float, 'distancia_km': float,
        'legs': [{'duracion_min':..,'distancia_km':..}, ...], 'origen': ...}.
        """
        coords = [(float(la), float(lo)) for la, lo in coords]
        if len(coords) < 2:
            return {"geojson": {"type": "LineString", "coordinates": []},
                    "duracion_min": 0.0, "distancia_km": 0.0, "legs": [], "origen": "vacio"}
        clave = _clave(coords, self.profile, "route")
        cache_path = self._ruta_cache_geom(clave)

        if usar_cache and not regenerar and cache_path.exists():
            d = json.loads(cache_path.read_text(encoding="utf-8"))
            d["origen"] = "cache"
            return d

        url = (f"{self.base_url}/route/v1/{self.profile}/{self._coords_a_osrm(coords)}"
               f"?overview=full&geometries=geojson&annotations=duration,distance")
        try:
            r = requests.get(url, timeout=self.timeout)
            data = r.json()
        except Exception as e:  # noqa: BLE001
            if usar_cache and cache_path.exists():
                d = json.loads(cache_path.read_text(encoding="utf-8"))
                d["origen"] = "cache"
                return d
            raise OSRMNoDisponible(
                f"No se pudo consultar la geometria en OSRM ({self.base_url}) ni hay cache. "
                f"Detalle: {e}")
        if data.get("code") != "Ok" or not data.get("routes"):
            raise OSRMNoDisponible(f"OSRM route respondio code={data.get('code')}")

        ruta = data["routes"][0]
        out = {
            "geojson": ruta["geometry"],                       # LineString GeoJSON (lon,lat)
            "duracion_min": float(ruta["duration"]) / 60.0,
            "distancia_km": float(ruta["distance"]) / 1000.0,
            "legs": [{"duracion_min": float(l["duration"]) / 60.0,
                      "distancia_km": float(l["distance"]) / 1000.0}
                     for l in ruta.get("legs", [])],
            "origen": "osrm",
        }
        if usar_cache:
            cache_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out

    # ----------------------------------------------------------------- #
    # Mantenimiento de cache
    # ----------------------------------------------------------------- #
    def limpiar_cache(self) -> int:
        """Borra toda la cache OSRM. Devuelve el numero de archivos eliminados."""
        archivos = list(self.cache_dir.glob("osrm_*"))
        for f in archivos:
            f.unlink()
        return len(archivos)

    def estado_cache(self) -> dict:
        tablas = list(self.cache_dir.glob("osrm_table_*.parquet"))
        rutas = list(self.cache_dir.glob("osrm_route_*.json"))
        return {"tablas": len(tablas), "geometrias": len(rutas),
                "directorio": str(self.cache_dir)}
