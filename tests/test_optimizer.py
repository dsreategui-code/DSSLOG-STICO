"""Tests del optimizador de rutas (greedy y OR-Tools)."""
import pytest
import pandas as pd

from optimization.route_optimizer import (
    construir_rutas_iniciales, asignar_pedidos, reordenar_intravehiculo, Ruta,
)
from optimization.constraints import respects_intravehicle


def _to_asignacion_df(rutas: dict) -> pd.DataFrame:
    rows = []
    for veh_id, ruta in rutas.items():
        for i, pid in enumerate(ruta.secuencia, start=1):
            rows.append({"vehiculo_id": veh_id, "pedido_id": pid, "secuencia": i})
    return pd.DataFrame(rows)


# ---------------- Motor greedy ----------------

def test_greedy_asigna_todos_los_pedidos(pedidos_min, vehiculos_min):
    rutas = construir_rutas_iniciales(pedidos_min, vehiculos_min, motor="greedy")
    asign = _to_asignacion_df(rutas)
    assert len(asign) == len(pedidos_min)


def test_greedy_respeta_intravehiculo(pedidos_min, vehiculos_min):
    rutas = construir_rutas_iniciales(pedidos_min, vehiculos_min, motor="greedy")
    asign = _to_asignacion_df(rutas)
    assert respects_intravehicle(asign)


def test_greedy_no_excede_capacidad_unidades(pedidos_min, vehiculos_min):
    rutas = construir_rutas_iniciales(pedidos_min, vehiculos_min, motor="greedy")
    for veh_id, ruta in rutas.items():
        cap = int(vehiculos_min[vehiculos_min["vehiculo_id"] == veh_id]
                  ["capacidad_unidades"].iloc[0])
        assert len(ruta.secuencia) <= cap, f"{veh_id} excede capacidad"


def test_greedy_no_excede_capacidad_kg(pedidos_min, vehiculos_min):
    rutas = construir_rutas_iniciales(pedidos_min, vehiculos_min, motor="greedy")
    pesos = dict(zip(pedidos_min["pedido_id"], pedidos_min["peso_kg"]))
    for veh_id, ruta in rutas.items():
        cap_kg = float(vehiculos_min[vehiculos_min["vehiculo_id"] == veh_id]
                       ["capacidad_kg"].iloc[0])
        carga = sum(pesos[p] for p in ruta.secuencia)
        assert carga <= cap_kg, f"{veh_id} excede capacidad en kg"


def test_greedy_prefiere_zona(pedidos_min, vehiculos_min):
    """Los pedidos de Callao deberian ir mayoritariamente al vehiculo de Callao."""
    rutas = construir_rutas_iniciales(pedidos_min, vehiculos_min, motor="greedy")
    callao_v = rutas["V01"]
    moderna_v = rutas["V02"]
    zona = pedidos_min.set_index("pedido_id")["zona"].to_dict()
    callao_count = sum(1 for p in callao_v.secuencia if zona[p] == "Callao / Oeste")
    moderna_count = sum(1 for p in moderna_v.secuencia if zona[p] == "Lima Moderna")
    # Cada vehiculo de zona debe captar al menos un pedido de su zona
    assert callao_count >= 1
    assert moderna_count >= 1


# ---------------- Reordenamiento intravehiculo ----------------

def test_reordenar_solo_pendientes_no_mueve_entregados(pedidos_min):
    ruta = Ruta(vehiculo_id="V01",
                secuencia=["P001", "P002", "P003", "P006"])
    # P001 y P002 ya entregados; P003 y P006 pendientes
    nueva = reordenar_intravehiculo(
        ruta, pedidos_min, pedidos_pendientes=["P003", "P006"],
    )
    # Los entregados conservan su posicion y orden
    assert nueva.secuencia[:2] == ["P001", "P002"]
    # Los pendientes siguen siendo los mismos pedidos, posiblemente reordenados
    assert set(nueva.secuencia[2:]) == {"P003", "P006"}


def test_reordenar_no_introduce_pedidos_de_otros_vehiculos(pedidos_min):
    """Regla intravehiculo: no se agregan pedidos externos."""
    ruta = Ruta(vehiculo_id="V01", secuencia=["P001", "P002"])
    nueva = reordenar_intravehiculo(
        ruta, pedidos_min, pedidos_pendientes=["P001", "P002"],
    )
    assert set(nueva.secuencia).issubset({"P001", "P002"})


# ---------------- Motor OR-Tools (opcional) ----------------

def test_ortools_es_drop_in_replacement(pedidos_min, vehiculos_min):
    """Si OR-Tools esta disponible, la solucion debe respetar las mismas restricciones."""
    from optimization import route_optimizer_ortools as ort
    if not ort.is_available():
        pytest.skip("OR-Tools no instalado en este entorno.")

    rutas = construir_rutas_iniciales(pedidos_min, vehiculos_min,
                                      motor="ortools", time_limit_seconds=4)
    assert rutas is not None
    asign = _to_asignacion_df(rutas)
    assert respects_intravehicle(asign)
    # Al menos algun vehiculo debe haber recibido pedidos
    asignados = sum(1 for r in rutas.values() if r.secuencia)
    assert asignados >= 1
