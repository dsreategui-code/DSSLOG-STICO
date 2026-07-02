"""Pruebas del ALNS (búsqueda de gran vecindario adaptativa)."""
import numpy as np
import pytest

from core.alns import _evaluar, optimizar
from core.data_models import Parametros, PerfilDecision
from core.optimizer_ortools import ModeloNumerico


def _modelo(cap_kg=(500, 500)):
    t = np.array([
        [0, 10, 12, 20, 22, 9],
        [10, 0, 8, 15, 18, 11],
        [12, 8, 0, 10, 14, 13],
        [20, 15, 10, 0, 6, 19],
        [22, 18, 14, 6, 0, 21],
        [9, 11, 13, 19, 21, 0],
    ], dtype=float)
    d = t * 0.4
    return ModeloNumerico(
        tiempo_min=t, dist_km=d, demanda_m3=[0, 1, 1, 1, 1, 1],
        demanda_kg=[0, 50, 60, 40, 55, 45],
        ventanas_min=[(0, 600)] * 6, servicio_min=[0, 5, 5, 5, 5, 5],
        pedido_ids=["HUB", "P1", "P2", "P3", "P4", "P5"],
        num_vehiculos=2, cap_m3=[10, 10], cap_kg=list(cap_kg),
        vehiculo_ids=["V1", "V2"], horizonte_min=600)


def _servidos(res):
    return {s.idx_nodo for r in res["rutas"].values() for s in r.secuencia}


def test_alns_sirve_a_todos_los_clientes():
    m = _modelo()
    out = optimizar(m, Parametros(iteraciones_alns=200, semilla_base=1))
    assert out["best"]["status"] == "ok"
    assert _servidos(out["best"]) == {1, 2, 3, 4, 5}


def test_alns_respeta_capacidad():
    m = _modelo(cap_kg=(160, 160))     # 250 kg total -> obliga a 2 rutas
    out = optimizar(m, Parametros(iteraciones_alns=200, semilla_base=2))
    for rc in out["best"]["rutas"].values():
        carga = sum(m.demanda_kg[s.idx_nodo] for s in rc.secuencia)
        assert carga <= 160 + 1e-6
    assert _servidos(out["best"]) == {1, 2, 3, 4, 5}


def test_alns_mejora_sobre_un_inicio_malo():
    m = _modelo()
    # Warm deliberadamente malo: todo en una ruta, orden pesimo.
    from core.optimizer_ortools import ParadaRuta, RutaCandidata
    mala = RutaCandidata(vehiculo_id="V1")
    for c in [4, 1, 3, 2, 5]:
        mala.secuencia.append(ParadaRuta(c, f"P{c}", 0, 0, 0, 0, 0))
    warm = {"status": "ok", "rutas": {"V1": mala}, "no_servidos": [], "perfil": "malo"}
    costo_ini = _evaluar([[4, 1, 3, 2, 5], []], m, None, 10.0)["costo"]
    out = optimizar(m, Parametros(iteraciones_alns=300, semilla_base=3), warm=warm)
    costo_fin = _evaluar([[s.idx_nodo for s in rc.secuencia]
                          for rc in out["best"]["rutas"].values()], m, None, 10.0)["costo"]
    assert costo_fin <= costo_ini + 1e-6


def test_alns_produce_elites():
    m = _modelo()
    out = optimizar(m, Parametros(iteraciones_alns=250, semilla_base=4), n_elites=3)
    assert isinstance(out["elites"], list)
    for e in out["elites"]:
        assert e["status"] == "ok"
