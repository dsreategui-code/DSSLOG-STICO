# -*- coding: utf-8 -*-
"""Fase 1 - Descarga del dataset SVRPBench (MBZUAI/svrp-bench) desde Hugging Face.

Guarda el dataset completo en Parquet dentro de svrpbench_raw/, genera una muestra
CSV para inspeccion visual y un .txt con la lista de columnas y tipos.

NO modifica el DSS. NO adapta el dataset. NO ejecuta modelos. Solo descarga y organiza.

Uso:
    python data_benchmark/svrpbench_scripts/download_svrpbench.py
    python data_benchmark/svrpbench_scripts/download_svrpbench.py --force   # re-descarga
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import pandas as pd

# Rutas (este script vive en data_benchmark/svrpbench_scripts/).
SCRIPTS_DIR = Path(__file__).resolve().parent
RAW_DIR = SCRIPTS_DIR.parent / "svrpbench_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

REPO_ID = "MBZUAI/svrp-bench"
PARQUET_OUT = RAW_DIR / "svrpbench_test.parquet"
SAMPLE_CSV = RAW_DIR / "svrpbench_sample.csv"
COLUMNS_TXT = RAW_DIR / "svrpbench_columns.txt"

# Columnas con listas anidadas (se serializan a JSON en el CSV de muestra).
NESTED_COLS = ["locations", "demands", "vehicle_capacities", "appear_times"]


def _to_native(v):
    """Convierte recursivamente arrays/escalares numpy a tipos nativos de Python."""
    if isinstance(v, np.ndarray):
        return [_to_native(x) for x in v.tolist()]
    if isinstance(v, (list, tuple)):
        return [_to_native(x) for x in v]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def descargar_parquet(force: bool = False) -> Path:
    """Descarga el dataset y lo guarda como Parquet en svrpbench_raw/."""
    if PARQUET_OUT.exists() and not force:
        print(f"[=] Ya existe {PARQUET_OUT.name} (usa --force para re-descargar). "
              "No se sobrescribe.")
        return PARQUET_OUT

    print(f"[1] Descargando {REPO_ID} (split 'test') desde Hugging Face...")
    from datasets import load_dataset
    ds = load_dataset(REPO_ID, split="test")
    print(f"    Filas: {ds.num_rows} | Columnas: {len(ds.column_names)}")

    print(f"[2] Guardando Parquet en {PARQUET_OUT}")
    ds.to_parquet(str(PARQUET_OUT))
    return PARQUET_OUT


def _derivar_metadatos(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega columnas derivadas utiles para la inspeccion visual."""
    def _size(s):
        m = re.search(r"_(\d+)_", str(s))
        return int(m.group(1)) if m else None

    def _variant(s):
        s = str(s)
        return "twcvrp" if s.startswith("twvrp_") else ("cvrp" if s.startswith("cvrp_") else "otro")

    def _depot_cfg(s):
        s = str(s)
        if "multi_depot" in s:
            return "multi_depot"
        if "depots_equal_city" in s:
            return "depots_equal_city"
        if "single_depot" in s:
            return "single_depot"
        return "otro"

    out = pd.DataFrame()
    out["subset_name"] = df["subset_name"]
    out["file_name"] = df["file_name"]
    out["instance_id"] = df["instance_id"]
    out["variant"] = df["subset_name"].apply(_variant)
    out["size_declarado"] = df["subset_name"].apply(_size)
    out["depot_config"] = df["subset_name"].apply(_depot_cfg)
    out["n_puntos"] = df["locations"].apply(len)
    out["n_clientes_aprox"] = out["n_puntos"] - 1
    out["num_vehicles"] = df["num_vehicles"]
    out["vehiculo_single_o_multi"] = df["num_vehicles"].apply(
        lambda n: "single" if int(n) == 1 else "multi"
    )
    out["demanda_total"] = df["demands"].apply(lambda d: int(sum(d)))
    out["demanda_max"] = df["demands"].apply(lambda d: int(max(d)) if len(d) else 0)
    out["n_demanda_cero"] = df["demands"].apply(lambda d: int(sum(1 for x in d if x == 0)))
    out["capacidad_total"] = df["vehicle_capacities"].apply(lambda c: float(sum(c)))
    out["appear_times_unicos"] = df["appear_times"].apply(lambda a: len(set(a)))
    out["appear_times_max"] = df["appear_times"].apply(lambda a: int(max(a)) if len(a) else 0)
    return out


def generar_muestra_csv(df: pd.DataFrame) -> None:
    """Muestra estratificada (1 instancia por subset_name) con anidados en JSON."""
    if SAMPLE_CSV.exists():
        print(f"[=] Ya existe {SAMPLE_CSV.name}; se regenera (artefacto de inspeccion).")

    muestra = df.groupby("subset_name", group_keys=False).head(1).reset_index(drop=True)
    meta = _derivar_metadatos(muestra)

    # Serializar campos anidados a JSON (numpy -> tipos nativos via .tolist()).
    for col in NESTED_COLS:
        if col in muestra.columns:
            meta[col + "_json"] = muestra[col].apply(
                lambda v: json.dumps(_to_native(v))
            )

    meta.to_csv(SAMPLE_CSV, index=False, encoding="utf-8")
    print(f"[3] Muestra CSV ({len(meta)} instancias, 1 por subset) -> {SAMPLE_CSV.name}")


def generar_columns_txt(df: pd.DataFrame) -> None:
    """Lista de columnas con tipos y forma del contenido."""
    lineas = ["# Columnas de SVRPBench (split 'test')", ""]
    lineas.append(f"Total de filas: {len(df)}")
    lineas.append(f"Total de columnas: {len(df.columns)}")
    lineas.append("")
    lineas.append("columna | dtype_pandas | ejemplo_resumido")
    lineas.append("-" * 60)
    fila0 = df.iloc[0]
    for col in df.columns:
        val = fila0[col]
        if hasattr(val, "__len__") and not isinstance(val, str):
            ejemplo = f"lista(len={len(val)}) ej={list(val[:2])}"
        else:
            ejemplo = repr(val)
        lineas.append(f"{col} | {df[col].dtype} | {ejemplo}")
    COLUMNS_TXT.write_text("\n".join(lineas), encoding="utf-8")
    print(f"[4] Lista de columnas -> {COLUMNS_TXT.name}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Descarga SVRPBench (Fase 1).")
    ap.add_argument("--force", action="store_true", help="Re-descarga aunque exista el Parquet.")
    args = ap.parse_args(argv)

    parquet = descargar_parquet(force=args.force)
    df = pd.read_parquet(parquet)
    generar_muestra_csv(df)
    generar_columns_txt(df)

    print("\n[OK] Descarga e inventario de Fase 1 completados.")
    print(f"     Parquet : {PARQUET_OUT}")
    print(f"     Muestra : {SAMPLE_CSV}")
    print(f"     Columnas: {COLUMNS_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
