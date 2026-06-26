# -*- coding: utf-8 -*-
"""Fase 6 - Pegamento comun para ejecutar baselines de la suite SVRPBench.

Construye una `Instance` de la suite a partir de la instancia canonica, ejecuta el
solver registrado y devuelve la salida comun (puntuada con `svrpbench_metrics` para
que TODOS los modelos se midan igual). No modifica la suite ni el DSS.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

RUNNERS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = RUNNERS_DIR.parent.parent
SUITE_DIR = RUNNERS_DIR.parent / "svrpbench_evaluation_suite"
for p in (str(PROJECT_ROOT), str(RUNNERS_DIR), str(SUITE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import svrpbench_metrics as M


def suite_disponible() -> tuple:
    """(disponible: bool, detalle: str). Verifica que la suite importe y registre solvers."""
    if not SUITE_DIR.exists():
        return False, f"No existe la suite en {SUITE_DIR} (clonar en Fase 2)."
    try:
        from vrp_bench.core import list_solvers
        return True, f"solvers: {list_solvers()}"
    except Exception as e:  # noqa: BLE001
        return False, f"suite no importable: {type(e).__name__}: {e}"


def solver_disponible(solver_id: str) -> bool:
    ok, _ = suite_disponible()
    if not ok:
        return False
    from vrp_bench.core import list_solvers
    return solver_id in list_solvers()


def _instancia_suite(inst: "M.CanonicalInstance"):
    from vrp_bench.core import Instance
    return Instance(
        locations=np.asarray(inst.coords, dtype=float),
        demands=np.asarray(inst.demands, dtype=float),
        vehicle_capacities=np.asarray(inst.capacities, dtype=float),
        num_vehicles=int(inst.num_vehicles),
        time_windows=(np.asarray(inst.time_windows, dtype=float)
                      if inst.time_windows is not None else None),
    )


def solve_suite_routes(solver_id: str, inst: "M.CanonicalInstance",
                       num_realizations: int = 1):
    """Optimiza UNA vez con un solver de la suite. Devuelve (rutas, runtime, error)."""
    ok, detalle = suite_disponible()
    if not ok:
        return None, 0.0, f"suite no disponible: {detalle}"
    if not solver_disponible(solver_id):
        return None, 0.0, f"solver '{solver_id}' no registrado"
    try:
        from vrp_bench.core import get_solver
        solver = get_solver(solver_id)()
        suite_inst = _instancia_suite(inst)
        t0 = time.perf_counter()
        solution = solver.solve(suite_inst, num_realizations=num_realizations)
        runtime = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"ejecucion fallida: {type(e).__name__}: {e}"
    routes = getattr(solution, "routes", None) or []
    return M.normalizar_rutas(routes, inst.n_customers), runtime, ""


def run_suite_solver(solver_id: str, model_name: str, inst: "M.CanonicalInstance",
                     run_id=0, num_realizations: int = 1, scenario=None) -> dict:
    """Ejecuta un solver de la suite y devuelve la salida comun (instruccion 16)."""
    rutas_cliente, runtime, err = solve_suite_routes(solver_id, inst, num_realizations)
    if err:
        return M.construir_salida(model_name, inst, run_id, None, 0.0, error_message=err)
    return M.construir_salida(model_name, inst, run_id, rutas_cliente, runtime,
                              scenario=scenario)
