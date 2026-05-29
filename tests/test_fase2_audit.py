"""Auditoria FASE 2 - asignacion de pedidos y filtro coherente en rutas iniciales."""
import math
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from optimization.route_optimizer import (
    asignar_pedidos, construir_rutas_iniciales, reordenar_intravehiculo, Ruta,
)
from optimization.route_optimizer_ortools import is_available, construir_rutas_or_tools
from optimization.constraints import respects_intravehicle
from simulation.replanning import evaluar_replanificacion, aplicar_replanificacion
from views import supervisor_routes


ROOT = Path(__file__).resolve().parent.parent


def _src(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


@pytest.fixture
def dataset_realista():
    """80 pedidos repartidos en 6 zonas + 10 vehiculos como el dataset sintetico."""
    zonas_centroides = {
        "Callao / Oeste":   (-12.06, -77.12),
        "Lima Centro":      (-12.06, -77.04),
        "Lima Norte":       (-11.99, -77.06),
        "Lima Sur":         (-12.18, -76.99),
        "Lima Este":        (-12.05, -76.94),
        "Lima Moderna":     (-12.10, -77.01),
    }
    ventanas = [("09:00", "12:00"), ("10:00", "13:00"), ("12:00", "15:00"),
                ("14:00", "17:00"), ("16:00", "19:00")]
    rng = __import__("random").Random(42)
    zonas_list = list(zonas_centroides.keys())
    pedidos = []
    for i in range(80):
        zona = zonas_list[i % len(zonas_list)]
        lat0, lon0 = zonas_centroides[zona]
        v = ventanas[i % len(ventanas)]
        pedidos.append({
            "pedido_id": f"P{i+1:03d}",
            "cliente": f"C{i+1}",
            "distrito": zona.split(" / ")[0],
            "zona": zona,
            "latitud": lat0 + rng.uniform(-0.025, 0.025),
            "longitud": lon0 + rng.uniform(-0.025, 0.025),
            "modelo": "Comfort",
            "peso_kg": rng.choice([22, 30, 35, 38]),
            "tipo_servicio": "Estandar",
            "tiempo_servicio_min": 10,
            "ventana_inicio": v[0],
            "ventana_fin": v[1],
        })
    pedidos_df = pd.DataFrame(pedidos)

    vehiculos = []
    for i in range(10):
        vehiculos.append({
            "vehiculo_id": f"V{i+1:02d}",
            "placa": f"AB{i+1:02d}",
            "capacidad_unidades": 12,
            "capacidad_kg": 550,
            "zona_preferente": zonas_list[i % len(zonas_list)],
            "conductor": f"Driver{i+1}",
        })
    return pedidos_df, pd.DataFrame(vehiculos)


# ============================================================
# Punto 1 - Distribucion entre los 10 vehiculos
# ============================================================

def test_greedy_usa_al_menos_8_de_10_vehiculos(dataset_realista):
    pedidos, vehiculos = dataset_realista
    asignacion = asignar_pedidos(pedidos, vehiculos)
    usados = sum(1 for pids in asignacion.values() if pids)
    assert usados >= 8, f"Greedy solo usa {usados} vehiculos (esperado >= 8)"


def test_greedy_distribuye_balanceado(dataset_realista):
    """Ningun vehiculo debe llevar mas del 1.5x del promedio."""
    pedidos, vehiculos = dataset_realista
    asignacion = asignar_pedidos(pedidos, vehiculos)
    cargas = [len(p) for p in asignacion.values() if p]
    prom = sum(cargas) / len(cargas)
    maximo = max(cargas)
    assert maximo <= prom * 1.5 + 1, \
        f"Carga maxima {maximo} excede 1.5x el promedio {prom:.1f}"


def test_greedy_asigna_todos_los_pedidos(dataset_realista):
    pedidos, vehiculos = dataset_realista
    asignacion = asignar_pedidos(pedidos, vehiculos)
    total = sum(len(p) for p in asignacion.values())
    assert total == len(pedidos)


def test_greedy_no_excede_capacidad_real(dataset_realista):
    pedidos, vehiculos = dataset_realista
    cap_u = dict(zip(vehiculos["vehiculo_id"], vehiculos["capacidad_unidades"]))
    asignacion = asignar_pedidos(pedidos, vehiculos)
    for v, pids in asignacion.items():
        assert len(pids) <= cap_u[v], f"{v} excede capacidad: {len(pids)} > {cap_u[v]}"


def test_ortools_usa_al_menos_8_de_10_vehiculos(dataset_realista):
    if not is_available():
        pytest.skip("OR-Tools no instalado")
    pedidos, vehiculos = dataset_realista
    rutas = construir_rutas_or_tools(pedidos, vehiculos, time_limit_seconds=6)
    assert rutas is not None
    usados = sum(1 for r in rutas.values() if r.secuencia)
    assert usados >= 8, f"OR-Tools solo usa {usados} vehiculos (esperado >= 8)"


def test_ortools_distribuye_balanceado(dataset_realista):
    if not is_available():
        pytest.skip("OR-Tools no instalado")
    pedidos, vehiculos = dataset_realista
    rutas = construir_rutas_or_tools(pedidos, vehiculos, time_limit_seconds=6)
    cargas = [len(r.secuencia) for r in rutas.values() if r.secuencia]
    prom = sum(cargas) / len(cargas)
    maximo = max(cargas)
    assert maximo <= prom * 1.5 + 1, \
        f"OR-Tools no balancea: max={maximo}, prom={prom:.1f}"


# ============================================================
# Punto 2 - Replanificacion intravehiculo
# ============================================================

def test_replanificacion_no_mueve_pedidos_entre_vehiculos(dataset_realista):
    """Tras una replanificacion, ningun pedido cambia de vehiculo."""
    pedidos, vehiculos = dataset_realista
    rutas = construir_rutas_iniciales(pedidos, vehiculos, motor="greedy")

    # Tomar la ruta del vehiculo con mas pedidos
    veh_objetivo = max(rutas.keys(), key=lambda v: len(rutas[v].secuencia))
    ruta_obj = rutas[veh_objetivo]
    if len(ruta_obj.secuencia) < 2:
        pytest.skip("Vehiculo objetivo sin suficientes pedidos para replanificar")

    pedidos_originales_por_veh = {v: set(r.secuencia) for v, r in rutas.items()}

    # Replanificar pendientes (todos los del vehiculo)
    propuesta = evaluar_replanificacion(
        ruta_obj, pedidos, list(ruta_obj.secuencia),
        hora_actual_min=540,
    )
    rutas_nuevas = aplicar_replanificacion(rutas, propuesta)

    pedidos_nuevos_por_veh = {v: set(r.secuencia) for v, r in rutas_nuevas.items()}

    # El conjunto de pedidos por vehiculo NO debe cambiar
    for v in rutas:
        assert pedidos_originales_por_veh[v] == pedidos_nuevos_por_veh[v], \
            f"Vehiculo {v} cambio su conjunto de pedidos en la replanificacion"


def test_replanificacion_preserva_pedidos_entregados(dataset_realista):
    """Los pedidos ya entregados se mantienen al inicio en su orden."""
    pedidos, vehiculos = dataset_realista
    rutas = construir_rutas_iniciales(pedidos, vehiculos, motor="greedy")
    veh = max(rutas.keys(), key=lambda v: len(rutas[v].secuencia))
    ruta = rutas[veh]
    if len(ruta.secuencia) < 4:
        pytest.skip("Ruta muy corta para distinguir entregados y pendientes")

    entregados = ruta.secuencia[:2]
    pendientes = ruta.secuencia[2:]
    nueva = reordenar_intravehiculo(ruta, pedidos, pendientes)
    assert nueva.secuencia[:2] == entregados, \
        "Los pedidos entregados no deben moverse"
    assert set(nueva.secuencia) == set(ruta.secuencia), \
        "El conjunto total de pedidos del vehiculo debe preservarse"


# ============================================================
# Punto 3 - Filtro coherente en supervisor_routes
# ============================================================

def test_supervisor_routes_define_helpers_de_filtro():
    assert hasattr(supervisor_routes, "_kpis_global")
    assert hasattr(supervisor_routes, "_kpis_vehiculo")
    assert hasattr(supervisor_routes, "_to_ruta_objs")


def test_kpis_global_agrega_y_kpis_vehiculo_individualiza(dataset_realista):
    pedidos, vehiculos = dataset_realista
    rutas = construir_rutas_iniciales(pedidos, vehiculos, motor="greedy")
    rutas_dict = {v: __import__("dataclasses").asdict(r) for v, r in rutas.items()}

    kpis_g = supervisor_routes._kpis_global(rutas_dict)
    pedidos_g = next(k["value"] for k in kpis_g if k["label"] == "Pedidos asignados")
    assert pedidos_g == len(pedidos)   # 80 pedidos en total

    veh_id = next(v for v, r in rutas_dict.items() if r["secuencia"])
    kpis_v = supervisor_routes._kpis_vehiculo(rutas_dict, veh_id, vehiculos)
    pedidos_v = next(k["value"] for k in kpis_v if k["label"] == "Pedidos asignados")
    assert pedidos_v == rutas_dict[veh_id]["carga_unidades"]
    assert pedidos_v < pedidos_g, \
        "KPIs por vehiculo deben mostrar solo su carga, no el total"


def test_supervisor_routes_filtra_tabla_por_vehiculo():
    """El codigo fuente debe filtrar df_rutas cuando veh_id no es None."""
    src = _src("views/supervisor_routes.py")
    assert 'df_rutas = df_rutas[df_rutas["vehiculo_id"] == veh_id]' in src, \
        "supervisor_routes.py debe filtrar la tabla por vehiculo seleccionado"


def test_supervisor_routes_sincroniza_mapa_kpis_tabla():
    """La misma variable veh_id se usa para mapa, kpis y tabla."""
    src = _src("views/supervisor_routes.py")
    # Selector
    assert 'veh_id = None if seleccion == "Todos" else seleccion' in src
    # Mapa usa veh_id
    assert "vehiculo_id=veh_id" in src
    # KPIs distinguen
    assert "_kpis_global(rutas)" in src
    assert "_kpis_vehiculo(rutas, veh_id" in src


def test_to_ruta_objs_convierte_dicts_a_dataclass():
    """Verifica que el bug del type() del codigo anterior quedo arreglado."""
    rutas_dict = {
        "V01": {"vehiculo_id": "V01", "secuencia": ["P001", "P002"],
                "distancia_km": 5.5, "tiempo_min": 30, "carga_unidades": 2, "carga_kg": 44},
    }
    objs = supervisor_routes._to_ruta_objs(rutas_dict)
    assert isinstance(objs["V01"], Ruta)
    assert objs["V01"].secuencia == ["P001", "P002"]
    assert objs["V01"].carga_unidades == 2
