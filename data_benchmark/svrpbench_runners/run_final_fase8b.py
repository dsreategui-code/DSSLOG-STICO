# -*- coding: utf-8 -*-
"""Fase 8b - BENCHMARK FINAL FIEL (TWCVRP real) de SVRPBench.

Reconstruccion fiel al paper (arXiv:2505.21887): capacidad multi-vehiculo real
(`ceil(total/num_veh)`), ventanas por cliente (generador oficial de la suite) y
PUNTUACION con el evaluador autoritativo de la suite (modelo estocastico del paper:
congestion + log-normal + accidentes). Decisiones metodologicas (acordadas con el usuario):

  - COBERTURA TOTAL: todos los modelos sirven a TODOS los clientes. Los clientes que el
    DSS no puede encajar dentro de la ventana estricta se sirven con viajes DEDICADOS
    (despachador de respaldo), cuyo coste se carga al DSS (ver `svrpbench_faithful`).
  - FLOTA HOLGADA E IGUAL: ningun modelo se limita a `num_vehicles`; la suite ya usa
    flota efectivamente ilimitada, y al DSS se le da holgura (factor 2). El cuello de
    botella son ventanas y capacidad, no el numero de vehiculos.

Diseno: cada modelo optimiza UNA vez por instancia; la solucion se evalua bajo 5
escenarios estocasticos COMPARTIDOS y semillados (mismo ruido para todos). Robustez =
std del costo entre escenarios.

No toca `data/` ni la logica del DSS. Escribe en `svrpbench_results/final_twcvrp/`.
"""
from __future__ import annotations

import json
import sys
import time
import zlib
from datetime import datetime
from pathlib import Path

RUNNERS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = RUNNERS_DIR.parent.parent
for p in (str(PROJECT_ROOT), str(RUNNERS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd

import svrpbench_faithful as F
import run_final_fase8 as AGG          # reutiliza agregacion / md / xlsx

SELECTED = RUNNERS_DIR.parent / "svrpbench_processed" / "selected_instances.csv"
OUT_DIR = PROJECT_ROOT / "data_benchmark" / "svrpbench_results" / "final_twcvrp"
LOGS_DIR = PROJECT_ROOT / "data_benchmark" / "svrpbench_logs"

MODELOS = ["DSS", "or-tools-tw", "or-tools", "nn2opt"]
N_REALIZACIONES = 5
# Rec #2: presupuesto de busqueda escalado por tamano para los solvers OR-Tools (DSS y
# or-tools-tw). Las instancias mayores necesitan mas tiempo para refinar el costo.
TIME_BY_SIZE = {50: 8, 100: 12, 200: 16}


def _time_limit(fiel: dict) -> int:
    return TIME_BY_SIZE.get(int(fiel["size"]), 15)


def _seed(uid: str, r: int) -> int:
    return zlib.crc32(f"{uid}|{r}".encode("utf-8")) & 0xFFFFFFFF


def _solve(model: str, fiel: dict):
    """Devuelve (rutas_nodos, runtime, error, n_reparadas)."""
    if model == "DSS":
        return F.solve_dss(fiel, time_limit_seconds=_time_limit(fiel), slack_minutos=0)
    if model == "or-tools-tw":
        return F.solve_ortools_tw(fiel, time_limit_seconds=_time_limit(fiel))
    rutas, rt, err = F.solve_suite(model, fiel)
    return rutas, rt, err, 0


def _fila(model, fiel, run_id, m, runtime, nrep, err=""):
    n = fiel["n_customers"]
    cap = fiel["cap_por_vehiculo"]
    util = round(fiel["total_demand"] / max(m["n_rutas"] * cap, 1), 4) if m else None
    return {
        "model_name": model,
        "instance_id": fiel["uid"],
        "instance_size": fiel["size"],
        "problem_type": "TWCVRP",
        "depot_type": "single_depot",
        "vehicle_type": "multi_vehicle",
        "run_id": run_id,
        "total_cost": m["total_cost"] if m else None,
        "total_distance": m["total_distance"] if m else None,
        "runtime_seconds": round(float(runtime), 4),
        "feasibility": m["feasibility"] if m else None,
        "constraint_violation_rate": m["cvr"] if m else None,
        "time_window_violations": m["time_window_violations"] if m else None,
        "otd_benchmark": m["otd"] if m else None,
        "vehicle_utilization": util,
        "demand_fulfillment": 1.0 if m else None,     # cobertura total garantizada
        "n_rutas": m["n_rutas"] if m else None,
        "n_reparadas_dedicadas": nrep,
        "error_message": err,
        "status": "failed" if err else "success",
    }


def ejecutar():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"benchmark_twcvrp_{ts}.log"

    uids = pd.read_csv(SELECTED)["instance_uid"].tolist()
    print(f"Instancias: {len(uids)} | Modelos: {MODELOS} | Realizaciones: {N_REALIZACIONES}")
    print(f"Total corridas: {len(uids) * len(MODELOS) * N_REALIZACIONES}")

    filas = []
    with open(log_path, "w", encoding="utf-8") as logf:
        for uid in uids:
            try:
                fiel = F.instancia_fiel(uid)
            except Exception as e:  # noqa: BLE001
                logf.write(f"instancia {uid} no cargable: {e}\n")
                continue
            for model in MODELOS:
                rutas, runtime, err, nrep = _solve(model, fiel)
                if err:
                    for r in range(N_REALIZACIONES):
                        filas.append(_fila(model, fiel, r, None, runtime, nrep, err))
                else:
                    for r in range(N_REALIZACIONES):
                        m = F.score_rutas(fiel, rutas, num_realizations=1, seed=_seed(uid, r))
                        filas.append(_fila(model, fiel, r, m, runtime, nrep))
                logf.write(f"[{datetime.now().isoformat(timespec='seconds')}] {model} | {uid} | "
                           f"{'ERROR:'+err if err else 'OK'} | rt={runtime:.2f}s | reparadas={nrep}\n")
                logf.flush()

    df = pd.DataFrame(filas)
    return df, log_path


def main():
    t0 = time.perf_counter()
    df, log_path = ejecutar()

    df.to_csv(OUT_DIR / "twcvrp_results_detailed.csv", index=False, encoding="utf-8")
    AGG._exportar_xlsx(df, OUT_DIR / "twcvrp_results_detailed.xlsx")

    by_model, by_size, by_model_size, by_instance, ranking = AGG.construir_agregados(df)
    by_model.to_csv(OUT_DIR / "twcvrp_results_by_model.csv", index=False, encoding="utf-8")
    by_size.to_csv(OUT_DIR / "twcvrp_results_by_size.csv", index=False, encoding="utf-8")
    by_model_size.to_csv(OUT_DIR / "twcvrp_results_by_model_size.csv", index=False, encoding="utf-8")
    by_instance.to_csv(OUT_DIR / "twcvrp_results_by_instance.csv", index=False, encoding="utf-8")
    ranking.to_csv(OUT_DIR / "twcvrp_model_ranking.csv", index=False, encoding="utf-8")
    df[df["status"] == "failed"].to_csv(OUT_DIR / "twcvrp_failed_runs.csv", index=False, encoding="utf-8")

    # Reparaciones del DSS (transparencia de la cobertura total).
    rep = (df[df["model_name"] == "DSS"][["instance_id", "instance_size", "n_reparadas_dedicadas"]]
           .drop_duplicates().sort_values("instance_size"))
    rep.to_csv(OUT_DIR / "twcvrp_dss_reparaciones.csv", index=False, encoding="utf-8")

    _resumen(df, by_model, by_model_size, ranking, rep)

    dur = time.perf_counter() - t0
    print(f"\n[OK] {len(df)} filas | {dur:.0f}s | log: {log_path.name}")
    print(f"Resultados -> {OUT_DIR}")
    return 0


def _resumen(df, by_model, by_model_size, ranking, rep):
    cols = ["model_name", "costo_prom", "robustness", "runtime_seconds", "feasibility",
            "constraint_violation_rate", "otd_benchmark", "vehicle_utilization",
            "demand_fulfillment"]
    L = [
        "# Resumen ejecutivo - Benchmark FINAL FIEL TWCVRP (Fase 8b)\n",
        f"- Instancias: **{df['instance_id'].nunique()}** | corridas: **{len(df)}** | "
        f"modelos: **{', '.join(sorted(df['model_name'].unique()))}**.",
        "- Reconstruccion fiel: capacidad real `ceil(total/num_veh)` + ventanas por cliente "
        "(generador oficial, 60/40 res/com) + evaluador estocastico del paper.",
        "- Cobertura total garantizada (demand_fulfillment = 1.0); flota holgada e igual.",
        f"- Reparaciones dedicadas del DSS (clientes no encajables en ventana estricta) "
        f"totales: **{int(rep['n_reparadas_dedicadas'].sum())}** "
        f"(prom/instancia {rep['n_reparadas_dedicadas'].mean():.1f}).\n",
        "## Agregado por modelo\n",
        AGG._md_table(by_model[cols]),
        "\n## Por modelo y tamano\n",
        AGG._md_table(by_model_size[["model_name", "instance_size", "costo_prom",
                                     "otd_benchmark", "constraint_violation_rate",
                                     "robustness", "runtime_seconds"]]),
        "\n## Ranking (menor costo, mayor factibilidad, menor CVR, mayor OTD, menor runtime)\n",
        AGG._md_table(ranking[["rank", "model_name", "costo_prom", "feasibility",
                               "constraint_violation_rate", "otd_benchmark",
                               "runtime_seconds"]]),
    ]
    (OUT_DIR / "svrpbench_benchmark_twcvrp_resumen.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
