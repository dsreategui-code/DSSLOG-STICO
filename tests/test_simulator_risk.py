"""Pruebas del simulador SimPy + Monte Carlo + motor de riesgo (IRI/KPIs)."""
import numpy as np

from core.risk_engine import calcular_iri, clasificar_iri, kpis_montecarlo
from core.simulator_simpy import ContextoSim, montecarlo, simular_una_corrida


def _ctx(ventana_fin_p2):
    # HUB(0) -> P1(1) -> P2(2). Viaje 10 min cada tramo, servicio ~5 min.
    t = np.array([[0, 10, 25], [10, 0, 15], [25, 15, 0]], dtype=float)
    return ContextoSim(
        tiempo_min=t, rutas={"V1": [0, 1, 2]},
        ventana_ini=[0, 0, 0], ventana_fin=[600, 600, ventana_fin_p2],
        serv_min=[0, 4, 4], serv_moda=[0, 5, 5], serv_max=[0, 8, 8],
        pedido_ids=["HUB", "P1", "P2"], sigma_viaje=0.2)


def test_una_corrida_devuelve_dos_entregas():
    reg = simular_una_corrida(_ctx(600), seed=1)
    assert {r["pedido_id"] for r in reg} == {"P1", "P2"}
    assert all(r["eta_min"] >= 0 for r in reg)


def test_reproducibilidad_misma_semilla():
    a = montecarlo(_ctx(600), iteraciones=30, semilla_base=7)
    b = montecarlo(_ctx(600), iteraciones=30, semilla_base=7)
    assert np.allclose(a.sort_values(["iteracion", "pedido_id"])["eta_min"].to_numpy(),
                       b.sort_values(["iteracion", "pedido_id"])["eta_min"].to_numpy())


def test_iri_bajo_si_ventana_amplia():
    m = montecarlo(_ctx(600), iteraciones=200, semilla_base=42)
    iri = calcular_iri(m).set_index("pedido_id")
    assert iri.loc["P2", "iri"] < 0.05
    assert iri.loc["P2", "clasificacion"] == "Bajo"


def test_iri_alto_si_ventana_imposible():
    # P2 se alcanza ~25-30 min; ventana cierra a los 5 -> casi siempre tarde.
    m = montecarlo(_ctx(5), iteraciones=200, semilla_base=42)
    iri = calcular_iri(m).set_index("pedido_id")
    assert iri.loc["P2", "iri"] > 0.8
    assert iri.loc["P2", "clasificacion"] == "Critico"


def test_clasificacion_limites():
    assert clasificar_iri(0.30) == "Bajo"
    assert clasificar_iri(0.31) == "Moderado"
    assert clasificar_iri(0.61) == "Alto"
    assert clasificar_iri(0.81) == "Critico"


def test_kpis_montecarlo_coherentes():
    m = montecarlo(_ctx(600), iteraciones=100, semilla_base=42)
    k = kpis_montecarlo(m)
    assert 0.0 <= k["otd"] <= 1.0
    assert 0.0 <= k["first_attempt_success"] <= 1.0
    assert k["n_pedidos"] == 2
    assert k["tardanza_p90_min"] >= k["tardanza_prom_min"] - 1e-6
