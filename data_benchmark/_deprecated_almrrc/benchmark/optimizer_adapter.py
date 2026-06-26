"""Adaptador del motor de optimizacion del DSS para casos benchmark.

Reutiliza EXACTAMENTE la misma estrategia de solver que el DSS
(`optimization/route_optimizer_ortools.py`): OR-Tools con
`PATH_CHEAPEST_ARC` + `GUIDED_LOCAL_SEARCH`. La diferencia es la entrada:
aqui se usa la MATRIZ REAL de tiempos del ALM RRC y el depot propio de cada ruta,
en lugar de la matriz euclidiana y el almacen de Callao. Asi el benchmark mide la
calidad de secuenciacion del mismo motor sobre datos de literatura, sin alterar el
optimizador del DSS.

Modelo: ruta abierta de un solo vehiculo (TSP). El vehiculo parte del depot y NO
esta obligado a regresar (coste de retorno al depot = 0), porque en ALM RRC la
secuencia de entrega no incluye el regreso. Ventanas horarias: opcionales y solo
donde son confiables (por defecto desactivadas, ver instruccion de alcance).

Si OR-Tools no esta disponible o no encuentra solucion, degrada a un greedy
nearest-neighbor por tiempo real (mismo espiritu que el fallback del DSS).
"""
import time
from typing import Dict, List

from benchmark.adapter import CasoBenchmark

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    _ORTOOLS_OK = True
except Exception:
    _ORTOOLS_OK = False


def ortools_disponible() -> bool:
    return _ORTOOLS_OK


def _matriz_segundos(caso: CasoBenchmark):
    """Matriz NxN en segundos enteros (incluye servicio en el nodo origen)."""
    nodos = caso.nodos
    n = len(nodos)
    idx = {s: i for i, s in enumerate(nodos)}
    viaje = [[0] * n for _ in range(n)]
    for i, o in enumerate(nodos):
        for j, d in enumerate(nodos):
            if i == j:
                continue
            viaje[i][j] = int(round(caso.tiempo(o, d) * 60.0))
    servicio = [int(round(caso.servicio_min.get(s, 0.0) * 60.0)) for s in nodos]
    return idx, viaje, servicio


def _greedy(caso: CasoBenchmark) -> List[str]:
    """Nearest-neighbor por tiempo de viaje real desde el depot."""
    pendientes = list(caso.stops_entrega)
    orden = []
    actual = caso.depot_stop_id
    while pendientes:
        siguiente = min(pendientes, key=lambda s: caso.tiempo(actual, s))
        orden.append(siguiente)
        actual = siguiente
        pendientes.remove(siguiente)
    return orden


def optimizar_secuencia(caso: CasoBenchmark, motor: str = "auto",
                        time_limit_seconds: int = 10,
                        usar_ventanas: bool = False) -> Dict:
    """Optimiza la secuencia de entrega de una ruta benchmark.

    Args:
        motor: "ortools", "greedy" o "auto" (intenta ortools y degrada a greedy).
        time_limit_seconds: limite de busqueda para OR-Tools.
        usar_ventanas: si True, aplica ventanas horarias confiables como restriccion.

    Devuelve dict: secuencia_propuesta, motor_usado, tiempo_computo_seg, status.
    """
    t_ini = time.perf_counter()

    if caso.n_paradas <= 1:
        return {
            "secuencia_propuesta": list(caso.stops_entrega),
            "motor_usado": "trivial",
            "tiempo_computo_seg": 0.0,
            "status": "ok",
        }

    if motor in ("ortools", "auto") and _ORTOOLS_OK:
        try:
            orden = _resolver_ortools(caso, time_limit_seconds, usar_ventanas)
            if orden:
                return {
                    "secuencia_propuesta": orden,
                    "motor_usado": "ortools",
                    "tiempo_computo_seg": round(time.perf_counter() - t_ini, 3),
                    "status": "ok",
                }
        except Exception as e:  # noqa: BLE001
            if motor == "ortools":
                return {
                    "secuencia_propuesta": [],
                    "motor_usado": "ortools",
                    "tiempo_computo_seg": round(time.perf_counter() - t_ini, 3),
                    "status": f"error_ortools: {e}",
                }
        # auto: cae a greedy

    orden = _greedy(caso)
    return {
        "secuencia_propuesta": orden,
        "motor_usado": "greedy",
        "tiempo_computo_seg": round(time.perf_counter() - t_ini, 3),
        "status": "ok",
    }


def _resolver_ortools(caso: CasoBenchmark, time_limit_seconds: int,
                      usar_ventanas: bool) -> List[str]:
    idx, viaje, servicio = _matriz_segundos(caso)
    nodos = caso.nodos
    n = len(nodos)
    depot = 0

    manager = pywrapcp.RoutingIndexManager(n, 1, depot)
    routing = pywrapcp.RoutingModel(manager)

    def transit(from_index, to_index):
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        # Ruta abierta: el regreso al depot no cuesta (no es parte de la secuencia).
        if j == depot:
            return 0
        return viaje[i][j] + servicio[i]

    transit_idx = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    if usar_ventanas:
        horizonte = 24 * 3600
        routing.AddDimension(transit_idx, horizonte, horizonte, False, "Time")
        time_dim = routing.GetDimensionOrDie("Time")
        for s, (i_node) in idx.items():
            v = caso.ventanas.get(s)
            index = manager.NodeToIndex(i_node)
            if v is not None:
                ini = int(round(v[0] * 60))
                fin = int(round(v[1] * 60))
                try:
                    time_dim.CumulVar(index).SetRange(max(0, ini), max(ini + 1, fin))
                except Exception:
                    pass

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(int(max(1, time_limit_seconds)))

    solution = routing.SolveWithParameters(params)
    if solution is None:
        return []

    orden = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node != depot:
            orden.append(nodos[node])
        index = solution.Value(routing.NextVar(index))
    return orden
