"""Pruebas del optimizador CORTEX (CVRPTW matrix-driven con perfiles)."""
import numpy as np
import pytest

from core.candidate_generator import (generar_candidatas, kpis_candidata, preparar_modelo)
from core.data_models import Hub, Parametros, Pedido, PerfilDecision, Vehiculo
from core.optimizer_ortools import ORTOOLS_OK, ModeloNumerico, resolver_cvrptw

pytestmark = pytest.mark.skipif(not ORTOOLS_OK, reason="OR-Tools no disponible")


def _modelo_pequeno():
    # Hub + 4 clientes; matriz simetrica de tiempos (min) y distancias (km).
    t = np.array([
        [0, 10, 12, 20, 22],
        [10, 0, 8, 15, 18],
        [12, 8, 0, 10, 14],
        [20, 15, 10, 0, 6],
        [22, 18, 14, 6, 0],
    ], dtype=float)
    d = t * 0.4
    return ModeloNumerico(
        tiempo_min=t, dist_km=d,
        demanda_m3=[0, 1, 1, 1, 1], demanda_kg=[0, 50, 60, 40, 55],
        ventanas_min=[(0, 600), (0, 600), (0, 600), (0, 600), (0, 600)],
        servicio_min=[0, 5, 5, 5, 5], pedido_ids=["HUB", "P1", "P2", "P3", "P4"],
        num_vehiculos=2, cap_m3=[10, 10], cap_kg=[500, 500],
        vehiculo_ids=["V1", "V2"], horizonte_min=600)


def test_resuelve_y_sirve_a_todos():
    m = _modelo_pequeno()
    perfil = PerfilDecision("eficiente", w_tiempo=1.0)
    res = resolver_cvrptw(m, perfil, Parametros(tiempo_solver_seg=3))
    assert res["status"] == "ok"
    servidos = {s.idx_nodo for r in res["rutas"].values() for s in r.secuencia}
    assert servidos == {1, 2, 3, 4}
    assert res["no_servidos"] == []


def test_eta_monotona_y_cargas_acumuladas():
    m = _modelo_pequeno()
    res = resolver_cvrptw(m, PerfilDecision("eficiente"), Parametros(tiempo_solver_seg=3))
    for r in res["rutas"].values():
        etas = [s.eta_min for s in r.secuencia]
        assert etas == sorted(etas)                  # ETA no decreciente en la ruta
        cargas = [s.carga_kg_acum for s in r.secuencia]
        assert cargas == sorted(cargas)              # carga acumulada creciente


def test_ventana_estricta_genera_tardanza_o_descartes():
    # Cliente 4 con ventana imposible (cierra en 5 min) -> tardanza > 0 o no servido.
    m = _modelo_pequeno()
    m.ventanas_min[4] = (0, 5)
    res = resolver_cvrptw(m, PerfilDecision("puntual", w_tardanza=1.0),
                          Parametros(tiempo_solver_seg=3))
    tardanza = sum(s.tardanza_min for r in res["rutas"].values() for s in r.secuencia)
    servido_4 = any(s.idx_nodo == 4 for r in res["rutas"].values() for s in r.secuencia)
    assert (tardanza > 0) or (not servido_4)


def test_doble_capacidad_peso_fuerza_dos_rutas():
    m = _modelo_pequeno()
    # Capacidad de peso pequena: ningun vehiculo puede con los 4 (205 kg) solo.
    m.cap_kg = [120, 120]
    res = resolver_cvrptw(m, PerfilDecision("eficiente"), Parametros(tiempo_solver_seg=3))
    cargas = [r.secuencia[-1].carga_kg_acum for r in res["rutas"].values()]
    assert all(c <= 120 + 1e-6 for c in cargas)      # respeta capacidad de peso
    assert len(res["rutas"]) >= 2


def test_generar_candidatas_por_perfil():
    hub = Hub("HUB", "Almacen", "Callao", -12.05, -77.12)
    pedidos = [Pedido(f"P{i}", f"C{i}", "Callao", -12.05 - i * 0.01, -77.12, "09:00", "19:00",
                      volumen_m3=1, peso_kg=50) for i in range(1, 5)]
    vehiculos = [Vehiculo("V1", capacidad_m3=10, capacidad_kg=500),
                 Vehiculo("V2", capacidad_m3=10, capacidad_kg=500)]
    t = _modelo_pequeno().tiempo_min
    d = _modelo_pequeno().dist_km
    modelo = preparar_modelo(hub, pedidos, vehiculos, t, d)
    perfiles = [PerfilDecision("eficiente", w_tiempo=1.0),
                PerfilDecision("balanceada", w_tiempo=0.7, w_balance=0.5)]
    # usar_alns=False para probar solo la generacion por perfil (sin candidatas ALNS extra).
    cands = generar_candidatas(modelo, perfiles,
                               Parametros(tiempo_solver_seg=3, usar_alns=False))
    assert len(cands) == 2
    assert {c["perfil"] for c in cands} == {"eficiente", "balanceada"}
    for c in cands:
        assert c["kpis"]["cobertura"] == 1.0          # sirve a los 4
