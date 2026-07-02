"""Pruebas del cerebro robusto: conjunto de ambiguedad, CVaR y pipeline DRO."""
import numpy as np
import pytest

from core.data_models import (Hub, Incidencia, Parametros, Pedido, PerfilDecision,
                              Vehiculo, Zona)
from core.optimizer_ortools import ORTOOLS_OK
from core.planner import planificar
from core.risk_engine import cvar, var
from core.uncertainty import conjunto_ambiguedad, probabilidades_por_nodo


def test_cvar_es_la_cola_y_supera_al_var():
    x = list(range(1, 101))                     # 1..100
    v90 = var(x, 0.9)
    c90 = cvar(x, 0.9)                           # media del peor 10% (91..100) = 95.5
    assert v90 == pytest.approx(np.quantile(x, 0.9))
    assert c90 > v90
    assert c90 == pytest.approx(95.5, abs=1.0)


def test_conjunto_ambiguedad_nominal_primero_y_peores_mas_severos():
    a = conjunto_ambiguedad("medio")
    assert a[0].nombre == "nominal"
    assert len(a) >= 2
    assert any(c.sigma_viaje > a[0].sigma_viaje and c.mult_incidencia > 1.0 for c in a[1:])
    assert len(conjunto_ambiguedad("alto")) >= len(conjunto_ambiguedad("bajo"))


def test_probabilidades_por_nodo_cruza_incidencias_y_zona():
    pedidos = [Pedido("P1", "C1", "SJL", -12.0, -77.0, "09:00", "13:00"),
               Pedido("P2", "C2", "Miraflores", -12.1, -77.0, "09:00", "13:00")]
    zonas = [Zona("SJL", "Este"), Zona("Miraflores", "CentroSur")]
    inc = [Incidencia("I1", "accidente", macrozona="Este", probabilidad=0.2, duracion_min=30)]
    ip, idl, au = probabilidades_por_nodo(pedidos, inc, zonas)
    assert ip[1] > 0 and idl[1] == 30      # SJL (macrozona Este) afectado
    assert ip[2] == 0                       # Miraflores no
    assert au[0] == 0.0                     # HUB sin ausencia


def _contexto():
    hub = Hub("HUB", "Almacen", "Callao", -12.05, -77.12, "09:00", "19:00")
    pedidos = [
        Pedido("P1", "C1", "Miraflores", -12.12, -77.03, "09:00", "13:00", peso_kg=40),
        Pedido("P2", "C2", "San Isidro", -12.10, -77.04, "09:00", "13:00", peso_kg=35),
        Pedido("P3", "C3", "SJL", -12.00, -76.99, "10:00", "16:00", peso_kg=50),
        Pedido("P4", "C4", "La Molina", -12.08, -76.95, "10:00", "16:00", peso_kg=30),
        Pedido("P5", "C5", "Callao", -12.06, -77.11, "09:00", "12:00", peso_kg=45),
    ]
    vehiculos = [Vehiculo("V1", capacidad_m3=10, capacidad_kg=400),
                 Vehiculo("V2", capacidad_m3=10, capacidad_kg=400)]
    zonas = [Zona("Miraflores", "CentroSur", 1.2, 1.25, 1.0),
             Zona("San Isidro", "CentroSur", 1.15, 1.2, 1.0),
             Zona("SJL", "Este", 1.3, 1.0, 1.35),
             Zona("La Molina", "Este", 1.15, 1.05, 1.0),
             Zona("Callao", "Oeste", 1.0, 1.0, 1.05)]
    incidencias = [Incidencia("I1", "accidente", macrozona="Este", franja="",
                              probabilidad=0.15, duracion_min=35, impacto_tiempo=1.4)]
    perfiles = [PerfilDecision("eficiente", w_tiempo=1.0, w_tardanza=0.4, w_riesgo=0.3),
                PerfilDecision("robusta", w_tiempo=0.5, w_tardanza=0.8, w_riesgo=1.0)]
    params = Parametros(tiempo_solver_seg=2, iteraciones_montecarlo=15, usar_osrm=False)
    return {"hub": hub, "pedidos": pedidos, "vehiculos": vehiculos, "zonas": zonas,
            "trafico": [], "eventos": [], "incidencias": incidencias, "perfiles": perfiles,
            "parametros": params, "tiempos_servicio": []}


@pytest.mark.skipif(not ORTOOLS_OK, reason="OR-Tools no disponible")
def test_pipeline_robusto_dro():
    res = planificar(_contexto(), robusto=True, radio_ambiguedad="bajo")
    assert res["factible"] is True
    assert "robusto" in res["modo"]
    assert res["evaluaciones"] and "score_robusto" in res["evaluaciones"][0]
    # peor caso no puede ser mejor que el nominal en riesgo (OTD peor <= OTD nominal)
    e0 = res["evaluaciones"][0]
    assert e0["otd_peor"] <= e0["otd_nominal"] + 1e-9
    assert res["perfil_recomendado"] is not None       # puede ser un perfil o una candidata ALNS
    assert res["escenario"]["rutas"]
    assert "nominal" in res["ambiguedad"]


@pytest.mark.skipif(not ORTOOLS_OK, reason="OR-Tools no disponible")
def test_reporte_compatible_con_vistas():
    from core.metrics import kpis_recomendada, tabla_candidatas, tabla_iri
    res = planificar(_contexto(), robusto=True, radio_ambiguedad="bajo")
    tc = tabla_candidatas(res)
    assert "otd" in tc.columns and "score_robusto" in tc.columns
    assert "iri" in tabla_iri(res).columns
    assert "otd" in kpis_recomendada(res)
