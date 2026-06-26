# -*- coding: utf-8 -*-
"""Fase 1 - Inspeccion de SVRPBench y generacion del diagnostico.

Lee el Parquet descargado por download_svrpbench.py y reporta la estructura del
dataset (splits, filas, columnas, tipos, campos anidados, campos para filtrar
variante/tamano/depot/vehiculo, ventanas, demanda, capacidad, depositos y
variables estocasticas). Escribe `svrpbench_diagnostico_fase1.md` en svrpbench_raw/.

NO modifica el DSS. NO adapta el dataset. NO ejecuta modelos.

Uso:
    python data_benchmark/svrpbench_scripts/inspect_svrpbench.py
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
RAW_DIR = SCRIPTS_DIR.parent / "svrpbench_raw"
PARQUET = RAW_DIR / "svrpbench_test.parquet"
DIAG_MD = RAW_DIR / "svrpbench_diagnostico_fase1.md"

NESTED_COLS = ["locations", "demands", "vehicle_capacities", "appear_times"]


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


def construir_reporte(df: pd.DataFrame) -> dict:
    """Calcula todos los indicadores de inspeccion y los devuelve en un dict."""
    rep = {}
    rep["n_filas"] = len(df)
    rep["columnas"] = list(df.columns)
    rep["dtypes"] = {c: str(df[c].dtype) for c in df.columns}

    fila0 = df.iloc[0]
    primera = {}
    for c in df.columns:
        v = fila0[c]
        if hasattr(v, "__len__") and not isinstance(v, str):
            primera[c] = f"lista(len={len(v)}) ej={list(v[:3])}"
        else:
            primera[c] = v
    rep["primera_fila"] = primera

    rep["campos_anidados"] = [c for c in df.columns
                              if hasattr(df.iloc[0][c], "__len__")
                              and not isinstance(df.iloc[0][c], str)]

    # Derivados.
    df = df.copy()
    df["variant"] = df["subset_name"].apply(_variant)
    df["size_declarado"] = df["subset_name"].apply(_size)
    df["depot_config"] = df["subset_name"].apply(_depot_cfg)
    df["n_puntos"] = df["locations"].apply(len)
    df["veh_tipo"] = df["num_vehicles"].apply(lambda n: "single" if int(n) == 1 else "multi")

    rep["variantes"] = df["variant"].value_counts().to_dict()
    rep["tamanos"] = df["size_declarado"].value_counts().sort_index().to_dict()
    rep["depot_config"] = df["depot_config"].value_counts().to_dict()
    rep["veh_tipo"] = df["veh_tipo"].value_counts().to_dict()
    rep["subsets"] = sorted(df["subset_name"].unique().tolist())
    rep["n_subsets"] = df["subset_name"].nunique()

    # n de puntos por tamano (verifica N+1 vs depositos extra).
    rep["npuntos_por_tamano"] = (
        df.groupby("size_declarado")["n_puntos"].agg(["min", "max"]).to_dict("index")
    )

    # Senales de presencia de campos.
    rep["tiene_demandas"] = "demands" in df.columns
    rep["tiene_capacidades"] = "vehicle_capacities" in df.columns
    rep["tiene_depot_implicito"] = "locations" in df.columns  # locations[0] = depot
    rep["tiene_ventanas_explicitas"] = any(
        any(k in c.lower() for k in ("time_window", "tw_", "ready", "due", "start_time", "end_time"))
        for c in df.columns
    )
    rep["tiene_estocasticos_explicitos"] = any(
        any(k in c.lower() for k in ("delay", "accident", "congest", "traffic", "stochastic", "noise"))
        for c in df.columns
    )
    # appear_times: senal de dinamismo. Revisar si es trivial (todo 0).
    df["appear_unicos"] = df["appear_times"].apply(lambda a: len(set(a)))
    df["appear_max"] = df["appear_times"].apply(lambda a: int(max(a)) if len(a) else 0)
    rep["appear_times_no_triviales"] = int((df["appear_unicos"] > 1).sum())
    rep["appear_times_max_global"] = int(df["appear_max"].max())

    # Consistencia len(vehicle_capacities) vs num_vehicles.
    df["n_cap"] = df["vehicle_capacities"].apply(len)
    df["cap_coincide"] = df["n_cap"] == df["num_vehicles"]
    rep["cap_coincide"] = int(df["cap_coincide"].sum())
    multi = df[df["subset_name"].str.contains("multi_vehicule_capacities")]
    rep["cap_multi_inconsistentes"] = int((~multi["cap_coincide"]).sum())
    rep["cap_multi_total"] = int(len(multi))

    return rep


def imprimir_reporte(rep: dict) -> None:
    print("=" * 64)
    print("INSPECCION SVRPBench - Fase 1")
    print("=" * 64)
    print(f"Splits disponibles: 1 (test)")
    print(f"Filas (split test): {rep['n_filas']}")
    print(f"Subsets (subset_name): {rep['n_subsets']}")
    print(f"Columnas: {rep['columnas']}")
    print(f"Tipos: {rep['dtypes']}")
    print(f"Campos anidados/complejos: {rep['campos_anidados']}")
    print(f"\nVariantes: {rep['variantes']}")
    print(f"Tamanos: {rep['tamanos']}")
    print(f"Config deposito: {rep['depot_config']}")
    print(f"Vehiculo single/multi: {rep['veh_tipo']}")
    print(f"\nVentanas horarias explicitas: {rep['tiene_ventanas_explicitas']}")
    print(f"Campos estocasticos explicitos: {rep['tiene_estocasticos_explicitos']}")
    print(f"appear_times no triviales (>1 valor): {rep['appear_times_no_triviales']} de {rep['n_filas']}")
    print(f"appear_times max global: {rep['appear_times_max_global']}")
    print("=" * 64)


def escribir_diagnostico(rep: dict) -> None:
    L = []
    L.append("# Diagnostico SVRPBench - Fase 1 (descarga e inspeccion)\n")
    L.append("Dataset: **MBZUAI/svrp-bench** (Hugging Face).  ")
    L.append("Fase: descarga, organizacion e inspeccion. **No** se adapta al DSS ni se "
             "ejecutan modelos.\n")

    L.append("## 1. Descarga\n")
    L.append("- El dataset se descargo correctamente: **si**.")
    L.append("- Estructura del repo: un unico Parquet (`data/test-00000-of-00001.parquet`) + README.")
    L.append(f"- Split unico: **test** con **{rep['n_filas']} instancias**, agrupadas en "
             f"**{rep['n_subsets']} subsets** (`subset_name`).\n")

    L.append("## 2. Archivos generados (en `data_benchmark/svrpbench_raw/`)\n")
    L.append("- `svrpbench_test.parquet` - dataset completo en Parquet.")
    L.append("- `svrpbench_sample.csv` - muestra (1 instancia por subset) con anidados en JSON y columnas derivadas.")
    L.append("- `svrpbench_columns.txt` - lista de columnas, tipos y ejemplos.")
    L.append("- `svrpbench_diagnostico_fase1.md` - este diagnostico.\n")

    L.append("## 3. Columnas del dataset\n")
    L.append("| columna | tipo | rol |")
    L.append("|---|---|---|")
    roles = {
        "subset_name": "Clave de filtrado: variante + tamano + config de deposito/vehiculo.",
        "file_name": "Nombre del archivo .npz de origen (redundante con subset_name).",
        "instance_id": "Indice de la instancia dentro del subset (0-9).",
        "locations": "Lista de coordenadas [x, y]. **locations[0] = deposito**, resto = clientes.",
        "demands": "Lista de demandas por punto. demands[0]=0 (deposito).",
        "num_vehicles": "Numero de vehiculos de la instancia.",
        "vehicle_capacities": "Lista de capacidades (1 por vehiculo).",
        "appear_times": "Tiempo de aparicion por punto (dinamismo). En este dataset: todo 0.",
    }
    for c in rep["columnas"]:
        L.append(f"| `{c}` | {rep['dtypes'].get(c,'')} | {roles.get(c,'')} |")
    L.append("")

    L.append("## 4. Campos para filtrar (taxonomia en `subset_name`)\n")
    L.append("Formato observado: `{variante}_{tamano}_{config_deposito}[_config_vehiculo]`.\n")
    L.append(f"- **Variantes**: {rep['variantes']}  ")
    L.append("  - `cvrp_*` = CVRP capacitado.  `twvrp_*` = **TWCVRP** (con ventanas horarias).")
    L.append(f"- **Tamanos** (clientes): {rep['tamanos']}")
    L.append(f"- **Config de deposito**: {rep['depot_config']}")
    L.append(f"- **Vehiculo single/multi** (por `num_vehicles`): {rep['veh_tipo']}\n")

    L.append("### Reglas de filtrado propuestas (para Fase 2)\n")
    L.append("| Objetivo | Regla |")
    L.append("|---|---|")
    L.append("| TWCVRP | `subset_name.startswith('twvrp_')` |")
    L.append("| Single-depot | `'single_depot' in subset_name` |")
    L.append("| Multi-depot | `'multi_depot' in subset_name` o `'depots_equal_city' in subset_name` |")
    L.append("| Single-vehicle | `num_vehicles == 1` |")
    L.append("| Multi-vehicle | `num_vehicles > 1` |")
    L.append("| Tamano 50 / 100 / 200 | size derivado de `subset_name` == 50 / 100 / 200 |")
    L.append("")

    L.append("## 5. Presencia de elementos clave\n")
    L.append("| Elemento | Presente | Como |")
    L.append("|---|---|---|")
    L.append("| Coordenadas de clientes | Si | `locations[1:]` |")
    L.append("| Deposito(s) | Si (implicito) | `locations[0]` (demanda 0); multi-depot por config |")
    L.append("| Demanda | Si | `demands` (entero por punto) |")
    L.append("| Capacidad vehicular | Si | `vehicle_capacities` |")
    L.append("| Numero de vehiculos | Si | `num_vehicles` |")
    L.append(f"| Ventanas horarias (columna explicita) | **No** | no hay columna TW; ni siquiera en `twvrp_*` |")
    L.append(f"| Variables estocasticas (congestion/retraso/accidente) | **No** | no hay columnas; ver seccion 7 |")
    L.append(f"| Dinamismo (`appear_times`) | Presente pero **trivial** | todo 0 en {rep['n_filas']} filas (max global={rep['appear_times_max_global']}) |")
    L.append("")

    L.append("## 6. Tamano de instancia vs numero de puntos\n")
    L.append("`n_puntos` deberia ser `tamano + 1` (clientes + deposito). En tamanos grandes hay")
    L.append("puntos extra (posibles depositos adicionales en configs multi-depot):\n")
    L.append("| tamano | n_puntos min | n_puntos max |")
    L.append("|---|---|---|")
    for size, mm in sorted(rep["npuntos_por_tamano"].items(), key=lambda kv: (kv[0] is None, kv[0])):
        L.append(f"| {size} | {mm['min']} | {mm['max']} |")
    L.append("")

    L.append("## 7. Problemas y vacios detectados (CRITICO)\n")
    L.append("1. **No hay columnas de ventanas horarias** en el Parquet, ni siquiera para los "
             "subsets `twvrp_*` (TWCVRP). Las ventanas que describe el paper se generan con el "
             "**codigo del pipeline de SVRPBench** (repositorio de generacion), no estan "
             "materializadas en este dataset de Hugging Face.")
    L.append("2. **No hay columnas estocasticas** (congestion, retrasos log-normales, accidentes, "
             "trafico por hora). Son justamente el motivo para elegir SVRPBench, pero **viven en "
             "el simulador/generador**, no en estas 8 columnas. Hay que obtenerlas aparte.")
    L.append(f"3. **`appear_times` es trivial** (todo 0 en las {rep['n_filas']} instancias): el "
             "dinamismo de aparicion no esta poblado en esta version del dataset.")
    L.append("4. **Representacion multi-deposito ambigua**: contar `demands == 0` no identifica "
             "depositos de forma fiable (hay clientes con demanda 0). Los depositos extra parecen "
             "reflejarse como puntos adicionales mas alla de `tamano+1`, pero el patron no es "
             "uniforme entre tamanos. Requiere verificacion en Fase 2.")
    L.append("5. **`subset_name` es la unica fuente de la taxonomia** (variante/tamano/config). "
             "No hay columnas atomicas para variante, tamano, n_depositos o config de vehiculo; "
             "se derivan por parsing del string.")
    L.append(f"6. **Capacidades inconsistentes en `multi_vehicule_capacities`**: en "
             f"{rep['cap_multi_inconsistentes']} de {rep['cap_multi_total']} de esos subsets, "
             f"`len(vehicle_capacities)` = 1 mientras `num_vehicles` es mucho mayor (hasta ~175). "
             f"Globalmente solo {rep['cap_coincide']}/{rep['n_filas']} filas cumplen "
             "`len(vehicle_capacities) == num_vehicles`. Hay que decidir en Fase 2 como asignar "
             "capacidad por vehiculo (replicar el valor unico o tratarlo como flota homogenea).\n")

    L.append("## 8. Que revisar antes de la Fase 2\n")
    L.append("1. **Origen de las ventanas horarias y de los eventos estocasticos**: revisar el "
             "repositorio/codigo oficial de SVRPBench (generador) para saber si se materializan "
             "ventanas, retrasos, congestion y accidentes, y con que distribuciones. Decidir si "
             "el adaptador del DSS (a) consume esos artefactos generados o (b) reconstruye las "
             "distribuciones segun el paper.")
    L.append("2. **Confirmar la convencion del deposito**: validar que `locations[0]` es siempre "
             "el deposito y como se listan multiples depositos en `multi_depot`/`depots_equal_city`.")
    L.append("3. **Definir el subconjunto experimental**: el contexto del DSS es ultima milla con "
             "ventanas y multi-vehiculo; el candidato natural es **`twvrp_*` single-depot** en "
             "tamanos **50/100/200**. Confirmar disponibilidad (hay 10 instancias por subset).")
    L.append("4. **Unidades y escala**: coordenadas enteras (~grilla 0-1000), capacidades en "
             "miles; definir el mapeo de unidades a tiempos/distancias del DSS.")
    L.append("5. **Compatibilidad con el DSS**: el DSS asume deposito unico (Callao) y ventanas "
             "HH:MM en una jornada; mapear el modelo SVRPBench (coordenadas abstractas, sin reloj "
             "explicito) a ese marco sin romper el flujo actual.\n")

    L.append("## 9. Conclusion de Fase 1\n")
    L.append("El dataset esta **descargado y organizado** en `data_benchmark/svrpbench_raw/`, con "
             "muestra CSV, lista de columnas y este diagnostico. La taxonomia de filtrado "
             "(variante/tamano/deposito/vehiculo) esta clara y vive en `subset_name` + "
             "`num_vehicles`. **Hallazgo principal**: las dimensiones estocasticas y de ventanas "
             "horarias **no estan en las columnas** del dataset HF; provienen del generador de "
             "SVRPBench. Resolver ese origen es el insumo critico para disenar la Fase 2.")

    DIAG_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"[OK] Diagnostico escrito en {DIAG_MD}")


def main():
    if not PARQUET.exists():
        print(f"ERROR: no existe {PARQUET}. Ejecuta primero download_svrpbench.py.",
              file=sys.stderr)
        return 1
    df = pd.read_parquet(PARQUET)
    rep = construir_reporte(df)
    imprimir_reporte(rep)
    escribir_diagnostico(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
