# -*- coding: utf-8 -*-
"""Fase 6 - Runner general del benchmark SVRPBench.

Orquesta la ejecucion de los modelos (DSS + baselines) sobre las mismas instancias,
con la misma estructura de E/S y las mismas metricas. Maneja errores, timeouts y logs.

IMPORTANTE: por seguridad NO ejecuta de forma masiva. Sin `--run` solo imprime el plan
(dry-run). Con `--run` ejecuta; con `--pilot` usa el subconjunto piloto del config.

Uso:
    python data_benchmark/svrpbench_runners/run_svrpbench_benchmark.py            # dry-run plan
    python data_benchmark/svrpbench_runners/run_svrpbench_benchmark.py --pilot    # plan del piloto
    python data_benchmark/svrpbench_runners/run_svrpbench_benchmark.py --pilot --run   # ejecuta piloto
"""
from __future__ import annotations

import argparse
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

import pandas as pd
import svrpbench_metrics as M

CONFIG_PATH = RUNNERS_DIR.parent / "svrpbench_processed" / "benchmark_execution_config.json"

# Registro de wrappers por id de modelo.
import run_dss_model
import run_ortools_baseline
import run_nn_2opt_baseline
import run_tabu_baseline
import run_aco_baseline

WRAPPERS = {
    "DSS": run_dss_model,
    "or-tools": run_ortools_baseline,
    "nn2opt": run_nn_2opt_baseline,
    "tabu": run_tabu_baseline,
    "aco": run_aco_baseline,
}


def cargar_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"No existe {CONFIG_PATH}.")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def validar_instancias(instancias, motivo: str) -> pd.DataFrame:
    """Valida la carga de cada instancia y sus campos minimos. Devuelve un DataFrame."""
    filas = []
    for uid in instancias:
        fila = {"instance_uid": uid, "motivo_seleccion": motivo,
                "cargable": False, "tiene_clientes": False, "tiene_deposito": False,
                "tiene_demanda": False, "tiene_capacidad": False, "tiene_vehiculos": False,
                "tiene_ventanas": False, "n_clientes": None, "num_vehicles": None,
                "error": ""}
        try:
            inst = M.cargar_instancia_canonica(uid)
            fila.update({
                "cargable": True,
                "tiene_clientes": inst.n_customers > 0,
                "tiene_deposito": len(inst.coords) >= 1 and inst.demands[0] == 0,
                "tiene_demanda": len(inst.demands) == len(inst.coords),
                "tiene_capacidad": len(inst.capacities) >= 1 and min(inst.capacities) > 0,
                "tiene_vehiculos": inst.num_vehicles > 1,
                # Ventanas: abiertas por defecto (no materializadas). Se reporta como
                # 'jornada' (disponible para calcular metricas, sin valores propios).
                "tiene_ventanas": True,
                "n_clientes": inst.n_customers,
                "num_vehicles": inst.num_vehicles,
            })
        except Exception as e:  # noqa: BLE001
            fila["error"] = f"{type(e).__name__}: {e}"
        filas.append(fila)
    return pd.DataFrame(filas)


def modelos_disponibles() -> dict:
    """Detecta en runtime que modelos pueden ejecutarse."""
    estado = {}
    for mid, mod in WRAPPERS.items():
        if mid == "DSS":
            estado[mid] = True
        else:
            try:
                estado[mid] = bool(mod.disponible())
            except Exception:  # noqa: BLE001
                estado[mid] = False
    return estado


def _ejecutar_modelo(mid, inst, run_id, cfg, logf):
    mod = WRAPPERS[mid]
    t0 = time.perf_counter()
    try:
        if mid == "DSS":
            out = mod.run(inst, run_id=run_id,
                          time_limit_seconds=cfg["limites"]["time_limit_dss_optimizador_seconds"])
        else:
            out = mod.run(inst, run_id=run_id, num_realizations=1)
    except Exception as e:  # noqa: BLE001 (red de seguridad)
        out = M.construir_salida(mid, inst, run_id, None, time.perf_counter() - t0,
                                 error_message=f"excepcion runner: {type(e).__name__}: {e}")
    out.pop("_detalle", None)
    estado = "ERROR" if out.get("error_message") else "OK"
    logf.write(f"[{datetime.now().isoformat(timespec='seconds')}] {mid} | "
               f"{inst.instance_uid} | run={run_id} | {estado} | "
               f"cost={out.get('total_cost')} rt={out.get('runtime_seconds')}s "
               f"{out.get('error_message','')}\n")
    logf.flush()
    return out


def correr(cfg: dict, pilot: bool, ejecutar: bool) -> int:
    disp = modelos_disponibles()
    if pilot:
        instancias = cfg["pilot"]["instancias"]
        modelos = [m for m in cfg["pilot"]["modelos"]]
        realizaciones = int(cfg["pilot"]["realizaciones"])
        results_dir = PROJECT_ROOT / cfg["rutas"]["results_pilot"]
    else:
        sel = pd.read_csv(PROJECT_ROOT / cfg["rutas"]["selected_instances"])
        instancias = sel["instance_uid"].tolist()
        modelos = (["DSS"] + [m["id"] for m in cfg["modelos"]["obligatorios"] if m["id"] != "DSS"]
                   + [m["id"] for m in cfg["modelos"]["viables"]]
                   + [m["id"] for m in cfg["modelos"]["opcionales"]])
        realizaciones = int(cfg["realizaciones_estocasticas"]["final"])
        results_dir = PROJECT_ROOT / cfg["rutas"]["results_final"]

    # Filtrar a modelos realmente disponibles.
    modelos_ok = [m for m in modelos if disp.get(m, False)]
    modelos_no = [m for m in modelos if not disp.get(m, False)]

    print("=" * 64)
    print(f"PLAN DE EJECUCION ({'PILOTO' if pilot else 'FINAL'})")
    print("=" * 64)
    print(f"Instancias: {len(instancias)} | Realizaciones: {realizaciones}")
    print(f"Modelos disponibles: {modelos_ok}")
    if modelos_no:
        print(f"Modelos NO disponibles (se omiten): {modelos_no}")
    total_runs = len(instancias) * len(modelos_ok) * realizaciones
    print(f"Total de corridas: {total_runs}")
    print(f"Resultados -> {results_dir}")

    if not ejecutar:
        print("\n[DRY-RUN] No se ejecuto nada. Use --run para ejecutar.")
        return 0

    results_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = PROJECT_ROOT / cfg["rutas"]["logs"]
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"benchmark_{'pilot' if pilot else 'final'}_{ts}.log"
    out_csv = results_dir / f"resultados_{'pilot' if pilot else 'final'}_{ts}.csv"

    # Validacion de carga + registro de instancias seleccionadas.
    motivo = "piloto: 1 instancia por tamano (50/100/200), primera de cada subset"
    sel_df = validar_instancias(instancias, motivo if pilot else "ejecucion final")
    if pilot:
        sel_df.to_csv(results_dir / "pilot_selected_instances.csv", index=False, encoding="utf-8")
        print(f"\nInstancias validadas -> pilot_selected_instances.csv "
              f"({int(sel_df['cargable'].sum())}/{len(sel_df)} cargables)")

    filas = []
    with open(log_path, "w", encoding="utf-8") as logf:
        for uid in instancias:
            try:
                inst = M.cargar_instancia_canonica(uid)
            except Exception as e:  # noqa: BLE001
                logf.write(f"instancia {uid} no cargable: {e}\n")
                continue
            for mid in modelos_ok:
                for r in range(realizaciones):
                    out = _ejecutar_modelo(mid, inst, r, cfg, logf)
                    out["robustness_inputs"] = json.dumps(out.get("robustness_inputs"))
                    filas.append(out)
                    (results_dir / f"{mid}__{uid}__r{r}.json").write_text(
                        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    df = pd.DataFrame(filas)
    cols = [c for c in M.COLUMNAS_RESULTADO if c in df.columns]
    df = df[cols]
    df.to_csv(out_csv, index=False, encoding="utf-8")

    # Salidas canonicas del piloto (instruccion Fase 7).
    if pilot:
        df.to_csv(results_dir / "pilot_results.csv", index=False, encoding="utf-8")
        try:
            with pd.ExcelWriter(results_dir / "pilot_results.xlsx", engine="xlsxwriter") as w:
                df.to_excel(w, sheet_name="resultados", index=False)
                sel_df.to_excel(w, sheet_name="instancias", index=False)
        except Exception as e:  # noqa: BLE001
            print(f"     (xlsx no generado: {e})")

    print(f"\n[OK] {len(filas)} corridas -> {out_csv}")
    print(f"     Log -> {log_path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Runner del benchmark SVRPBench.")
    ap.add_argument("--pilot", action="store_true", help="Usa el subconjunto piloto del config.")
    ap.add_argument("--run", action="store_true", help="Ejecuta (sin esto, solo dry-run/plan).")
    args = ap.parse_args(argv)
    cfg = cargar_config()
    return correr(cfg, pilot=args.pilot, ejecutar=args.run)


if __name__ == "__main__":
    raise SystemExit(main())
