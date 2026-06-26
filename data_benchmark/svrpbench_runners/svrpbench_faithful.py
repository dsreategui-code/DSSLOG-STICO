# -*- coding: utf-8 -*-
"""Fase 8-bis - Reconstruccion FIEL del benchmark TWCVRP (SVRPBench).

Corrige los dos defectos de fidelidad detectados al analizar el paper (arXiv:2505.21887):

  1. CAPACIDAD multi-vehiculo real. El parquet `svrpbench_test.parquet` guarda la
     capacidad como `demanda_total` por vehiculo (degenerada -> un vehiculo basta). El
     paper (Seccion 3, "Demand Assignment") fija `cap = total ÷ num_vehicles`. Aqui se
     usa `cap_por_vehiculo = ceil(demanda_total / num_vehicles)`, identico para todos
     los modelos, lo que fuerza ruteo multi-vehiculo genuino.

  2. VENTANAS de tiempo por cliente. El parquet no trae las ventanas (solo `appear_times`
     en cero). Se regeneran con el generador OFICIAL de la suite
     (`time_windows_generator.sample_time_window`, Seccion 2.2 del paper): 60% residencial
     (bimodal manana/tarde) y 40% comercial (mediodia), anchos 1-3 h / 1-2 h, en minutos
     sobre el dia (0..1440). Semilla determinista por instancia -> reproducible.

PUNTUACION COMUN Y FIEL: todas las rutas (DSS y baselines) se evaluan con el evaluador
AUTORITATIVO de la suite (`VRPSolverBase.calculate_solution_cost`), que usa el modelo
estocastico del paper (congestion por hora + retraso log-normal + accidentes Poisson via
`travel_time_generator.sample_travel_time`) en la grilla canonica (1 unidad ~ 1 minuto a
velocidad 1). Asi DSS y baselines se miden EXACTAMENTE igual y de forma fiel al paper.

No toca `data/` ni la logica del DSS. No modifica la suite. Reusa el optimizador del DSS
como libreria, alimentandolo con ventanas + capacidad reales y una escala temporal
consistente con el evaluador.
"""
from __future__ import annotations

import math
import random
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

RUNNERS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = RUNNERS_DIR.parent.parent
SUITE_DIR = RUNNERS_DIR.parent / "svrpbench_evaluation_suite"
SCRIPTS_DIR = RUNNERS_DIR.parent / "svrpbench_scripts"
for p in (str(PROJECT_ROOT), str(RUNNERS_DIR), str(SCRIPTS_DIR),
          str(SUITE_DIR), str(SUITE_DIR / "vrp_bench")):
    if p not in sys.path:
        sys.path.insert(0, p)

RAW_PARQUET = RUNNERS_DIR.parent / "svrpbench_raw" / "svrpbench_test.parquet"

# Supuestos del paper.
COMMERCIAL_FRAC = 0.40          # 40% comercial, 60% residencial (paper, pag. 5)
JORNADA_MAX_MIN = 1439          # dia completo (0..1439 min)


# --------------------------------------------------------------------------- #
# 1) Instancia fiel
# --------------------------------------------------------------------------- #
def _raw_row(uid: str) -> pd.Series:
    subset_name, idx = str(uid).rsplit("__", 1)
    raw = pd.read_parquet(RAW_PARQUET)
    g = raw[raw["subset_name"] == subset_name]
    hit = g[g["instance_id"].astype(str) == str(idx)]
    if hit.empty:
        raise KeyError(f"Instancia '{uid}' no esta en {RAW_PARQUET.name}.")
    return hit.iloc[0]


def instancia_fiel(uid: str) -> dict:
    """Construye la instancia TWCVRP fiel: capacidad real + ventanas por cliente."""
    from time_windows_generator import sample_time_window

    r = _raw_row(uid)
    locs = np.array([np.array(p, dtype=float) for p in r["locations"]], dtype=float)
    dem = np.array(r["demands"], dtype=float)
    nveh = int(r["num_vehicles"])
    total = float(dem.sum())
    cap = math.ceil(total / max(nveh, 1))           # paper: total / num_vehicles
    caps = np.full(nveh, float(cap), dtype=float)
    n = len(dem)

    # Ventanas por cliente, semilladas de forma determinista por uid (reproducible).
    np.random.seed(zlib.crc32(str(uid).encode("utf-8")) & 0xFFFFFFFF)
    tw = np.zeros((n, 2), dtype=float)
    ctypes = np.full(n, -1, dtype=int)              # -1 = deposito/demanda 0
    for i in range(n):
        if i == 0 or dem[i] <= 0:
            tw[i] = [0.0, float(JORNADA_MAX_MIN)]    # deposito / demanda 0: abierto
            continue
        ctype = 1 if np.random.uniform() < COMMERCIAL_FRAC else 0
        ctypes[i] = ctype
        s, e = sample_time_window(ctype, 0)
        tw[i] = [float(max(0, min(s, JORNADA_MAX_MIN))),
                 float(max(0, min(e, JORNADA_MAX_MIN)))]

    return {
        "uid": str(uid), "subset_name": str(r["subset_name"]),
        "instance_id": int(r["instance_id"]), "size": int(r.get("size_declarado", n - 1)),
        "locations": locs, "demands": dem, "vehicle_capacities": caps,
        "num_vehicles": nveh, "time_windows": tw, "customer_types": ctypes,
        "total_demand": total, "cap_por_vehiculo": int(cap), "n_customers": n - 1,
    }


def _suite_instance(fiel: dict):
    from vrp_bench.core import Instance
    n = len(fiel["demands"])
    return Instance(
        locations=fiel["locations"], demands=fiel["demands"],
        vehicle_capacities=fiel["vehicle_capacities"], num_vehicles=fiel["num_vehicles"],
        time_windows=fiel["time_windows"], appear_times=np.zeros(n),
    )


# --------------------------------------------------------------------------- #
# 2) Puntuacion comun y fiel (evaluador autoritativo de la suite)
# --------------------------------------------------------------------------- #
def _dist_grid(a: int, b: int, locs: np.ndarray) -> float:
    return float(np.hypot(*(locs[a] - locs[b])))


def _distancia_total(rutas_nodos, locs) -> float:
    tot = 0.0
    for ruta in rutas_nodos:
        for i in range(len(ruta) - 1):
            tot += _dist_grid(ruta[i], ruta[i + 1], locs)
    return tot


def _otd_deterministico(rutas_nodos, fiel) -> tuple:
    """OTD a-priori (sin ruido): fraccion de clientes servidos dentro de ventana,
    con el plan deterministico (viaje = distancia de grilla, esperando apertura)."""
    locs, tw, dem = fiel["locations"], fiel["time_windows"], fiel["demands"]
    a_tiempo = 0
    servidos = 0
    tarde = 0
    for ruta in rutas_nodos:
        t = 0.0
        for i in range(1, len(ruta)):
            prev, node = ruta[i - 1], ruta[i]
            t += _dist_grid(prev, node, locs)
            if node == 0 or dem[node] <= 0:
                continue
            servidos += 1
            ini, fin = tw[node]
            if t < ini:
                t = ini                      # espera apertura
            if t <= fin + 1e-6:
                a_tiempo += 1
            else:
                tarde += 1
    otd = round(a_tiempo / servidos, 4) if servidos else 0.0
    return otd, tarde


def score_rutas(fiel: dict, rutas_nodos, num_realizations: int = 5,
                seed: int = 0) -> dict:
    """Puntua rutas (lista de [0, c.., 0]) con el evaluador de la suite + extras.

    `seed` semilla el muestreo estocastico para que TODOS los modelos enfrenten el
    mismo ruido en una instancia (comparacion justa)."""
    from nn_2opt_solver import NN2optSolver

    inst = _suite_instance(fiel)
    base = NN2optSolver(inst.to_legacy_dict())
    base.debug = False

    random.seed(seed)
    np.random.seed(seed)
    m = base.calculate_solution_cost(rutas_nodos, 0, num_realizations)

    locs = fiel["locations"]
    total_distance = round(_distancia_total(rutas_nodos, locs), 4)
    otd, tarde_det = _otd_deterministico(rutas_nodos, fiel)
    n_rutas = len([r for r in rutas_nodos if any(x != 0 for x in r)])
    return {
        "total_cost": round(float(m.get("total_cost", 0.0)), 4),
        "total_distance": total_distance,
        "waiting_time": round(float(m.get("waiting_time", 0.0)), 4),
        "cvr": round(float(m.get("cvr", 0.0)), 4),
        "feasibility": float(m.get("feasibility", 0.0)),
        "robustness": round(float(m.get("robustness", 0.0)), 4),
        "time_window_violations": int(m.get("time_window_violations", 0)),
        "otd": otd,
        "tw_violations_deterministico": int(tarde_det),
        "n_rutas": n_rutas,
    }


# --------------------------------------------------------------------------- #
# 3) Helpers de formato de rutas
# --------------------------------------------------------------------------- #
def con_deposito(rutas_cliente) -> list:
    """[[c1,c2],...] (indices de cliente 1..N) -> [[0,c1,c2,0],...] para el evaluador."""
    out = []
    for ruta in rutas_cliente or []:
        limpia = [int(c) for c in ruta if int(c) != 0]
        if limpia:
            out.append([0] + limpia + [0])
    return out


# --------------------------------------------------------------------------- #
# 4) Solvers -> rutas (formato comun [0, c.., 0])
# --------------------------------------------------------------------------- #
# Escala temporal del DSS: el evaluador usa 1 unidad de grilla ~ 1 minuto (velocidad 1).
# El DSS calcula tiempo = dist_km / vel_kmh * 60, con dist_km = unidades * KM_POR_UNIDAD.
# Para que el plan del DSS use 1 min por unidad: KM_POR_UNIDAD = vel_kmh / 60.
_DSS_VEL_KMH = 18.0
_DSS_KM_POR_UNIDAD = _DSS_VEL_KMH / 60.0       # = 0.30 -> 1 unidad de grilla = 1 min
_JORNADA_INI = "00:00"
_JORNADA_FIN = "23:59"
_FLOTA_FACTOR = 2                               # holgura de flota (la suite no limita nº de rutas)


def _min_a_hhmm(m: float) -> str:
    m = int(round(max(0, min(JORNADA_MAX_MIN, m))))
    return f"{m // 60:02d}:{m % 60:02d}"


def _latlon(px, py, dx, dy):
    from config.settings import ALMACEN
    off_x = (px - dx) * _DSS_KM_POR_UNIDAD
    off_y = (py - dy) * _DSS_KM_POR_UNIDAD
    lat = ALMACEN["latitud"] + off_y / 111.0
    lon = ALMACEN["longitud"] + off_x / (111.0 * math.cos(math.radians(ALMACEN["latitud"])))
    return round(lat, 6), round(lon, 6)


def _dataframes_dss(fiel: dict):
    """Construye (pedidos, vehiculos) del DSS con ventanas + capacidad reales."""
    locs, dem, tw = fiel["locations"], fiel["demands"], fiel["time_windows"]
    dx, dy = locs[0]
    filas = []
    for i in range(1, len(locs)):
        lat, lon = _latlon(locs[i][0], locs[i][1], dx, dy)
        filas.append({
            "pedido_id": f"C{i:04d}", "cliente": f"cliente_{i}",
            "distrito": "ALM", "zona": "ALM", "modelo": "benchmark",
            "peso_kg": float(dem[i]), "tipo_servicio": "Estandar",
            "tiempo_servicio_min": 0.0,
            "ventana_inicio": _min_a_hhmm(tw[i][0]), "ventana_fin": _min_a_hhmm(tw[i][1]),
            "latitud": lat, "longitud": lon,
        })
    pedidos = pd.DataFrame(filas)
    n_veh = max(1, int(fiel["num_vehicles"]) * _FLOTA_FACTOR)
    cap = float(fiel["cap_por_vehiculo"])
    vehiculos = pd.DataFrame([{
        "vehiculo_id": f"V{v+1:03d}", "placa": f"BMK-{v+1:03d}",
        "capacidad_unidades": int(fiel["n_customers"]), "capacidad_kg": cap,
        "zona_preferente": "ALM", "conductor": "benchmark",
    } for v in range(n_veh)])
    return pedidos, vehiculos


def solve_dss(fiel: dict, time_limit_seconds: int = 10, slack_minutos: int = 0):
    """Optimiza con el DSS (CVRPTW real). Devuelve (rutas_nodos, runtime, error).

    `slack_minutos=0`: el DSS respeta las ventanas VERDADERAS (sin ensanchar), igual que
    el evaluador. Se llama directo a `construir_rutas_or_tools` para fijar el slack;
    degrada al greedy del DSS si OR-Tools no esta disponible o no halla solucion."""
    try:
        from optimization.route_optimizer_ortools import (
            construir_rutas_or_tools, is_available)
        from optimization.route_optimizer import construir_rutas_iniciales
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"optimizador DSS no disponible: {e}"
    try:
        pedidos, vehiculos = _dataframes_dss(fiel)
        t0 = time.perf_counter()
        rutas = None
        if is_available():
            # factor_balance = _FLOTA_FACTOR: la flota es FLOTA_FACTOR x num_vehicles, asi que
            # se balancea la carga al nivel del fleet NATURAL del paper (num_vehicles), dejando
            # vehiculos de sobra para reparaciones sin forzar rutas artificialmente finas.
            rutas = construir_rutas_or_tools(
                pedidos, vehiculos, velocidad_kmh=_DSS_VEL_KMH,
                jornada_inicio=_JORNADA_INI, jornada_fin=_JORNADA_FIN,
                slack_minutos=slack_minutos, time_limit_seconds=time_limit_seconds,
                factor_balance=float(_FLOTA_FACTOR))
        if rutas is None:
            rutas = construir_rutas_iniciales(
                pedidos, vehiculos, motor="greedy", velocidad_kmh=_DSS_VEL_KMH,
                jornada_inicio=_JORNADA_INI, jornada_fin=_JORNADA_FIN)
        runtime = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"ejecucion DSS fallida: {e}"
    rutas_cliente = []
    for r in rutas.values():
        seq = getattr(r, "secuencia", None)
        if not seq:
            continue
        idx = [int("".join(ch for ch in str(p) if ch.isdigit()))
               for p in seq if any(ch.isdigit() for ch in str(p))]
        if idx:
            rutas_cliente.append(idx)

    # Cobertura total: los clientes reales que el optimizador no pudo encajar dentro de la
    # ventana estricta se sirven con un viaje DEDICADO (despachador de respaldo). Una ruta
    # de un solo cliente cumple su ventana esperando la apertura; su coste extra se carga al
    # DSS. Asi todos los modelos sirven a TODOS los clientes (decision metodologica Fase 8b).
    servidos = {c for ruta in rutas_cliente for c in ruta}
    reales = {i for i in range(1, len(fiel["demands"])) if fiel["demands"][i] > 0}
    faltan = sorted(reales - servidos)
    for c in faltan:
        rutas_cliente.append([c])
    return con_deposito(rutas_cliente), runtime, "", len(faltan)


def solve_ortools_tw(fiel: dict, time_limit_seconds: int = 10):
    """Baseline OR-Tools TWCVRP independiente: respeta ventanas REALES + capacidad, con
    espera generosa (CVRPTW estandar). Devuelve (rutas_nodos, runtime, error, 0).

    A diferencia del 'or-tools' registrado de la suite (solo capacidad), este SI usa las
    ventanas; es un rival fuerte y justo para el DSS. Misma grilla (1 unidad = 1 min)."""
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"ortools no disponible: {e}", 0
    locs = fiel["locations"]; dem = fiel["demands"]; tw = fiel["time_windows"]
    n = len(locs)
    cap = int(fiel["cap_por_vehiculo"])
    nveh = max(1, int(fiel["num_vehicles"]) * _FLOTA_FACTOR)
    horizon = JORNADA_MAX_MIN
    # Matriz de tiempos = distancia de grilla (entero), 1 unidad = 1 minuto.
    tm = [[int(round(_dist_grid(i, j, locs))) for j in range(n)] for i in range(n)]
    demands = [int(round(dem[i])) for i in range(n)]
    try:
        t0 = time.perf_counter()
        mgr = pywrapcp.RoutingIndexManager(n, nveh, 0)
        routing = pywrapcp.RoutingModel(mgr)
        tcb = routing.RegisterTransitCallback(
            lambda fi, ti: tm[mgr.IndexToNode(fi)][mgr.IndexToNode(ti)])
        routing.SetArcCostEvaluatorOfAllVehicles(tcb)
        routing.AddDimension(tcb, horizon, horizon * 2, False, "Time")
        tdim = routing.GetDimensionOrDie("Time")
        for node in range(n):
            idx = mgr.NodeToIndex(node)
            lo, hi = (0, horizon) if (node == 0 or dem[node] <= 0) else tw[node]
            tdim.CumulVar(idx).SetRange(int(lo), int(hi))
        dcb = routing.RegisterUnaryTransitCallback(
            lambda fi: demands[mgr.IndexToNode(fi)])
        routing.AddDimensionWithVehicleCapacity(dcb, 0, [cap] * nveh, True, "Cap")
        penalty = 10_000_000
        for node in range(1, n):
            if dem[node] > 0:
                routing.AddDisjunction([mgr.NodeToIndex(node)], penalty)
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        params.time_limit.FromSeconds(int(time_limit_seconds))
        sol = routing.SolveWithParameters(params)
        runtime = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"or-tools-tw fallido: {type(e).__name__}: {e}", 0
    if sol is None:
        return None, runtime, "or-tools-tw sin solucion", 0
    rutas = []
    for v in range(nveh):
        idx = routing.Start(v); clientes = []
        while not routing.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            if node != 0:
                clientes.append(node)
            idx = sol.Value(routing.NextVar(idx))
        if clientes:
            rutas.append([0] + clientes + [0])
    # Cobertura total: reparar clientes reales no servidos (mismo criterio que el DSS).
    servidos = {c for r in rutas for c in r if c != 0}
    reales = {i for i in range(1, n) if dem[i] > 0}
    nrep = 0
    for c in sorted(reales - servidos):
        rutas.append([0, c, 0]); nrep += 1
    return rutas, runtime, "", nrep


def solve_suite(solver_id: str, fiel: dict):
    """Optimiza con un solver de la suite. Devuelve (rutas_nodos, runtime, error)."""
    try:
        from vrp_bench.core import get_solver, list_solvers
        if solver_id not in list_solvers():
            return None, 0.0, f"solver '{solver_id}' no registrado"
        inst = _suite_instance(fiel)
        solver = get_solver(solver_id)()
        t0 = time.perf_counter()
        sol = solver.solve(inst, num_realizations=1)
        runtime = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001
        return None, 0.0, f"ejecucion suite fallida: {type(e).__name__}: {e}"
    rutas = []
    for r in (getattr(sol, "routes", None) or []):
        seq = [int(x) for x in r]
        clientes = [c for c in seq if c != 0]
        if clientes:
            rutas.append([0] + clientes + [0])
    return rutas, runtime, ""


if __name__ == "__main__":
    f = instancia_fiel("twvrp_50_single_depot__0")
    print(f"uid={f['uid']} n_clientes={f['n_customers']} nveh={f['num_vehicles']} "
          f"cap/veh={f['cap_por_vehiculo']} (total={f['total_demand']:.0f})")
    anchos = [f["time_windows"][i, 1] - f["time_windows"][i, 0]
              for i in range(len(f["demands"])) if f["demands"][i] > 0]
    print(f"ventanas: ancho medio={np.mean(anchos):.0f} min  "
          f"comercial={int((f['customer_types'] == 1).sum())}/"
          f"{int((f['customer_types'] >= 0).sum())}")
