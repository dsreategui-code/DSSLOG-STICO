"""Pruebas del cliente OSRM (sin servidor vivo): se simulan respuestas de OSRM.

Cubren: orden lon,lat; parseo de unidades (s->min, m->km); cache parquet/json;
y el modo degradado (sin servidor y sin cache -> error claro).
"""
import json

import numpy as np
import pytest

from geo.osrm_client import OSRMClient, OSRMNoDisponible, _clave


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _cliente(tmp_path):
    return OSRMClient(base_url="http://localhost:5000", profile="driving",
                      cache_dir=tmp_path)


def test_coords_a_osrm_invierte_a_lon_lat():
    # dominio (lat, lon) -> OSRM 'lon,lat'
    s = OSRMClient._coords_a_osrm([(-12.05, -77.12), (-12.10, -77.00)])
    assert s == "-77.12,-12.05;-77.0,-12.1"


def test_matriz_base_parsea_unidades_y_cachea(tmp_path, monkeypatch):
    payload = {"code": "Ok",
               "durations": [[0, 120], [120, 0]],     # segundos
               "distances": [[0, 2000], [2000, 0]]}   # metros
    monkeypatch.setattr("geo.osrm_client.requests.get",
                        lambda *a, **k: _Resp(payload))
    cli = _cliente(tmp_path)
    coords = [(-12.05, -77.12), (-12.10, -77.00)]
    res = cli.matriz_base(coords)
    assert res["origen"] == "osrm"
    assert np.allclose(res["duracion_min"], [[0, 2], [2, 0]])   # 120 s -> 2 min
    assert np.allclose(res["distancia_km"], [[0, 2], [2, 0]])   # 2000 m -> 2 km

    # Sin servidor (ahora lanza), pero existe cache -> debe leerla.
    def _boom(*a, **k):
        raise ConnectionError("osrm caido")
    monkeypatch.setattr("geo.osrm_client.requests.get", _boom)
    res2 = cli.matriz_base(coords)
    assert res2["origen"] == "cache"
    assert np.allclose(res2["duracion_min"], [[0, 2], [2, 0]])


def test_geometria_ruta_parsea_y_cachea(tmp_path, monkeypatch):
    geojson = {"type": "LineString", "coordinates": [[-77.12, -12.05], [-77.00, -12.10]]}
    payload = {"code": "Ok", "routes": [{
        "geometry": geojson, "duration": 300, "distance": 5000,
        "legs": [{"duration": 300, "distance": 5000}]}]}
    monkeypatch.setattr("geo.osrm_client.requests.get", lambda *a, **k: _Resp(payload))
    cli = _cliente(tmp_path)
    coords = [(-12.05, -77.12), (-12.10, -77.00)]
    g = cli.geometria_ruta(coords)
    assert g["duracion_min"] == 5.0           # 300 s
    assert g["distancia_km"] == 5.0           # 5000 m
    assert g["geojson"]["type"] == "LineString"
    assert g["origen"] == "osrm"
    # cache json escrito y legible
    assert cli.estado_cache()["geometrias"] == 1


def test_sin_servidor_sin_cache_lanza_error_claro(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("osrm caido")
    monkeypatch.setattr("geo.osrm_client.requests.get", _boom)
    cli = _cliente(tmp_path)
    with pytest.raises(OSRMNoDisponible):
        cli.matriz_base([(-12.05, -77.12), (-12.10, -77.00)])


def test_disponible_false_si_no_responde(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("osrm caido")
    monkeypatch.setattr("geo.osrm_client.requests.get", _boom)
    assert _cliente(tmp_path).disponible() is False


def test_clave_estable_y_sensible_a_coords():
    c1 = [(-12.05, -77.12), (-12.10, -77.00)]
    c2 = [(-12.05, -77.12), (-12.10, -77.01)]
    assert _clave(c1, "driving", "table") == _clave(c1, "driving", "table")
    assert _clave(c1, "driving", "table") != _clave(c2, "driving", "table")
