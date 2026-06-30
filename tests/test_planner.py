"""Prueba end-to-end del pipeline de planificacion CORTEX-LM (con matriz de respaldo)."""
import pytest

from core.data_models import (Hub, Parametros, Pedido, PerfilDecision, Vehiculo, Zona)
from core.metrics import kpis_recomendada, tabla_candidatas, tabla_iri
from core.optimizer_ortools import ORTOOLS_OK
from core.planner import planificar

pytestmark = pytest.mark.skipif(not ORTOOLS_OK, reason="OR-Tools no disponible")


def _contexto():
    hub = Hub("HUB", "Almacen", "Callao", -12.05, -77.12, "09:00", "19:00")
    pedidos = [
        Pedido("P1", "C1", "Miraflores", -12.12, -77.03, "09:00", "13:00", peso_kg=40),
        Pedido("P2", "C2", "San Isidro", -12.10, -77.04, "09:00", "13:00", peso_kg=35),
        Pedido("P3", "C3", "Surco", -12.15, -77.00, "10:00", "16:00", peso_kg=50),
        Pedido("P4", "C4", "La Molina", -12.08, -76.95, "10:00", "16:00", peso_kg=30),
        Pedido("P5", "C5", "Callao", -12.06, -77.11, "09:00", "12:00", peso_kg=45),
        Pedido("P6", "C6", "Ate", -12.02, -76.92, "11:00", "17:00", peso_kg=25),
    ]
    vehiculos = [Vehiculo("V1", capacidad_m3=10, capacidad_kg=400),
                 Vehiculo("V2", capacidad_m3=10, capacidad_kg=400)]
    zonas = [Zona("Miraflores", "CentroSur", 1.2, 1.25, 1.0),
             Zona("San Isidro", "CentroSur", 1.15, 1.2, 1.0),
             Zona("La Molina", "Este", 1.15, 1.05, 1.0),
             Zona("Ate", "Este", 1.25, 1.0, 1.2),
             Zona("Callao", "Oeste", 1.0, 1.0, 1.05)]
    perfiles = [PerfilDecision("eficiente", w_tiempo=1.0, w_tardanza=0.4, w_riesgo=0.3),
                PerfilDecision("puntual", w_tiempo=0.5, w_tardanza=1.0, w_riesgo=0.7),
                PerfilDecision("balanceada", w_tiempo=0.7, w_tardanza=0.7, w_riesgo=0.6,
                               w_balance=0.3)]
    params = Parametros(tiempo_solver_seg=2, iteraciones_montecarlo=30, usar_osrm=False)
    return {"hub": hub, "pedidos": pedidos, "vehiculos": vehiculos, "zonas": zonas,
            "trafico": [], "eventos": [], "incidencias": [], "perfiles": perfiles,
            "parametros": params, "tiempos_servicio": []}


def test_pipeline_completo_factible_y_recomienda():
    res = planificar(_contexto())
    assert res["factible"] is True
    assert res["matriz_origen"] == "haversine_respaldo"   # sin OSRM en pruebas
    assert len(res["candidatas"]) == 3
    assert res["perfil_recomendado"] in {"eficiente", "puntual", "balanceada"}


def test_pipeline_genera_escenario_para_gemelo():
    res = planificar(_contexto())
    esc = res["escenario"]
    assert esc is not None and esc["rutas"]
    # todos los pedidos servidos aparecen en alguna ruta
    servidos = {p["pedido_id"] for r in esc["rutas"].values() for p in r}
    assert servidos == {"P1", "P2", "P3", "P4", "P5", "P6"}


def test_tablas_de_reporte():
    res = planificar(_contexto())
    tc = tabla_candidatas(res)
    assert len(tc) == 3 and "otd" in tc.columns
    iri = tabla_iri(res)
    assert "iri" in iri.columns and len(iri) == 6
    kpis = kpis_recomendada(res)
    assert "otd" in kpis and "perfil" in kpis


def test_infactible_si_capacidad_insuficiente():
    ctx = _contexto()
    for v in ctx["vehiculos"]:
        v.capacidad_kg = 50    # flota 100 kg < demanda (~225 kg)
    res = planificar(ctx)
    assert res["factible"] is False
    assert any(c["nombre"] == "capacidad_peso" and not c["ok"]
               for c in res["factibilidad"]["checks"])
