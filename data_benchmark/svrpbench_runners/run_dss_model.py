# -*- coding: utf-8 -*-
"""Fase 6 - Wrapper del DSS como modelo evaluado del benchmark.

Ejecuta el optimizador ACTUAL del DSS sobre una instancia SVRPBench adaptada
(via el adaptador de la Fase 5) y devuelve la estructura de salida comun. NO modifica
el DSS: lo importa como libreria y le entrega DataFrames.

Entrada comun: CanonicalInstance + run_id (semilla/realizacion).
Salida comun: dict de `svrpbench_metrics.construir_salida`.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
RUNNERS_DIR = SCRIPTS_DIR
PROJECT_ROOT = SCRIPTS_DIR.parent.parent
SV_SCRIPTS = SCRIPTS_DIR.parent / "svrpbench_scripts"
for p in (str(PROJECT_ROOT), str(RUNNERS_DIR), str(SV_SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import svrpbench_metrics as M

MODEL_NAME = "DSS"


def _ruta_a_indices(secuencia) -> list:
    """Convierte ['C0001','C0002',...] del DSS a [1, 2, ...] (indices de cliente)."""
    idx = []
    for pid in secuencia:
        s = str(pid)
        digits = "".join(ch for ch in s if ch.isdigit())
        if digits:
            idx.append(int(digits))
    return idx


def solve_routes(inst: "M.CanonicalInstance", motor: str = "auto",
                 time_limit_seconds: int = 10):
    """Optimiza UNA vez con el DSS. Devuelve (rutas_cliente, runtime, error_message)."""
    try:
        import svrpbench_to_dss_adapter as ad
        from optimization.route_optimizer import construir_rutas_iniciales
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"dependencia/adaptador no disponible: {e}"
    try:
        pedidos, vehiculos = ad.cargar_para_optimizador(inst.instance_uid)
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"instancia no adaptable: {e}"
    try:
        t0 = time.perf_counter()
        rutas = construir_rutas_iniciales(
            pedidos, vehiculos, motor=motor, time_limit_seconds=time_limit_seconds,
        )
        runtime = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"ejecucion fallida: {e}"
    rutas_cliente = [
        _ruta_a_indices(r.secuencia)
        for r in rutas.values() if getattr(r, "secuencia", None)
    ]
    return M.normalizar_rutas(rutas_cliente, inst.n_customers), runtime, ""


def run(inst: "M.CanonicalInstance", run_id=0, motor: str = "auto",
        time_limit_seconds: int = 10, scenario=None) -> dict:
    """Corre el DSS sobre la instancia y devuelve la salida comun."""
    rutas_cliente, runtime, err = solve_routes(inst, motor, time_limit_seconds)
    if err:
        return M.construir_salida(MODEL_NAME, inst, run_id, None, 0.0, error_message=err)
    return M.construir_salida(MODEL_NAME, inst, run_id, rutas_cliente, runtime,
                              scenario=scenario)


if __name__ == "__main__":
    import json
    inst = M.cargar_instancia_canonica("twvrp_50_single_depot__0")
    out = run(inst, run_id=0, motor="greedy")
    out.pop("_detalle", None)
    print(json.dumps(out, indent=2, ensure_ascii=False))
