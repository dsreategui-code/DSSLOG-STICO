"""Punto 1: robustez POR DISENO en el ALNS via Sample Average Approximation (SAA) + CVaR.

Verifica el paquete de escenarios (numeros aleatorios comunes / CRN), que el objetivo robusto
penaliza la COLA de tardanza (CVaR) y que optimizar sobre los escenarios protege una ventana
ajustada mejor que el costo deterministico."""
import numpy as np

from core.alns import optimizar
from core.data_models import Parametros
from core.optimizer_ortools import ModeloNumerico
from core.saa import (comparar_robustez, construir_escenarios, evaluar_escenarios,
                      tardanza_por_escenario)


def _modelo_ventana_ajustada(ventana_b=(0, 25)):
    """1 vehiculo, 3 clientes. B (nodo 2) esta cerca del hub con ventana AJUSTADA: visitarlo
    tarde lo pone en riesgo. Los dos ordenes B-primero y B-ultimo tienen el MISMO viaje (80),
    asi que la unica diferencia entre ellos es el riesgo de tardanza."""
    t = np.array([
        [0, 30, 10, 30],
        [30, 0, 25, 15],
        [10, 25, 0, 25],
        [30, 15, 25, 0],
    ], dtype=float)
    return ModeloNumerico(
        tiempo_min=t, dist_km=t * 0.4, demanda_m3=[0, 1, 1, 1], demanda_kg=[0, 10, 10, 10],
        ventanas_min=[(0, 600), (0, 600), ventana_b, (0, 600)], servicio_min=[0, 5, 5, 5],
        pedido_ids=["HUB", "A", "B", "C"], num_vehiculos=1, cap_m3=[100], cap_kg=[100],
        vehiculo_ids=["V1"], horizonte_min=600)


def _esc(m, **kw):
    n = int(m.tiempo_min.shape[0])
    return construir_escenarios(m, [0.0] * n, [0.0] * n, [0.0] * n,
                                n_escenarios=kw.get("n", 40), sigma_viaje=0.25,
                                sigma_sistemico=0.10, seed=kw.get("seed", 1))


def test_escenarios_reproducibles_y_factor_dia_centrado():
    m = _modelo_ventana_ajustada()
    a = _esc(m, seed=7)
    b = _esc(m, seed=7)
    assert np.allclose(a.factor_dia, b.factor_dia)
    assert np.allclose(a.mult, b.mult)
    # El factor sistemico del dia tiene esperanza ~1 (log-normal centrada).
    assert abs(float(a.factor_dia.mean()) - 1.0) < 0.15
    # Semillas distintas -> escenarios distintos.
    c = _esc(m, seed=8)
    assert not np.allclose(a.factor_dia, c.factor_dia)


def test_cvar_no_menor_que_media_y_penaliza_cola():
    m = _modelo_ventana_ajustada()
    esc = _esc(m, n=60, seed=3)
    # Orden fragil (B al final) vs robusto (B primero); mismo viaje total.
    ev_rob = evaluar_escenarios([[2, 1, 3]], m, 10.0, esc, alpha=0.9, beta=1.0)
    ev_fra = evaluar_escenarios([[1, 3, 2]], m, 10.0, esc, alpha=0.9, beta=1.0)
    # CVaR (cola) nunca por debajo de la media de tardanza.
    assert ev_rob["cvar_tard"] >= ev_rob["tard_media"] - 1e-9
    assert ev_fra["cvar_tard"] >= ev_fra["tard_media"] - 1e-9
    # El orden robusto tiene MUCHO menos riesgo de cola y menor costo robusto total.
    assert ev_rob["cvar_tard"] < ev_fra["cvar_tard"]
    assert ev_rob["costo"] < ev_fra["costo"]


def test_saa_protege_ventana_ajustada_mejor_que_deterministico():
    # Ventana de B on-time en el caso NOMINAL aunque se visite al final (80<=82), pero con
    # variabilidad su cola incumple: el costo deterministico es indiferente, el SAA no.
    m = _modelo_ventana_ajustada(ventana_b=(0, 82))
    esc = _esc(m, n=50, seed=2)
    par = Parametros(iteraciones_alns=400, semilla_base=5)
    det = optimizar(m, par)                                   # objetivo deterministico
    saa = optimizar(m, par, escenarios=esc, alpha=0.9, beta=1.0)   # objetivo robusto (SAA+CVaR)

    def _routes(res):
        return [[s.idx_nodo for s in rc.secuencia] for rc in res["best"]["rutas"].values()]

    assert saa["best"]["status"] == "ok"
    assert {s.idx_nodo for r in saa["best"]["rutas"].values() for s in r.secuencia} == {1, 2, 3}
    obj_det = evaluar_escenarios(_routes(det), m, 10.0, esc, alpha=0.9, beta=1.0)["costo"]
    obj_saa = evaluar_escenarios(_routes(saa), m, 10.0, esc, alpha=0.9, beta=1.0)["costo"]
    # Optimizar el objetivo robusto no es peor (y suele ser mejor) que el deterministico
    # cuando se evaluan ambos sobre los MISMOS escenarios.
    assert obj_saa <= obj_det + 1e-6


def test_tardanza_por_escenario_vector_de_largo_S():
    m = _modelo_ventana_ajustada()
    esc = _esc(m, n=33, seed=4)
    tv = tardanza_por_escenario([[2, 1, 3]], m, esc)
    assert tv.shape == (33,)
    assert (tv >= 0).all()


def _modelo_trade_off():
    """1 vehiculo, 3 clientes. B (nodo 2) tiene ventana ajustada (0,85) y su arribo NOMINAL como
    ultima parada (~80) cabe justo, por lo que el objetivo DETERMINISTA prefiere el orden
    B-ultimo (viaje 80 < 95); pero ese orden es FRAGIL: con variabilidad B suele incumplir. El
    objetivo ROBUSTO (SAA) prefiere B-primero (arribo ~10, seguro) a costa de +15 km de viaje."""
    t = np.array([
        [0, 40, 10, 40],
        [40, 0, 30, 15],
        [10, 30, 0, 15],
        [40, 15, 15, 0],
    ], dtype=float)
    return ModeloNumerico(
        tiempo_min=t, dist_km=t * 0.4, demanda_m3=[0, 1, 1, 1], demanda_kg=[0, 10, 10, 10],
        ventanas_min=[(0, 600), (0, 600), (0, 85), (0, 600)], servicio_min=[0, 5, 5, 5],
        pedido_ids=["HUB", "A", "B", "C"], num_vehiculos=1, cap_m3=[100], cap_kg=[100],
        vehiculo_ids=["V1"], horizonte_min=600)


def test_benchmark_saa_no_empeora_la_cola_fuera_de_muestra():
    # El benchmark corre ALNS deterministico vs robusto (SAA) y mide la tardanza FUERA DE
    # MUESTRA. Propiedad garantizada: el robusto NUNCA empeora la cola (CVaR) de tardanza
    # respecto del deterministico. La reduccion estricta se da en instancias con trade-off real
    # (ver test_cvar_no_menor_que_media_y_penaliza_cola para el objetivo, y el script de
    # benchmark sobre datos reales para la magnitud).
    m = _modelo_trade_off()
    n = int(m.tiempo_min.shape[0])
    out = comparar_robustez(m, Parametros(iteraciones_alns=400, semilla_base=5),
                            [0.0] * n, [0.0] * n, [0.0] * n, alpha=0.9, beta=1.0,
                            n_train=40, n_val=300, seed_train=1, seed_val=99991)
    assert out["robusto_saa"]["servidos"] == 3 and out["determinista"]["servidos"] == 3
    assert out["robusto_saa"]["cvar_tard_min"] <= out["determinista"]["cvar_tard_min"] + 1e-6
    assert out["reduccion_cvar_min"] >= -1e-6
