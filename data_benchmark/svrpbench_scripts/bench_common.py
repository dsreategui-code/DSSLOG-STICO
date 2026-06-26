"""Utilidades comunes y reutilizables para el benchmark SVRPBench.

Estas funciones son agnosticas del dataset (no contienen logica de ALM RRC). Se
adaptaron de la infraestructura del benchmark anterior para conservar lo reutilizable:
exportacion consolidada a CSV/XLSX y agregacion de resultados.

El pipeline previsto de SVRPBench (a implementar en este mismo paquete) es:

    svrpbench_loader.py     ->  carga instancias desde svrpbench_raw/ o svrpbench/
    svrpbench_adapter.py    ->  convierte cada instancia al formato interno del DSS
                                (pedidos, vehiculos, ventanas, congestion, etc.)
    svrpbench_runner.py     ->  ejecuta el optimizador/simulador del DSS por instancia
    svrpbench_metrics.py    ->  indicadores OPERATIVOS (no de similitud de secuencia):
                                OTD, retraso medio/p90, % fuera de ventana, impacto de
                                congestion/accidentes, robustez ante incertidumbre, etc.
    bench_common.py         ->  (este modulo) export + agregacion compartidos.

Ubicacion de datos (se crean si no existen):
    svrpbench_raw/        instancias originales descargadas de SVRPBench
    svrpbench/           instancias normalizadas listas para adaptar
    svrpbench_processed/ artefactos intermedios (matrices, ventanas, escenarios)
    svrpbench_results/   salidas consolidadas (CSV / XLSX)
"""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


# Raiz = data_benchmark/ (este archivo vive en data_benchmark/svrpbench_scripts/).
BENCH_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = BENCH_ROOT / "svrpbench_raw"
INSTANCES_DIR = BENCH_ROOT / "svrpbench"
PROCESSED_DIR = BENCH_ROOT / "svrpbench_processed"
RESULTS_DIR = BENCH_ROOT / "svrpbench_results"

for _d in (RAW_DIR, INSTANCES_DIR, PROCESSED_DIR, RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def exportar_resultados(df: pd.DataFrame, prefijo: str = "svrpbench",
                        resumen: Optional[Dict] = None) -> Dict[str, Optional[Path]]:
    """Guarda resultados consolidados en CSV y XLSX dentro de svrpbench_results/.

    Args:
        df: tabla de resultados (una fila por instancia/corrida).
        prefijo: prefijo del nombre de archivo.
        resumen: dict opcional de metricas agregadas (va a una hoja "Resumen").

    Devuelve {"csv": Path, "xlsx": Path|None}.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = RESULTS_DIR / f"{prefijo}_{ts}.csv"
    xlsx_path = RESULTS_DIR / f"{prefijo}_{ts}.xlsx"

    df.to_csv(csv_path, index=False, encoding="utf-8")

    try:
        with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
            df.to_excel(writer, sheet_name="Detalle", index=False)
            if resumen:
                pd.DataFrame([resumen]).to_excel(writer, sheet_name="Resumen", index=False)
    except Exception:
        xlsx_path = None  # sin xlsxwriter/openpyxl: el CSV sigue disponible

    return {"csv": csv_path, "xlsx": xlsx_path}


def resumen_promedios(filas: List[Dict], columnas: List[str],
                      decimales: int = 3) -> Dict:
    """Promedia las columnas indicadas sobre las filas validas (status == 'ok')."""
    ok = [f for f in filas if f.get("status", "ok") == "ok"]
    if not ok:
        return {}
    out = {"instancias_evaluadas": len(ok)}
    for col in columnas:
        vals = [f[col] for f in ok if f.get(col) is not None]
        out[f"{col}_promedio"] = round(sum(vals) / len(vals), decimales) if vals else None
    return out
