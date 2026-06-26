# -*- coding: utf-8 -*-
"""Fase 4 - Construccion del subconjunto procesado de SVRPBench.

Filtra, limpia, valida y guarda UNICAMENTE las instancias que cumplen el protocolo
experimental de la Fase 3 (TWCVRP / variante con ventanas, single-depot, multi-vehicle,
tamanos 50/100/200), de forma controlada y trazable.

NO modifica el DSS. NO adapta instancias al formato del DSS. NO ejecuta modelos.
NO altera los crudos en svrpbench_raw/. Solo escribe en svrpbench_processed/.

Nota honesta (instruccion 11): el parquet crudo NO contiene columna de ventanas
horarias; los subsets `twvrp_*` son la variante TWCVRP del dataset (marcador en
`subset_name`), pero los VALORES de ventana deben materializarse aparte (generador de
la suite) antes de la evaluacion. Por eso el filtro de "ventanas" se aplica a nivel de
VARIANTE (twvrp_), y se marca `has_time_window_values=False` sin inventar datos.

Uso:
    python data_benchmark/svrpbench_scripts/filter_svrpbench_subset.py
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
RAW_DIR = SCRIPTS_DIR.parent / "svrpbench_raw"
PROC_DIR = SCRIPTS_DIR.parent / "svrpbench_processed"
PROC_DIR.mkdir(parents=True, exist_ok=True)

RAW_PARQUET = RAW_DIR / "svrpbench_test.parquet"

# Salidas
OUT_PARQUET = PROC_DIR / "svrpbench_subset.parquet"
OUT_SAMPLE_CSV = PROC_DIR / "svrpbench_subset_sample.csv"
OUT_SELECTED = PROC_DIR / "selected_instances.csv"
OUT_EXCLUDED = PROC_DIR / "excluded_instances.csv"
OUT_CONFIG = PROC_DIR / "benchmark_subset_config.json"

SIZES_OBJETIVO = [50, 100, 200]
NESTED_COLS = ["locations", "demands", "vehicle_capacities", "appear_times"]


# --------------------------------------------------------------------------- #
# Utilitarios
# --------------------------------------------------------------------------- #
def _to_native(v):
    if isinstance(v, np.ndarray):
        return [_to_native(x) for x in v.tolist()]
    if isinstance(v, (list, tuple)):
        return [_to_native(x) for x in v]
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return v


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


def _vehicle_suffix(s):
    s = str(s)
    for k in ("multi_vehicule_capacities", "single_vehicule_capacities",
              "single_vehicule_sumDemands"):
        if k in s:
            return k
    return "base"


def _safe_len(v):
    try:
        return int(len(v))
    except Exception:
        return 0


# --------------------------------------------------------------------------- #
# Derivacion de metadatos (sobre copia de trabajo, nunca sobre el crudo)
# --------------------------------------------------------------------------- #
def derivar(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["row_index_original"] = np.arange(len(d))
    d["instance_uid"] = d["subset_name"].astype(str) + "__" + d["instance_id"].astype(str)
    d["variant"] = d["subset_name"].apply(_variant)
    d["size_declarado"] = d["subset_name"].apply(_size)
    d["depot_config"] = d["subset_name"].apply(_depot_cfg)
    d["vehicle_suffix"] = d["subset_name"].apply(_vehicle_suffix)
    d["n_points"] = d["locations"].apply(_safe_len)
    d["n_customers"] = d["n_points"] - 1
    d["cap_len"] = d["vehicle_capacities"].apply(_safe_len)
    d["cap_consistent"] = d["cap_len"] == d["num_vehicles"]
    d["vehiculo_tipo"] = d["num_vehicles"].apply(lambda n: "multi" if int(n) > 1 else "single")
    d["demanda_total"] = d["demands"].apply(lambda x: int(sum(x)) if _safe_len(x) else 0)
    d["demanda_len"] = d["demands"].apply(_safe_len)
    d["is_twcvrp_variant"] = d["variant"] == "twcvrp"
    # El parquet crudo NO trae valores de ventana -> se marca explicitamente.
    d["has_time_window_values"] = False
    return d


# --------------------------------------------------------------------------- #
# Filtros secuenciales trazables
# --------------------------------------------------------------------------- #
def aplicar_filtros(d: pd.DataFrame):
    """Aplica filtros en orden; devuelve (seleccionadas, excluidas, traza_conteos)."""
    filtros = [
        ("F1_variante_TWCVRP", d["variant"] == "twcvrp",
         "subset_name comienza con 'twvrp_' (variante con ventanas)"),
        ("F2_single_depot", d["depot_config"] == "single_depot",
         "'single_depot' in subset_name"),
        ("F3_tamano_50_100_200", d["size_declarado"].isin(SIZES_OBJETIVO),
         "tamano derivado en {50,100,200}"),
        ("F4_multi_vehicle", d["num_vehicles"] > 1,
         "num_vehicles > 1"),
        ("F5_capacidades_consistentes", d["cap_consistent"],
         "len(vehicle_capacities) == num_vehicles"),
    ]

    # Validacion de campos criticos no nulos (F6).
    def _validos(row):
        problemas = []
        if row["n_points"] < 2:
            problemas.append("locations vacio o sin clientes")
        if row["demanda_len"] != row["n_points"]:
            problemas.append("demands con longitud distinta a locations")
        if row["cap_len"] < 1:
            problemas.append("vehicle_capacities vacio")
        if not (isinstance(row["num_vehicles"], (int, np.integer)) and int(row["num_vehicles"]) > 0):
            problemas.append("num_vehicles invalido")
        if pd.isna(row["instance_id"]):
            problemas.append("instance_id nulo")
        if pd.isna(row["size_declarado"]):
            problemas.append("size no derivable")
        return problemas

    d = d.copy()
    d["_validacion_problemas"] = d.apply(lambda r: "; ".join(_validos(r)), axis=1)
    filtros.append(("F6_campos_criticos_no_nulos", d["_validacion_problemas"] == "",
                    "clientes+deposito+demanda+capacidad+vehiculos+id+tamano no nulos"))

    n0 = len(d)
    traza = [{"paso": "F0_universo", "regla": "todas las instancias del parquet",
              "antes": n0, "despues": n0, "excluidas_en_este_paso": 0}]

    vivos = pd.Series(True, index=d.index)
    motivo_exclusion = pd.Series("", index=d.index)

    for nombre, mask, regla in filtros:
        antes = int(vivos.sum())
        # Excluidas en este paso = vivas que fallan la mask aqui.
        falla = vivos & (~mask)
        # Registrar motivo solo si aun no tenian motivo (primer filtro que las excluye).
        nuevas = falla & (motivo_exclusion == "")
        if nombre == "F6_campos_criticos_no_nulos":
            motivo_exclusion[nuevas] = "F6: " + d.loc[nuevas, "_validacion_problemas"]
        else:
            motivo_exclusion[nuevas] = f"{nombre}: no cumple ({regla})"
        vivos = vivos & mask
        despues = int(vivos.sum())
        traza.append({"paso": nombre, "regla": regla, "antes": antes,
                      "despues": despues, "excluidas_en_este_paso": antes - despues})

    seleccionadas = d[vivos].copy()
    excluidas = d[~vivos].copy()
    excluidas["motivo_exclusion"] = motivo_exclusion[~vivos]
    return seleccionadas, excluidas, traza


# --------------------------------------------------------------------------- #
# Escritura de salidas
# --------------------------------------------------------------------------- #
META_COLS = ["instance_uid", "subset_name", "file_name", "instance_id",
             "row_index_original", "variant", "size_declarado", "depot_config",
             "vehicle_suffix", "n_points", "n_customers", "num_vehicles",
             "vehiculo_tipo", "cap_len", "cap_consistent", "demanda_total",
             "is_twcvrp_variant", "has_time_window_values"]


def escribir_salidas(seleccionadas, excluidas):
    # 1) Parquet del subconjunto (incluye anidados originales + derivados).
    cols_parquet = ["instance_uid", "subset_name", "file_name", "instance_id",
                    "row_index_original", "variant", "size_declarado", "depot_config",
                    "vehicle_suffix", "n_points", "n_customers", "num_vehicles",
                    "vehiculo_tipo", "cap_len", "cap_consistent", "demanda_total",
                    "is_twcvrp_variant", "has_time_window_values",
                    "locations", "demands", "vehicle_capacities", "appear_times"]
    seleccionadas[cols_parquet].reset_index(drop=True).to_parquet(OUT_PARQUET, index=False)

    # 2) Muestra CSV (las 30, anidados en JSON para inspeccion visual).
    sample = seleccionadas[META_COLS].copy()
    for col in NESTED_COLS:
        sample[col + "_json"] = seleccionadas[col].apply(lambda v: json.dumps(_to_native(v)))
    sample.to_csv(OUT_SAMPLE_CSV, index=False, encoding="utf-8")

    # 3) selected_instances.csv (metadatos, sin anidados pesados).
    seleccionadas[META_COLS].to_csv(OUT_SELECTED, index=False, encoding="utf-8")

    # 4) excluded_instances.csv (todas las excluidas + razon).
    exc_cols = ["instance_uid", "subset_name", "instance_id", "variant",
                "size_declarado", "depot_config", "vehicle_suffix",
                "num_vehicles", "vehiculo_tipo", "cap_consistent", "motivo_exclusion"]
    excluidas[exc_cols].to_csv(OUT_EXCLUDED, index=False, encoding="utf-8")


def construir_config(n0, seleccionadas, excluidas, traza):
    por_tamano = seleccionadas["size_declarado"].value_counts().sort_index().to_dict()
    por_variante = seleccionadas["variant"].value_counts().to_dict()
    por_depot = seleccionadas["depot_config"].value_counts().to_dict()
    por_vehiculo = seleccionadas["vehiculo_tipo"].value_counts().to_dict()

    cfg = {
        "fecha_generacion": str(date.today()),
        "dataset": "SVRPBench (MBZUAI/svrp-bench, parquet, split test)",
        "fuente_cruda": str(RAW_PARQUET.relative_to(SCRIPTS_DIR.parent.parent)),
        "criterios_inclusion": {
            "variante": "TWCVRP (subset_name comienza con 'twvrp_')",
            "deposito": "single-depot ('single_depot' in subset_name)",
            "vehiculos": "multi-vehicle (num_vehicles > 1)",
            "tamanos": SIZES_OBJETIVO,
            "capacidades": "len(vehicle_capacities) == num_vehicles",
            "campos_criticos_no_nulos": True,
        },
        "criterios_exclusion": {
            "cvrp_sin_ventanas": True,
            "multi_depot_o_depots_equal_city": True,
            "single_vehicle": True,
            "tamanos_fuera_de_50_100_200": True,
            "capacidades_inconsistentes": True,
            "campos_criticos_nulos": True,
        },
        "campos_usados_para_filtrar": {
            "tipo_problema": "subset_name (prefijo twvrp_/cvrp_)",
            "ventanas_horarias": "subset_name (variante twvrp_); VALORES no presentes en el parquet",
            "cantidad_clientes": "len(locations) - 1 (y tamano en subset_name)",
            "tipo_deposito": "subset_name (single_depot/...)",
            "numero_depositos": "convencion: locations[0] = deposito unico",
            "cantidad_vehiculos": "num_vehicles",
            "config_vehicular": "subset_name (sufijo) + num_vehicles",
            "demanda": "demands",
            "capacidad": "vehicle_capacities",
            "variables_estocasticas": "NO en el parquet; provienen del generador de la suite",
        },
        "n_instancias_originales": int(n0),
        "n_instancias_seleccionadas": int(len(seleccionadas)),
        "n_instancias_excluidas": int(len(excluidas)),
        "conteos_por_tamano": {str(k): int(v) for k, v in por_tamano.items()},
        "conteos_por_variante": {str(k): int(v) for k, v in por_variante.items()},
        "conteos_por_deposito": {str(k): int(v) for k, v in por_depot.items()},
        "conteos_por_vehiculo": {str(k): int(v) for k, v in por_vehiculo.items()},
        "traza_filtros": traza,
        "validacion_campos": {
            "tienen_clientes": bool((seleccionadas["n_customers"] > 0).all()),
            "tienen_deposito": bool((seleccionadas["n_points"] >= 1).all()),
            "tienen_demanda": bool((seleccionadas["demanda_len"] == seleccionadas["n_points"]).all()),
            "tienen_capacidad": bool((seleccionadas["cap_len"] >= 1).all()),
            "tienen_ventanas_valores": bool(seleccionadas["has_time_window_values"].any()),
            "son_variante_twcvrp": bool(seleccionadas["is_twcvrp_variant"].all()),
            "son_single_depot": bool((seleccionadas["depot_config"] == "single_depot").all()),
            "son_multi_vehicle": bool((seleccionadas["num_vehicles"] > 1).all()),
        },
        "archivos_generados": {
            "subset_parquet": str(OUT_PARQUET.name),
            "subset_sample_csv": str(OUT_SAMPLE_CSV.name),
            "selected_instances_csv": str(OUT_SELECTED.name),
            "excluded_instances_csv": str(OUT_EXCLUDED.name),
            "config_json": str(OUT_CONFIG.name),
            "diagnostico_md": "svrpbench_subset_diagnostico_fase4.md",
        },
        "nota_ventanas": ("Los subsets twvrp_* son la variante TWCVRP del dataset, pero el "
                          "parquet crudo NO incluye los valores de ventana. Deben materializarse "
                          "con el generador de la suite (semilla fija) antes de evaluar. No se "
                          "inventan datos en esta fase."),
    }
    OUT_CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def main():
    if not RAW_PARQUET.exists():
        print(f"ERROR: no existe {RAW_PARQUET}. Ejecuta download_svrpbench.py.", file=sys.stderr)
        return 1

    raw = pd.read_parquet(RAW_PARQUET)   # solo lectura; el crudo no se modifica
    n0 = len(raw)
    d = derivar(raw)
    seleccionadas, excluidas, traza = aplicar_filtros(d)

    print("=" * 64)
    print("FILTRADO SVRPBench - Fase 4")
    print("=" * 64)
    for t in traza:
        print(f"  {t['paso']:32s} antes={t['antes']:>4} despues={t['despues']:>4} "
              f"(-{t['excluidas_en_este_paso']})")
    print(f"\nSeleccionadas: {len(seleccionadas)} | Excluidas: {len(excluidas)}")
    print("Por tamano:", seleccionadas["size_declarado"].value_counts().sort_index().to_dict())

    escribir_salidas(seleccionadas, excluidas)
    cfg = construir_config(n0, seleccionadas, excluidas, traza)

    print("\n[OK] Subconjunto procesado escrito en", PROC_DIR)
    for k, v in cfg["archivos_generados"].items():
        print(f"     {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
