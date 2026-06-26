# -*- coding: utf-8 -*-
"""Fase 6 - Modulo de metricas COMUN para el benchmark SVRPBench.

Garantiza que TODOS los modelos (DSS y baselines) se puntuen de forma identica:
cada modelo produce rutas (listas de indices de cliente, 1..N, sin deposito) y este
modulo las evalua sobre la MISMA instancia canonica (coordenadas de la grilla SVRPBench).
Asi el costo, factibilidad, OTD, etc. se calculan con la misma formula para todos.

Escala/unidades alineadas con el adaptador de la Fase 5:
  - 1 unidad de grilla = KM_POR_UNIDAD km (0.05).
  - velocidad = 18 km/h para convertir distancia <-> tiempo.

Ventanas horarias: el subconjunto NO trae valores de ventana (Fases 4/5). Por defecto se
asume ventana abierta (jornada completa) -> time_window_violations=0 y otd=1.0. Si se
materializan ventanas (`time_windows` por nodo), este modulo las evalua correctamente.

NO toca el DSS. NO ejecuta modelos. Solo calcula metricas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
PROC_DIR = SCRIPTS_DIR.parent / "svrpbench_processed"
SUBSET_PARQUET = PROC_DIR / "svrpbench_subset.parquet"

KM_POR_UNIDAD = 0.05
VELOCIDAD_KMH = 18.0
JORNADA_MIN = (9 * 60, 19 * 60)   # 09:00-19:00 en minutos
SERVICIO_DEFAULT_MIN = 0.0


# --------------------------------------------------------------------------- #
# Instancia canonica (espacio de la grilla SVRPBench)
# --------------------------------------------------------------------------- #
@dataclass
class CanonicalInstance:
    instance_uid: str
    size: int
    num_vehicles: int
    coords: List[Tuple[float, float]]            # nodo 0 = deposito; 1..N = clientes
    demands: List[float]                          # idx 0 = deposito (0)
    capacities: List[float]                       # por vehiculo
    time_windows: Optional[List[Tuple[float, float]]] = None   # por nodo (min); None = abierta
    service_times: Optional[List[float]] = None   # por nodo (min); None = 0
    metadata: dict = field(default_factory=dict)

    @property
    def n_customers(self) -> int:
        return len(self.coords) - 1

    @property
    def total_demand(self) -> float:
        return float(sum(self.demands[1:]))

    def dist_km(self, a: int, b: int) -> float:
        (xa, ya), (xb, yb) = self.coords[a], self.coords[b]
        return math.hypot(xa - xb, ya - yb) * KM_POR_UNIDAD

    def ventana(self, nodo: int) -> Tuple[float, float]:
        if self.time_windows is not None and self.time_windows[nodo] is not None:
            return self.time_windows[nodo]
        return JORNADA_MIN

    def servicio(self, nodo: int) -> float:
        if self.service_times is not None:
            return float(self.service_times[nodo])
        return SERVICIO_DEFAULT_MIN


def cargar_instancia_canonica(instance_uid: str) -> CanonicalInstance:
    """Carga una instancia canonica desde el subconjunto procesado (Fase 4)."""
    if not SUBSET_PARQUET.exists():
        raise FileNotFoundError(f"No existe {SUBSET_PARQUET}. Ejecuta la Fase 4.")
    df = pd.read_parquet(SUBSET_PARQUET)
    hit = df[df["instance_uid"].astype(str) == str(instance_uid)]
    if hit.empty:
        raise KeyError(f"Instancia '{instance_uid}' no esta en el subconjunto.")
    r = hit.iloc[0]
    coords = [tuple(map(float, p)) for p in r["locations"]]
    demands = [float(x) for x in r["demands"]]
    caps = [float(c) for c in r["vehicle_capacities"]]
    return CanonicalInstance(
        instance_uid=str(r["instance_uid"]),
        size=int(r["size_declarado"]),
        num_vehicles=int(r["num_vehicles"]),
        coords=coords, demands=demands, capacities=caps,
        time_windows=None, service_times=None,
        metadata={"subset_name": str(r["subset_name"]),
                  "row_index_original": int(r["row_index_original"])},
    )


# --------------------------------------------------------------------------- #
# Normalizacion de rutas
# --------------------------------------------------------------------------- #
def normalizar_rutas(rutas, n_customers: int) -> List[List[int]]:
    """Devuelve rutas como listas de indices de cliente (1..N), sin deposito (0)."""
    out = []
    for ruta in rutas or []:
        limpia = [int(x) for x in ruta if int(x) != 0 and 1 <= int(x) <= n_customers]
        if limpia:
            out.append(limpia)
    return out


# --------------------------------------------------------------------------- #
# Calculo de metricas (identico para todos los modelos)
# --------------------------------------------------------------------------- #
def _dividir(a, b):
    return (a / b) if b else 0.0


# Modelo estocastico de scoring (Fase 8): multiplicador de tiempo de viaje por arco,
# semillado de forma determinista por (instancia, realizacion, arco). Es una
# SIMPLIFICACION del generador de la suite (retraso log-normal), aplicada de forma
# IDENTICA a todos los modelos para que la comparacion sea justa y reproducible.
import random as _random
import zlib as _zlib

SIGMA_LOGNORMAL = 0.30   # variabilidad del retraso (log-normal, E[mult] ~ 1)


def _mult_arco(instance_uid: str, realizacion: int, i: int, j: int) -> float:
    """Multiplicador estocastico (>0, media ~1) del tiempo de viaje del arco (i,j)."""
    clave = f"{instance_uid}|{realizacion}|{i}|{j}".encode("utf-8")
    seed = _zlib.crc32(clave)
    rng = _random.Random(seed)
    mu = -0.5 * SIGMA_LOGNORMAL ** 2   # asegura E[mult] = 1
    return rng.lognormvariate(mu, SIGMA_LOGNORMAL)


def calcular_metricas(rutas_cliente: List[List[int]], inst: CanonicalInstance,
                      scenario: Optional[int] = None) -> Dict:
    """Calcula metricas a partir de rutas y la instancia.

    Si `scenario` (id de realizacion) se entrega, el tiempo de viaje de cada arco se
    perturba con un multiplicador estocastico semillado por (instancia, scenario, arco);
    entonces `total_cost`/`total_time`/OTD/CVR/TWv reflejan esa realizacion. Si es None
    (deterministico, como el piloto), `total_cost` = distancia geometrica (km).
    """
    n = inst.n_customers
    servidos = [c for ruta in rutas_cliente for c in ruta]
    set_servidos = set(servidos)
    estocastico = scenario is not None

    total_dist_km = 0.0
    total_viaje_min = 0.0       # tiempo de viaje (perturbado si estocastico)
    total_serv_min = 0.0
    cap_violaciones = 0
    tw_violaciones = 0
    clientes_a_tiempo = 0
    demanda_servida_factible = 0.0
    vehiculos_usados = 0
    carga_por_ruta = []

    for v, ruta in enumerate(rutas_cliente):
        if not ruta:
            continue
        vehiculos_usados += 1
        cap_v = inst.capacities[v] if v < len(inst.capacities) else inst.capacities[-1]
        carga = sum(inst.demands[c] for c in ruta)
        carga_por_ruta.append(carga)
        factible_cap = carga <= cap_v + 1e-6
        if not factible_cap:
            cap_violaciones += 1

        prev = 0  # deposito
        t = float(inst.ventana(0)[0])  # arranca al abrir jornada
        for c in ruta:
            d = inst.dist_km(prev, c)
            total_dist_km += d
            viaje = d / max(VELOCIDAD_KMH, 1.0) * 60.0
            if estocastico:
                viaje *= _mult_arco(inst.instance_uid, scenario, prev, c)
            total_viaje_min += viaje
            t += viaje
            ini, fin = inst.ventana(c)
            if t < ini:
                t = ini  # espera apertura
            llegada = t
            if llegada <= fin:
                clientes_a_tiempo += 1
            else:
                tw_violaciones += 1
            serv = inst.servicio(c)
            total_serv_min += serv
            t += serv
            if factible_cap:
                demanda_servida_factible += inst.demands[c]
            prev = c

    total_time_min = total_viaje_min + total_serv_min
    # En modo estocastico el costo = tiempo operativo realizado (min); deterministico = km.
    total_cost = round(total_time_min, 4) if estocastico else round(total_dist_km, 4)

    # Restricciones evaluadas: capacidad por vehiculo usado + ventana por cliente servido.
    n_restricciones = vehiculos_usados + len(servidos)
    n_violaciones = cap_violaciones + tw_violaciones
    cvr = round(_dividir(n_violaciones, n_restricciones) * 100.0, 3)

    demand_fulfillment = round(_dividir(sum(inst.demands[c] for c in set_servidos),
                                        inst.total_demand), 4)
    feasibility = round(_dividir(demanda_servida_factible, inst.total_demand), 4)
    otd = round(_dividir(clientes_a_tiempo, len(servidos)) if servidos else 0.0, 4)

    cap_usada = sum(inst.capacities[v] if v < len(inst.capacities) else inst.capacities[-1]
                    for v in range(len(rutas_cliente)) if rutas_cliente[v])
    vehicle_utilization = round(_dividir(sum(carga_por_ruta), cap_usada), 4)

    # Factibilidad de cobertura: solo exige servir clientes con DEMANDA POSITIVA.
    # Un cliente con demanda 0 no requiere entrega; los solvers de la suite los omiten,
    # lo cual NO es una infactibilidad real (toda la demanda se sirve, capacidad OK).
    clientes_pos = {c for c in range(1, n + 1) if inst.demands[c] > 0}
    todos_pos_servidos = clientes_pos.issubset(set_servidos)
    no_servidos_demanda_cero = (n - len(set_servidos))

    return {
        "total_cost": total_cost,
        "total_distance": round(total_dist_km, 4),
        "total_time": round(total_time_min, 3),
        "feasibility": feasibility,
        "constraint_violation_rate": cvr,
        "time_window_violations": int(tw_violaciones),
        "otd_benchmark": otd,
        "vehicle_utilization": vehicle_utilization,
        "demand_fulfillment": demand_fulfillment,
        "n_clientes_servidos": len(set_servidos),
        "n_vehiculos_usados": vehiculos_usados,
        "capacidad_violaciones": cap_violaciones,
        "todos_los_clientes_servidos": todos_pos_servidos,
        "clientes_no_servidos_demanda_cero": no_servidos_demanda_cero,
    }


def _tipos(inst: CanonicalInstance) -> Dict[str, str]:
    sub = str(inst.metadata.get("subset_name", ""))
    problem = "TWCVRP" if sub.startswith("twvrp_") else ("CVRP" if sub.startswith("cvrp_") else "NA")
    if "multi_depot" in sub or "depots_equal_city" in sub:
        depot = "multi_depot"
    elif "single_depot" in sub:
        depot = "single_depot"
    else:
        depot = "NA"
    vehicle = "multi_vehicle" if inst.num_vehicles > 1 else "single_vehicle"
    return {"problem_type": problem, "depot_type": depot, "vehicle_type": vehicle}


def construir_salida(model_name: str, inst: CanonicalInstance, run_id, rutas_cliente,
                     runtime_seconds: float, error_message: str = "",
                     scenario: Optional[int] = None) -> Dict:
    """Estructura de salida UNICA para todos los modelos (instruccion 16 + Fase 8).

    `scenario` (id de realizacion) activa el scoring estocastico. `status` se deriva:
    success / failed (error) / infeasible (viola capacidad o no sirve toda la demanda).
    """
    tt = _tipos(inst)
    base = {
        "model_name": model_name,
        "instance_id": inst.instance_uid,
        "instance_size": inst.size,
        "problem_type": tt["problem_type"],
        "depot_type": tt["depot_type"],
        "vehicle_type": tt["vehicle_type"],
        "run_id": run_id,
        "total_cost": None, "total_distance": None, "total_time": None,
        "runtime_seconds": round(float(runtime_seconds), 4),
        "feasibility": None, "constraint_violation_rate": None,
        "time_window_violations": None, "otd_benchmark": None,
        "vehicle_utilization": None, "demand_fulfillment": None,
        "robustness_inputs": None,
        "error_message": error_message,
        "status": "failed" if error_message else "success",
    }
    if error_message:
        return base
    m = calcular_metricas(rutas_cliente, inst, scenario=scenario)
    base.update({k: m[k] for k in (
        "total_cost", "total_distance", "total_time", "feasibility",
        "constraint_violation_rate", "time_window_violations", "otd_benchmark",
        "vehicle_utilization", "demand_fulfillment")})
    if m["capacidad_violaciones"] > 0 or not m["todos_los_clientes_servidos"]:
        base["status"] = "infeasible"
    base["robustness_inputs"] = [m["total_cost"]]
    base["_detalle"] = m
    return base


# --------------------------------------------------------------------------- #
# Robustness (preparada para Fase 8)
# --------------------------------------------------------------------------- #
def robustness_desde_realizaciones(costos: List[float]) -> Optional[float]:
    """Variabilidad del costo total entre realizaciones estocasticas (desv. estandar).

    Devuelve None si hay menos de 2 realizaciones.
    """
    vals = [c for c in (costos or []) if c is not None]
    if len(vals) < 2:
        return None
    return round(float(np.std(vals, ddof=0)), 4)


# Columnas definitivas de la tabla de resultados (orden canonico).
COLUMNAS_RESULTADO = [
    "model_name", "instance_id", "instance_size", "problem_type", "depot_type",
    "vehicle_type", "run_id",
    "total_cost", "total_distance", "total_time", "runtime_seconds",
    "feasibility", "constraint_violation_rate", "time_window_violations",
    "otd_benchmark", "vehicle_utilization", "demand_fulfillment",
    "robustness_inputs", "error_message", "status",
]
