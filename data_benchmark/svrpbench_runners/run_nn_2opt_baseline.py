# -*- coding: utf-8 -*-
"""Fase 6 - Wrapper baseline 'NN+2opt' (solver 'nn2opt') de la suite SVRPBench.

Entrada/salida comunes (ver _suite_common / svrpbench_metrics). Si el solver no esta
disponible, devuelve la salida con error_message (no rompe el runner).
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _suite_common as SC
import svrpbench_metrics as M

SOLVER_ID = "nn2opt"
MODEL_NAME = "NN+2opt"


def disponible() -> bool:
    return SC.solver_disponible(SOLVER_ID)


def run(inst: "M.CanonicalInstance", run_id=0, num_realizations: int = 1) -> dict:
    return SC.run_suite_solver(SOLVER_ID, MODEL_NAME, inst, run_id, num_realizations)


if __name__ == "__main__":
    import json
    print("disponible:", disponible())
    inst = M.cargar_instancia_canonica("twvrp_50_single_depot__0")
    out = run(inst, run_id=0)
    out.pop("_detalle", None)
    print(json.dumps(out, indent=2, ensure_ascii=False))
