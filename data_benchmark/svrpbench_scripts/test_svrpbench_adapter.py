# -*- coding: utf-8 -*-
"""Fase 5 - Pruebas del adaptador SVRPBench -> DSS.

Valida que:
  - una instancia de 50, 100 y 200 clientes se adapta sin errores;
  - los DataFrames generados tienen las columnas que el DSS espera;
  - el adaptador respeta deposito unico, multi-vehiculo, demanda, capacidad,
    ventanas, coordenadas, clientes e identificador;
  - el manejo de errores funciona (instancia no encontrada);
  - una corrida MINIMA del optimizador actual del DSS acepta una instancia pequena.

NO ejecuta el benchmark final ni todos los modelos.

Uso:
    python data_benchmark/svrpbench_scripts/test_svrpbench_adapter.py        # standalone
    pytest data_benchmark/svrpbench_scripts/test_svrpbench_adapter.py -v
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent.parent
for p in (str(PROJECT_ROOT), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd
import pytest

import svrpbench_to_dss_adapter as ad
from utils.formatters import hhmm_to_minutes

PEDIDOS_COLS = {"pedido_id", "zona", "latitud", "longitud", "peso_kg",
                "tipo_servicio", "tiempo_servicio_min", "ventana_inicio", "ventana_fin"}
VEHICULOS_COLS = {"vehiculo_id", "capacidad_unidades", "capacidad_kg",
                  "zona_preferente", "conductor"}


def _uid_por_tamano(size: int):
    idx = ad.listar_instancias()
    hit = idx[idx["size_declarado"] == size]
    return None if hit.empty else hit.iloc[0]["instance_uid"]


@pytest.mark.parametrize("size", [50, 100, 200])
def test_adapta_sin_errores_y_columnas(size):
    uid = _uid_por_tamano(size)
    if uid is None:
        pytest.skip(f"No hay instancia de {size} clientes en el subconjunto.")
    caso = ad.adaptar_instancia(uid, escribir_archivos=True)

    ped, veh = caso["pedidos"], caso["vehiculos"]
    # Columnas esperadas por el DSS.
    assert PEDIDOS_COLS.issubset(set(ped.columns)), f"faltan columnas en pedidos: {PEDIDOS_COLS - set(ped.columns)}"
    assert VEHICULOS_COLS.issubset(set(veh.columns))
    # Tamano coherente.
    assert len(ped) == size, f"esperados {size} clientes, hay {len(ped)}"
    assert caso["metadata"]["n_clientes"] == size
    # Multi-vehiculo y deposito unico.
    assert len(veh) > 1, "debe ser multi-vehiculo"
    assert set(ped["zona"].unique()) == {ad.ZONA_BENCHMARK}
    assert "ALMACEN" in set(caso["matriz_tiempos"]["origen"])


@pytest.mark.parametrize("size", [50, 100, 200])
def test_validaciones_de_integridad(size):
    uid = _uid_por_tamano(size)
    if uid is None:
        pytest.skip(f"No hay instancia de {size}.")
    caso = ad.adaptar_instancia(uid, escribir_archivos=False)
    ped, veh = caso["pedidos"], caso["vehiculos"]
    assert (ped["peso_kg"] >= 0).all(), "no debe haber demandas negativas"
    assert not ped[["latitud", "longitud"]].isnull().any().any(), "todo cliente con coordenadas"
    assert (veh["capacidad_kg"] > 0).all(), "todo vehiculo con capacidad"
    assert (ped["ventana_inicio"].apply(hhmm_to_minutes)
            < ped["ventana_fin"].apply(hhmm_to_minutes)).all(), "ventanas validas"
    # Factibilidad gruesa.
    assert float(veh["capacidad_kg"].sum()) >= float(ped["peso_kg"].sum())


def test_archivos_de_caso_generados():
    uid = _uid_por_tamano(50)
    ad.adaptar_instancia(uid, escribir_archivos=True)
    cdir = ad.CASES_DIR / uid
    for f in ("pedidos_benchmark.csv", "vehiculos_benchmark.csv",
              "matriz_tiempos_benchmark.csv", "parametros_benchmark.csv",
              "metadata_benchmark.json"):
        assert (cdir / f).exists(), f"falta {f}"


def test_instancia_no_encontrada():
    with pytest.raises(ad.AdapterError):
        ad.adaptar_instancia("no_existe__999", escribir_archivos=False)


def test_corrida_minima_optimizador():
    """Corrida MINIMA del optimizador actual del DSS sobre una instancia de 50 clientes."""
    uid = _uid_por_tamano(50)
    if uid is None:
        pytest.skip("Sin instancia de 50.")
    pedidos, vehiculos = ad.cargar_para_optimizador(uid)

    from optimization.route_optimizer import construir_rutas_iniciales
    rutas = construir_rutas_iniciales(pedidos, vehiculos, motor="greedy")

    # Todas las paradas asignadas, ningun pedido duplicado entre vehiculos.
    asignados = [pid for r in rutas.values() for pid in r.secuencia]
    assert len(asignados) == len(pedidos), "todos los clientes deben quedar asignados"
    assert len(set(asignados)) == len(asignados), "ningun cliente en dos vehiculos"
    # Respeta capacidad_kg por vehiculo.
    peso = dict(zip(pedidos["pedido_id"], pedidos["peso_kg"]))
    cap = dict(zip(vehiculos["vehiculo_id"], vehiculos["capacidad_kg"]))
    for vid, r in rutas.items():
        carga = sum(peso[p] for p in r.secuencia)
        assert carga <= cap[vid] + 1e-6, f"{vid} excede capacidad ({carga:.0f} > {cap[vid]:.0f})"


def _run_standalone():
    print("=" * 60)
    print("PRUEBA STANDALONE - Adaptador SVRPBench (Fase 5)")
    print("=" * 60)
    for size in (50, 100, 200):
        uid = _uid_por_tamano(size)
        if uid is None:
            print(f"  [skip] sin instancia de {size}")
            continue
        caso = ad.adaptar_instancia(uid, escribir_archivos=True)
        print(f"  [{size:>3}] {uid}: {len(caso['pedidos'])} clientes, "
              f"{len(caso['vehiculos'])} vehiculos, "
              f"demanda={caso['metadata']['demanda_total']:.0f}, "
              f"cap_total={caso['metadata']['capacidad_total']:.0f}")
    # Corrida minima
    uid50 = _uid_por_tamano(50)
    pedidos, vehiculos = ad.cargar_para_optimizador(uid50)
    from optimization.route_optimizer import construir_rutas_iniciales
    rutas = construir_rutas_iniciales(pedidos, vehiculos, motor="greedy")
    usados = sum(1 for r in rutas.values() if r.secuencia)
    asignados = sum(len(r.secuencia) for r in rutas.values())
    print(f"\n  Corrida minima (greedy) sobre {uid50}: "
          f"{asignados}/{len(pedidos)} clientes asignados en {usados} vehiculos.")
    print("  OK." if asignados == len(pedidos) else "  ADVERTENCIA: faltan asignaciones.")


if __name__ == "__main__":
    _run_standalone()
