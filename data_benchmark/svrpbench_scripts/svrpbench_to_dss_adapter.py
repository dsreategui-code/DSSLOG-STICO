# -*- coding: utf-8 -*-
"""Fase 5 - Adaptador SVRPBench -> formato interno del DSS.

Convierte una instancia del subconjunto procesado de SVRPBench
(`svrpbench_processed/svrpbench_subset.parquet`) a los DataFrames/archivos que el
optimizador actual del DSS ya consume, **sin modificar el DSS**. El optimizador del DSS
usa un deposito global (ALMACEN, Callao) y construye matrices euclidianas; por eso este
adaptador **traslada y escala** las coordenadas de SVRPBench para que el deposito de la
instancia caiga exactamente en ALMACEN, preservando la geometria relativa. Asi el motor
del DSS queda intacto.

Supuestos documentados (instrucciones 10, 11):
  - Escala: 1 unidad de la grilla SVRPBench = KM_POR_UNIDAD km (default 0.05; grilla ~1000
    -> ciudad ~50 km). Configurable.
  - Deposito: locations[0] de la instancia (demanda 0) -> ALMACEN (Callao). Single-depot.
  - Demanda: SVRPBench `demands[i]` -> `peso_kg` del pedido.
  - Capacidad: SVRPBench `vehicle_capacities[v]` -> `capacidad_kg` del vehiculo v.
    `capacidad_unidades` se fija alta (= nº clientes) para no restringir (SVRPBench limita por
    suma de demanda vs capacidad, analogo a kg).
  - Ventanas horarias: NO estan materializadas en el parquet (Fase 4). Se asigna ventana
    abierta = jornada completa (09:00-19:00) como valor estandar para permitir la corrida
    benchmark. Registrado como supuesto. (La materializacion real es tarea de fases posteriores.)
  - Tiempo de servicio: no existe en SVRPBench -> 0 min (supuesto).
  - Zona: single-depot -> zona unica "ALM" para todos. Sin variables locales de Lima.

NO ejecuta el benchmark final ni todos los modelos. NO toca data/ del DSS.
"""
import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import pandas as pd

# Raiz del proyecto en sys.path para importar modulos del DSS (sin modificarlos).
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import ALMACEN  # noqa: E402

PROC_DIR = SCRIPTS_DIR.parent / "svrpbench_processed"
SUBSET_PARQUET = PROC_DIR / "svrpbench_subset.parquet"
CASES_DIR = SCRIPTS_DIR.parent / "svrpbench_cases"

# ---- Constantes de mapeo (supuestos) ----
KM_POR_UNIDAD = 0.05          # 1 unidad de grilla SVRPBench = 0.05 km
JORNADA_INICIO = "09:00"
JORNADA_FIN = "19:00"
SERVICIO_DEFAULT_MIN = 0.0
ZONA_BENCHMARK = "ALM"
VELOCIDAD_KMH = 18.0


class AdapterError(Exception):
    """Error controlado del adaptador."""


# --------------------------------------------------------------------------- #
# Carga y seleccion
# --------------------------------------------------------------------------- #
def cargar_subset() -> pd.DataFrame:
    if not SUBSET_PARQUET.exists():
        raise AdapterError(
            f"No existe {SUBSET_PARQUET}. Ejecuta filter_svrpbench_subset.py (Fase 4)."
        )
    return pd.read_parquet(SUBSET_PARQUET)


def listar_instancias() -> pd.DataFrame:
    df = cargar_subset()
    return df[["instance_uid", "subset_name", "instance_id", "size_declarado",
               "num_vehicles"]].reset_index(drop=True)


def _buscar_fila(df: pd.DataFrame, selector) -> pd.Series:
    """Selecciona por instance_uid exacto o por (subset_name, instance_id)."""
    s = str(selector)
    hit = df[df["instance_uid"].astype(str) == s]
    if not hit.empty:
        return hit.iloc[0]
    # Fallback: instance_id numerico de un solo tamano no es unico -> exigir uid.
    raise AdapterError(
        f"Instancia '{selector}' no encontrada. Usa instance_uid "
        f"(p.ej. 'twvrp_50_single_depot__0'). Disponibles: {len(df)}."
    )


# --------------------------------------------------------------------------- #
# Transformacion geometrica
# --------------------------------------------------------------------------- #
def _a_latlon(px, py, depot_x, depot_y):
    """Traslada+escala un punto de la grilla a lat/lon alrededor de ALMACEN."""
    off_x_km = (px - depot_x) * KM_POR_UNIDAD
    off_y_km = (py - depot_y) * KM_POR_UNIDAD
    lat = ALMACEN["latitud"] + off_y_km / 111.0
    lon = ALMACEN["longitud"] + off_x_km / (111.0 * math.cos(math.radians(ALMACEN["latitud"])))
    return round(lat, 6), round(lon, 6)


# --------------------------------------------------------------------------- #
# Adaptacion principal
# --------------------------------------------------------------------------- #
def adaptar_instancia(selector, escribir_archivos: bool = True) -> dict:
    """Adapta una instancia SVRPBench y devuelve DataFrames listos para el optimizador.

    Devuelve dict: {instance_uid, pedidos, vehiculos, zonas, matriz_tiempos,
                    parametros, metadata}.
    """
    df = cargar_subset()
    fila = _buscar_fila(df, selector)
    uid = str(fila["instance_uid"])

    locations = [list(map(float, p)) for p in fila["locations"]]
    demands = [float(x) for x in fila["demands"]]
    capacities = [float(c) for c in fila["vehicle_capacities"]]
    num_vehicles = int(fila["num_vehicles"])

    if not locations:
        raise AdapterError(f"{uid}: 'locations' vacio.")
    if len(demands) != len(locations):
        raise AdapterError(f"{uid}: longitud de demands ({len(demands)}) != locations ({len(locations)}).")
    if not capacities:
        raise AdapterError(f"{uid}: 'vehicle_capacities' vacio.")

    depot_x, depot_y = locations[0]

    # --- pedidos (clientes = locations[1:]) ---
    pedidos_rows = []
    for i in range(1, len(locations)):
        px, py = locations[i]
        lat, lon = _a_latlon(px, py, depot_x, depot_y)
        pedidos_rows.append({
            "pedido_id": f"C{i:04d}",
            "cliente": f"cliente_{i}",
            "distrito": ZONA_BENCHMARK,
            "zona": ZONA_BENCHMARK,
            "modelo": "benchmark",
            "peso_kg": float(demands[i]),
            "tipo_servicio": "Estandar",
            "tiempo_servicio_min": SERVICIO_DEFAULT_MIN,
            "ventana_inicio": JORNADA_INICIO,
            "ventana_fin": JORNADA_FIN,
            "latitud": lat,
            "longitud": lon,
            "grid_x": px,
            "grid_y": py,
        })
    pedidos = pd.DataFrame(pedidos_rows)

    # --- vehiculos ---
    n_clientes = len(pedidos)
    vehiculos_rows = []
    for v in range(num_vehicles):
        cap_kg = float(capacities[v]) if v < len(capacities) else float(capacities[-1])
        vehiculos_rows.append({
            "vehiculo_id": f"V{v+1:02d}",
            "placa": f"BMK-{v+1:03d}",
            "capacidad_unidades": int(n_clientes),   # alto: no restringe
            "capacidad_kg": cap_kg,
            "zona_preferente": ZONA_BENCHMARK,
            "conductor": "benchmark",
        })
    vehiculos = pd.DataFrame(vehiculos_rows)

    # --- zonas (single zone) ---
    dlat, dlon = _a_latlon(depot_x, depot_y, depot_x, depot_y)
    zonas = pd.DataFrame([{
        "zona": ZONA_BENCHMARK, "centro_lat": dlat, "centro_lon": dlon,
    }])

    # --- matriz de tiempos (depot + clientes), euclidiana km/min ---
    matriz = _construir_matriz(pedidos)

    # --- parametros ---
    parametros = pd.DataFrame([{
        "velocidad_kmh": VELOCIDAD_KMH,
        "jornada_inicio": JORNADA_INICIO,
        "jornada_fin": JORNADA_FIN,
        "km_por_unidad": KM_POR_UNIDAD,
        "servicio_default_min": SERVICIO_DEFAULT_MIN,
        "motor_optimizacion": "auto",
    }])

    metadata = {
        "instance_uid": uid,
        "subset_name": str(fila["subset_name"]),
        "instance_id": int(fila["instance_id"]),
        "row_index_original": int(fila["row_index_original"]),
        "size_declarado": int(fila["size_declarado"]),
        "n_clientes": n_clientes,
        "num_vehicles": num_vehicles,
        "depot_grid": [depot_x, depot_y],
        "depot_latlon": [dlat, dlon],
        "demanda_total": float(sum(demands)),
        "capacidad_total": float(sum(capacities)),
        "capacidad_min": float(min(capacities)),
        "supuestos": {
            "km_por_unidad": KM_POR_UNIDAD,
            "deposito": "locations[0] -> ALMACEN (Callao); single-depot",
            "demanda": "demands -> peso_kg",
            "capacidad": "vehicle_capacities -> capacidad_kg; capacidad_unidades = n_clientes (no restringe)",
            "ventanas": "ventana abierta 09:00-19:00 (no materializadas en el parquet)",
            "tiempo_servicio": f"{SERVICIO_DEFAULT_MIN} min (no existe en SVRPBench)",
            "zona": f"'{ZONA_BENCHMARK}' unica (sin variables locales de Lima)",
        },
    }

    resultado = {
        "instance_uid": uid, "pedidos": pedidos, "vehiculos": vehiculos,
        "zonas": zonas, "matriz_tiempos": matriz, "parametros": parametros,
        "metadata": metadata,
    }

    validar_caso(resultado)
    if escribir_archivos:
        _escribir_caso(resultado)
    return resultado


def _construir_matriz(pedidos: pd.DataFrame) -> pd.DataFrame:
    """Matriz depot+clientes (euclidiana en km y min a VELOCIDAD_KMH)."""
    nodos = [("ALMACEN", ALMACEN["latitud"], ALMACEN["longitud"])]
    for _, p in pedidos.iterrows():
        nodos.append((p["pedido_id"], p["latitud"], p["longitud"]))
    filas = []
    for oid, olat, olon in nodos:
        for did, dlat, dlon in nodos:
            if oid == did:
                continue
            dx = (dlat - olat) * 111.0
            dy = (dlon - olon) * 111.0 * math.cos(math.radians((olat + dlat) / 2))
            dist = math.sqrt(dx * dx + dy * dy)
            filas.append({
                "origen": oid, "destino": did,
                "distancia_km": round(dist, 4),
                "tiempo_min": round(dist / max(VELOCIDAD_KMH, 1.0) * 60.0, 3),
            })
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------- #
# Validacion (instruccion 16)
# --------------------------------------------------------------------------- #
def validar_caso(caso: dict) -> None:
    uid = caso["instance_uid"]
    pedidos, vehiculos = caso["pedidos"], caso["vehiculos"]
    from utils.formatters import hhmm_to_minutes

    if pedidos.empty:
        raise AdapterError(f"{uid}: sin clientes.")
    if (pedidos["peso_kg"] < 0).any():
        raise AdapterError(f"{uid}: demandas negativas detectadas.")
    if pedidos[["latitud", "longitud"]].isnull().any().any():
        raise AdapterError(f"{uid}: clientes sin coordenadas.")
    for col in ("ventana_inicio", "ventana_fin"):
        if pedidos[col].isnull().any():
            raise AdapterError(f"{uid}: ventana nula en {col}.")
    if (pedidos["ventana_inicio"].apply(hhmm_to_minutes)
            >= pedidos["ventana_fin"].apply(hhmm_to_minutes)).any():
        raise AdapterError(f"{uid}: ventana invalida (inicio >= fin).")
    if vehiculos.empty:
        raise AdapterError(f"{uid}: sin vehiculos.")
    if (vehiculos["capacidad_kg"] <= 0).any() or vehiculos["capacidad_kg"].isnull().any():
        raise AdapterError(f"{uid}: capacidad vehicular nula o no positiva.")
    # Factibilidad gruesa: capacidad total >= demanda total.
    if float(vehiculos["capacidad_kg"].sum()) < float(pedidos["peso_kg"].sum()) - 1e-6:
        raise AdapterError(
            f"{uid}: capacidad total insuficiente "
            f"({vehiculos['capacidad_kg'].sum():.0f} < {pedidos['peso_kg'].sum():.0f})."
        )
    # Deposito (matriz debe contener ALMACEN como origen).
    if "ALMACEN" not in set(caso["matriz_tiempos"]["origen"]):
        raise AdapterError(f"{uid}: matriz sin deposito (ALMACEN).")


# --------------------------------------------------------------------------- #
# Escritura del caso
# --------------------------------------------------------------------------- #
def _escribir_caso(caso: dict) -> Path:
    uid = caso["instance_uid"]
    cdir = CASES_DIR / uid
    cdir.mkdir(parents=True, exist_ok=True)
    caso["pedidos"].to_csv(cdir / "pedidos_benchmark.csv", index=False, encoding="utf-8")
    caso["vehiculos"].to_csv(cdir / "vehiculos_benchmark.csv", index=False, encoding="utf-8")
    caso["zonas"].to_csv(cdir / "zonas_benchmark.csv", index=False, encoding="utf-8")
    caso["matriz_tiempos"].to_csv(cdir / "matriz_tiempos_benchmark.csv", index=False, encoding="utf-8")
    caso["parametros"].to_csv(cdir / "parametros_benchmark.csv", index=False, encoding="utf-8")
    with open(cdir / "metadata_benchmark.json", "w", encoding="utf-8") as f:
        json.dump(caso["metadata"], f, indent=2, ensure_ascii=False)
    return cdir


# --------------------------------------------------------------------------- #
# API de conveniencia para el optimizador (instruccion 13, 14)
# --------------------------------------------------------------------------- #
def cargar_para_optimizador(selector) -> tuple:
    """Devuelve (pedidos, vehiculos) DataFrames listos para construir_rutas_iniciales."""
    caso = adaptar_instancia(selector, escribir_archivos=False)
    return caso["pedidos"], caso["vehiculos"]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Adapta una instancia SVRPBench al formato DSS.")
    ap.add_argument("--instancia", help="instance_uid (ej. twvrp_50_single_depot__0)")
    ap.add_argument("--listar", action="store_true", help="Lista las instancias disponibles.")
    args = ap.parse_args()
    if args.listar or not args.instancia:
        print(listar_instancias().to_string(index=False))
    else:
        c = adaptar_instancia(args.instancia)
        print(f"OK: {c['instance_uid']} -> {len(c['pedidos'])} clientes, "
              f"{len(c['vehiculos'])} vehiculos. Caso en {CASES_DIR / c['instance_uid']}")
