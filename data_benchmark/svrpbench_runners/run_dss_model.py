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


def _modelo_desde_instancia(inst: "M.CanonicalInstance", solver_seg_por_perfil: int):
    """Construye un ModeloNumerico de CORTEX-LM DIRECTO desde la instancia SVRPBench, con la
    MISMA metrica de distancia/velocidad que svrpbench_metrics (para optimizar el mismo costo que
    se puntua) y desactivando el contexto Lima (jornada/overtime/cuadrilla/seguridad/OSRM).

    `solver_seg_por_perfil`: presupuesto de OR-Tools POR perfil. El total (n_perfiles * este valor)
    respeta el time_limit del benchmark, para no dar ventaja injusta ni exceder el cap por instancia."""
    import numpy as np
    from core.optimizer_ortools import ModeloNumerico
    from core.data_models import Parametros

    n = inst.n_customers + 1
    H = int(M.JORNADA_MIN[1] - M.JORNADA_MIN[0])              # horizonte (min) = jornada SVRPBench
    dist = np.zeros((n, n)); tiempo = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                d = inst.dist_km(i, j)                        # euclidea * KM_POR_UNIDAD (identico al scoring)
                dist[i][j] = d
                tiempo[i][j] = d / max(M.VELOCIDAD_KMH, 1.0) * 60.0
    ventanas = []
    for k in range(n):
        ini, fin = inst.ventana(k)                            # min del dia (JORNADA si no hay ventana)
        ventanas.append((max(0, int(ini - M.JORNADA_MIN[0])), min(H, int(fin - M.JORNADA_MIN[0]))))
    servicio = [float(inst.servicio(k)) for k in range(n)]
    modelo = ModeloNumerico(
        tiempo_min=tiempo, dist_km=dist,
        demanda_m3=[float(x) for x in inst.demands], demanda_kg=[0.0] * n,
        ventanas_min=ventanas, servicio_min=servicio,
        pedido_ids=["HUB"] + [f"C{i}" for i in range(1, n)],
        num_vehiculos=int(inst.num_vehicles),
        cap_m3=[float(c) for c in inst.capacities], cap_kg=[0.0] * int(inst.num_vehicles),
        vehiculo_ids=[f"V{i+1}" for i in range(int(inst.num_vehicles))], horizonte_min=H,
    )
    # Params: motor CORTEX-LM (OR-Tools + ALNS) SIN el contexto Lima (comparacion justa).
    params = Parametros(
        tiempo_solver_seg=max(1, int(solver_seg_por_perfil)), usar_alns=True, usar_saa=False,
        jornada_max_min=0, overtime_max_min=0, frac_cuadrillas=0.0,
        usar_seguridad_horaria=False, usar_osrm=False, usar_clima=False, usar_feriados=False,
        semilla_base=42)
    return modelo, params


def solve_routes(inst: "M.CanonicalInstance", motor: str = "auto",
                 time_limit_seconds: int = 10):
    """Optimiza UNA vez con el motor CORTEX-LM (OR-Tools + ALNS). Devuelve
    (rutas_cliente, runtime, error_message)."""
    try:
        from core.candidate_generator import generar_candidatas
        from core.data_models import PERFILES_POR_DEFECTO
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"CORTEX-LM no disponible: {e}"
    try:
        # En SVRPBench determinista (sin contexto Lima), los 5 perfiles de robustez colapsan a la
        # misma solucion: se corre el optimizador NUCLEO (OR-Tools + ALNS) con el perfil "robusta"
        # y el presupuesto COMPLETO. La seleccion multi-perfil/DRO es una feature del caso Lima.
        perfiles = [p for p in PERFILES_POR_DEFECTO if p.perfil == "robusta"] \
            or list(PERFILES_POR_DEFECTO[:1])
        modelo, params = _modelo_desde_instancia(inst, int(time_limit_seconds))
        t0 = time.perf_counter()
        cands = generar_candidatas(modelo, perfiles, params)
        runtime = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"ejecucion fallida: {e}"
    ok = [c for c in cands if c["resultado"].get("status") == "ok" and c["resultado"].get("rutas")]
    if not ok:
        return None, runtime, "sin solucion factible"
    # Mejor candidata: primero cobertura, luego menor distancia (= costo deterministico SVRPBench).
    best = min(ok, key=lambda c: (-c["kpis"]["cobertura"], c["kpis"]["distancia_km"]))
    rutas_cliente = [[s.idx_nodo for s in rc.secuencia]
                     for rc in best["resultado"]["rutas"].values() if rc.secuencia]
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
