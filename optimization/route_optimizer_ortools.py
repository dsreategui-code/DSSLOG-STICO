"""Optimizador CVRPTW basado en Google OR-Tools.

Resuelve simultaneamente:
  - asignacion de pedidos a vehiculos (capacity-constrained)
  - secuenciacion con ventanas horarias (time-window-constrained)
  - minimizacion del tiempo total + penalizacion por tardanza

Expone la misma API que el optimizador greedy (`construir_rutas_iniciales`)
para que sea drop-in replacement. Si OR-Tools no esta disponible o no encuentra
solucion en el tiempo limite, devuelve None y el codigo cliente puede degradar
al optimizador greedy.
"""
from dataclasses import asdict
from typing import Dict, List, Optional
import math
import pandas as pd

from config.settings import ALMACEN
from optimization.route_optimizer import Ruta, _dist_km
from utils.formatters import hhmm_to_minutes

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    ORTOOLS_AVAILABLE = True
except Exception:
    ORTOOLS_AVAILABLE = False


def is_available() -> bool:
    return ORTOOLS_AVAILABLE


def _build_distance_time_matrices(pedidos: pd.DataFrame, velocidad_kmh: float):
    """Construye matrices indexadas [0=almacen, 1..N=pedidos]."""
    n = len(pedidos)
    coords = [(ALMACEN["latitud"], ALMACEN["longitud"])] + list(
        zip(pedidos["latitud"], pedidos["longitud"])
    )
    dist = [[0] * (n + 1) for _ in range(n + 1)]
    tiempo = [[0] * (n + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(n + 1):
            if i == j:
                continue
            d = _dist_km(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
            t = (d / max(velocidad_kmh, 1.0)) * 60.0
            dist[i][j] = int(round(d * 1000))   # metros (entero)
            tiempo[i][j] = max(1, int(round(t)))
    return dist, tiempo


def construir_rutas_or_tools(pedidos: pd.DataFrame, vehiculos: pd.DataFrame,
                             velocidad_kmh: float = 18.0,
                             jornada_inicio: str = "09:00",
                             jornada_fin: str = "19:00",
                             time_limit_seconds: int = 8,
                             slack_minutos: int = 30,
                             ) -> Optional[Dict[str, Ruta]]:
    """Resuelve CVRPTW con OR-Tools.

    Devuelve dict {vehiculo_id: Ruta} o None si no fue posible obtener solucion.
    """
    if not ORTOOLS_AVAILABLE:
        return None
    if pedidos is None or pedidos.empty or vehiculos is None or vehiculos.empty:
        return None

    pedidos_idx = pedidos.reset_index(drop=True)
    n = len(pedidos_idx)
    num_vehicles = len(vehiculos)

    # Indices: 0 = almacen (deposito), 1..n = pedidos
    dist_mat, time_mat = _build_distance_time_matrices(pedidos_idx, velocidad_kmh)

    # Capacidades (unidades y kg) por vehiculo
    capacidades_u = [int(v) for v in vehiculos["capacidad_unidades"].tolist()]
    capacidades_kg = [int(v) for v in vehiculos["capacidad_kg"].tolist()]
    demanda_u = [0] + [1] * n
    demanda_kg = [0] + [int(round(float(p))) for p in pedidos_idx["peso_kg"].tolist()]

    # Ventanas horarias en minutos desde el inicio de jornada (0..600 si 09-19)
    t0 = hhmm_to_minutes(jornada_inicio)
    horizonte = hhmm_to_minutes(jornada_fin) - t0
    ventanas = [(0, horizonte)]
    tiempos_servicio = [0]
    for _, p in pedidos_idx.iterrows():
        ini = max(0, hhmm_to_minutes(p["ventana_inicio"]) - t0 - slack_minutos)
        fin = min(horizonte, hhmm_to_minutes(p["ventana_fin"]) - t0 + slack_minutos)
        ventanas.append((ini, fin))
        tiempos_servicio.append(int(round(float(p["tiempo_servicio_min"]))))

    manager = pywrapcp.RoutingIndexManager(n + 1, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Coste = tiempo de viaje (en minutos)
    def time_callback(from_index, to_index):
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        return time_mat[i][j] + tiempos_servicio[i]

    transit_idx = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # Dimension de tiempo con ventanas
    routing.AddDimension(
        transit_idx,
        slack_max=slack_minutos,
        capacity=horizonte + slack_minutos,
        fix_start_cumul_to_zero=False,
        name="Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")
    for node in range(n + 1):
        index = manager.NodeToIndex(node)
        ini, fin = ventanas[node]
        time_dim.CumulVar(index).SetRange(ini, fin)

    # Capacidad unidades
    def demand_units_callback(from_index):
        return demanda_u[manager.IndexToNode(from_index)]

    units_idx = routing.RegisterUnaryTransitCallback(demand_units_callback)
    routing.AddDimensionWithVehicleCapacity(
        units_idx, 0, capacidades_u, True, "Units",
    )

    # Capacidad kg
    def demand_kg_callback(from_index):
        return demanda_kg[manager.IndexToNode(from_index)]

    kg_idx = routing.RegisterUnaryTransitCallback(demand_kg_callback)
    routing.AddDimensionWithVehicleCapacity(
        kg_idx, 0, capacidades_kg, True, "Kg",
    )

    # Permitir dropear pedidos con penalizacion alta (mejor entregar que dejar fuera)
    penalty = 1_000_000
    for node in range(1, n + 1):
        routing.AddDisjunction([manager.NodeToIndex(node)], penalty)

    # Parametros de busqueda
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(int(time_limit_seconds))

    solution = routing.SolveWithParameters(params)
    if solution is None:
        return None

    veh_ids = vehiculos["vehiculo_id"].tolist()
    pedidos_ids = pedidos_idx["pedido_id"].tolist()
    rutas: Dict[str, Ruta] = {v: Ruta(vehiculo_id=v, secuencia=[]) for v in veh_ids}

    for veh_i, veh_id in enumerate(veh_ids):
        index = routing.Start(veh_i)
        secuencia = []
        carga_kg = 0.0
        dist_total_m = 0
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            next_index = solution.Value(routing.NextVar(index))
            next_node = manager.IndexToNode(next_index)
            if node != 0:
                pid = pedidos_ids[node - 1]
                secuencia.append(pid)
                carga_kg += float(pedidos_idx.iloc[node - 1]["peso_kg"])
            dist_total_m += dist_mat[node][next_node]
            index = next_index

        tiempo_total = solution.Value(time_dim.CumulVar(index))
        rutas[veh_id] = Ruta(
            vehiculo_id=veh_id,
            secuencia=secuencia,
            distancia_km=round(dist_total_m / 1000.0, 2),
            tiempo_min=round(float(tiempo_total), 1),
            carga_unidades=len(secuencia),
            carga_kg=round(carga_kg, 1),
        )
    return rutas
