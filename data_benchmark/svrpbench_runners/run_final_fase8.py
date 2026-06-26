# -*- coding: utf-8 -*-
"""Fase 8 - Runner del BENCHMARK FINAL de SVRPBench.

Ejecuta DSS + baselines aprobados (OR-Tools, NN+2opt) sobre TODAS las instancias del
subconjunto (30: 10x50, 10x100, 10x200), con 5 realizaciones estocasticas por instancia.

Diseno: cada modelo OPTIMIZA UNA vez por instancia (deterministico) y la solucion se
EVALUA bajo 5 escenarios estocasticos COMPARTIDOS y semillados (mismos multiplicadores
de arco para todos los modelos) -> robustness = desv. estandar del costo entre escenarios.
Asi se completa la metrica de robustez del protocolo de forma justa, reproducible y
eficiente, sin re-optimizar 5 veces ni modificar el DSS.

No toca `data/` ni la logica del DSS. Guarda detalle, agregados, ranking, fallidos,
infactibles, logs y un resumen automatico.

Uso:
    python data_benchmark/svrpbench_runners/run_final_fase8.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

RUNNERS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = RUNNERS_DIR.parent.parent
for p in (str(PROJECT_ROOT), str(RUNNERS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd

import svrpbench_metrics as M
import run_dss_model
import _suite_common as SC

CONFIG_PATH = RUNNERS_DIR.parent / "svrpbench_processed" / "benchmark_execution_config.json"
FINAL_DIR = PROJECT_ROOT / "data_benchmark" / "svrpbench_results" / "final"
LOGS_DIR = PROJECT_ROOT / "data_benchmark" / "svrpbench_logs"
SELECTED = RUNNERS_DIR.parent / "svrpbench_processed" / "selected_instances.csv"

# Modelos aprobados tras la Fase 7 (pilot: 0 fallos).
MODELOS = ["DSS", "or-tools", "nn2opt"]
N_REALIZACIONES = 5
DSS_TIME_LIMIT = 10


def _solve(model: str, inst):
    if model == "DSS":
        return run_dss_model.solve_routes(inst, motor="auto", time_limit_seconds=DSS_TIME_LIMIT)
    solver_id = "or-tools" if model == "or-tools" else model
    return SC.solve_suite_routes(solver_id, inst, num_realizations=1)


def ejecutar():
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"benchmark_final_{ts}.log"

    instancias = pd.read_csv(SELECTED)["instance_uid"].tolist()
    print(f"Instancias: {len(instancias)} | Modelos: {MODELOS} | "
          f"Realizaciones: {N_REALIZACIONES}")
    print(f"Total corridas: {len(instancias) * len(MODELOS) * N_REALIZACIONES}")

    filas = []
    with open(log_path, "w", encoding="utf-8") as logf:
        for uid in instancias:
            try:
                inst = M.cargar_instancia_canonica(uid)
            except Exception as e:  # noqa: BLE001
                logf.write(f"instancia {uid} no cargable: {e}\n")
                continue
            for model in MODELOS:
                rutas, runtime, err = _solve(model, inst)
                for r in range(N_REALIZACIONES):
                    if err:
                        out = M.construir_salida(model, inst, r, None, runtime, error_message=err)
                    else:
                        out = M.construir_salida(model, inst, r, rutas, runtime, scenario=r)
                    out.pop("_detalle", None)
                    out["robustness_inputs"] = json.dumps(out.get("robustness_inputs"))
                    filas.append(out)
                logf.write(f"[{datetime.now().isoformat(timespec='seconds')}] {model} | "
                           f"{uid} | {'ERROR:'+err if err else 'OK'} | rt={runtime:.2f}s\n")
                logf.flush()
                # JSON por (modelo, instancia) con las 5 realizaciones.
                (FINAL_DIR / f"{model}__{uid}.json").write_text(
                    json.dumps([f for f in filas[-N_REALIZACIONES:]],
                               ensure_ascii=False, indent=2), encoding="utf-8")

    df = pd.DataFrame(filas)
    cols = [c for c in M.COLUMNAS_RESULTADO if c in df.columns]
    df = df[cols]
    return df, log_path


# --------------------------------------------------------------------------- #
# Agregaciones
# --------------------------------------------------------------------------- #
_METRICAS_PROM = ["runtime_seconds", "feasibility", "constraint_violation_rate",
                  "otd_benchmark", "time_window_violations", "vehicle_utilization",
                  "demand_fulfillment"]


def _robustez_por(df, keys):
    """Robustez = std del total_cost entre realizaciones, por (keys + instancia),
    luego promediada sobre instancias."""
    gk = list(keys) if "instance_id" in keys else list(keys) + ["instance_id"]
    per_inst = (df.groupby(gk)["total_cost"]
                  .std(ddof=0).reset_index(name="robustez_inst"))
    return per_inst.groupby(keys)["robustez_inst"].mean().reset_index(name="robustness")


def _conteos_status(df, keys):
    piv = (df.groupby(keys)["status"].value_counts().unstack(fill_value=0)
             .reset_index())
    for c in ("success", "failed", "infeasible", "timeout"):
        if c not in piv.columns:
            piv[c] = 0
    piv = piv.rename(columns={"success": "n_exitosas", "failed": "n_fallidas",
                              "infeasible": "n_infactibles", "timeout": "n_timeouts"})
    return piv[keys + ["n_exitosas", "n_fallidas", "n_infactibles", "n_timeouts"]]


def _agregar(df, keys):
    ok = df[df["status"] != "failed"].copy()
    g = ok.groupby(keys)
    agg = g["total_cost"].agg(costo_prom="mean", costo_min="min", costo_max="max",
                              costo_std=lambda s: float(np.std(s, ddof=0))).reset_index()
    proms = g[_METRICAS_PROM].mean().reset_index()
    agg = agg.merge(proms, on=keys)
    agg = agg.merge(_robustez_por(ok, keys), on=keys, how="left")
    agg = agg.merge(_conteos_status(df, keys), on=keys, how="left")
    redondear = (["costo_prom", "costo_min", "costo_max", "costo_std", "robustness"]
                 + _METRICAS_PROM)
    for c in redondear:
        if c in agg.columns:
            agg[c] = agg[c].round(4)
    return agg


def construir_agregados(df):
    by_model = _agregar(df, ["model_name"])
    by_size = _agregar(df, ["instance_size"])
    by_model_size = _agregar(df, ["model_name", "instance_size"])
    by_instance = _agregar(df, ["model_name", "instance_id", "instance_size"])

    # Ranking por modelo: costo asc, feasibility desc, cvr asc, otd desc, runtime asc.
    rk = by_model.copy()
    rk = rk.sort_values(
        by=["costo_prom", "feasibility", "constraint_violation_rate",
            "otd_benchmark", "runtime_seconds"],
        ascending=[True, False, True, False, True]).reset_index(drop=True)
    rk.insert(0, "rank", range(1, len(rk) + 1))
    return by_model, by_size, by_model_size, by_instance, rk


def main():
    t0 = time.perf_counter()
    df, log_path = ejecutar()

    df.to_csv(FINAL_DIR / "final_results_detailed.csv", index=False, encoding="utf-8")
    _exportar_xlsx(df, FINAL_DIR / "final_results_detailed.xlsx")

    by_model, by_size, by_model_size, by_instance, ranking = construir_agregados(df)
    by_model.to_csv(FINAL_DIR / "final_results_by_model.csv", index=False, encoding="utf-8")
    by_size.to_csv(FINAL_DIR / "final_results_by_size.csv", index=False, encoding="utf-8")
    by_model_size.to_csv(FINAL_DIR / "final_results_by_model_size.csv", index=False, encoding="utf-8")
    by_instance.to_csv(FINAL_DIR / "final_results_by_instance.csv", index=False, encoding="utf-8")
    ranking.to_csv(FINAL_DIR / "final_model_ranking.csv", index=False, encoding="utf-8")

    df[df["status"] == "failed"].to_csv(FINAL_DIR / "final_failed_runs.csv", index=False, encoding="utf-8")
    df[df["status"] == "infeasible"].to_csv(FINAL_DIR / "final_infeasible_runs.csv", index=False, encoding="utf-8")

    _resumen_auto(df, by_model, ranking)

    dur = time.perf_counter() - t0
    print(f"\n[OK] {len(df)} filas | {dur:.0f}s | log: {log_path.name}")
    print(f"Resultados -> {FINAL_DIR}")
    return 0


def _exportar_xlsx(df, path):
    """Exporta a .xlsx probando motores disponibles (xlsxwriter -> openpyxl)."""
    for engine in ("xlsxwriter", "openpyxl"):
        try:
            with pd.ExcelWriter(path, engine=engine) as w:
                df.to_excel(w, sheet_name="detalle", index=False)
            return
        except Exception:  # noqa: BLE001
            continue
    print("(xlsx no generado: ni xlsxwriter ni openpyxl disponibles)")


def _md_table(df) -> str:
    """Tabla markdown autocontenida (sin depender de `tabulate`)."""
    cols = [str(c) for c in df.columns]
    filas = [[("" if pd.isna(v) else str(v)) for v in row] for row in df.itertuples(index=False)]
    lineas = ["| " + " | ".join(cols) + " |",
              "| " + " | ".join("---" for _ in cols) + " |"]
    lineas += ["| " + " | ".join(r) + " |" for r in filas]
    return "\n".join(lineas)


def _resumen_auto(df, by_model, ranking):
    n_inst = df["instance_id"].nunique()
    n_runs = len(df)
    modelos = sorted(df["model_name"].unique())
    tamanos = sorted(df["instance_size"].unique())
    mejor_costo = by_model.sort_values("costo_prom").iloc[0]["model_name"]
    mejor_feas = by_model.sort_values("feasibility", ascending=False).iloc[0]["model_name"]
    mejor_otd = by_model.sort_values("otd_benchmark", ascending=False).iloc[0]["model_name"]
    mejor_rt = by_model.sort_values("runtime_seconds").iloc[0]["model_name"]
    pos_dss = int(ranking[ranking["model_name"] == "DSS"]["rank"].iloc[0]) if "DSS" in set(ranking["model_name"]) else None

    L = [
        "# Resumen ejecutivo - Benchmark final SVRPBench (Fase 8)\n",
        f"- Instancias ejecutadas: **{n_inst}** (tamanos {tamanos}).",
        f"- Corridas totales (modelo x instancia x realizacion): **{n_runs}**.",
        f"- Modelos comparados: **{', '.join(modelos)}**.",
        f"- Tamanos evaluados: **{tamanos}**.",
        f"- Mejor modelo por costo total (menor): **{mejor_costo}**.",
        f"- Mejor modelo por factibilidad: **{mejor_feas}**.",
        f"- Mejor modelo por OTD benchmark: **{mejor_otd}**.",
        f"- Mejor modelo por runtime (menor): **{mejor_rt}**.",
        f"- Posicion del DSS en el ranking global: **{pos_dss} de {len(ranking)}**.\n",
        "## Agregado por modelo\n",
        _md_table(by_model[["model_name", "costo_prom", "robustness", "runtime_seconds",
                  "feasibility", "constraint_violation_rate", "otd_benchmark",
                  "vehicle_utilization", "demand_fulfillment",
                  "n_exitosas", "n_fallidas", "n_infactibles"]]),
        "\n## Ranking\n",
        _md_table(ranking[["rank", "model_name", "costo_prom", "feasibility",
                 "constraint_violation_rate", "otd_benchmark", "runtime_seconds"]]),
    ]
    (FINAL_DIR / "svrpbench_benchmark_final_resumen.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
