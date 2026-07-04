"""Optimizador CVRPTW del motor CORTEX-LM (matrix-driven, con perfiles de decision).

A diferencia de optimization/route_optimizer_ortools.py (que recomputa la matriz desde
lat/lon y alimenta el flujo actual de la app), este resolvedor:
  - consume una MATRIZ CONTEXTUAL de tiempos ya construida (minutos) + matriz de distancias;
  - soporta DOBLE capacidad (volumen m3 y peso kg);
  - aplica PERFILES DE DECISION que modulan penalizaciones REALES del modelo (tardanza,
    riesgo de incumplimiento, balance de carga), no solo etiquetas;
  - permite esperar a que abra una ventana (espera_max_min), comportamiento CVRPTW estandar.

Resuelve con OR-Tools (PATH_CHEAPEST_ARC + Guided Local Search). Trabaja con heuristicas y
metaheuristicas: produce soluciones de buena calidad bajo el limite de tiempo, NO optimos
garantizados. Si no encuentra solucion, lo informa; permite descartar pedidos con
penalizacion muy alta solo si son infactibles dentro de las ventanas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.data_models import PerfilDecision, Parametros

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    ORTOOLS_OK = True
except Exception:  # noqa: BLE001
    ORTOOLS_OK = False

ESCALA = 100            # escala entero para tiempos/costos (sub-minuto)
MARGEN_RIESGO_MIN = 20  # margen antes del cierre de ventana penalizado por w_riesgo


@dataclass
class ParadaRuta:
    idx_nodo: int
    pedido_id: str
    eta_min: float            # minutos desde el inicio de jornada (arribo)
    carga_m3_acum: float
    carga_kg_acum: float
    tardanza_min: float
    distancia_km_acum: float


@dataclass
class RutaCandidata:
    vehiculo_id: str
    secuencia: List[ParadaRuta] = field(default_factory=list)
    distancia_km: float = 0.0
    tiempo_min: float = 0.0            # cumul de tiempo al FIN de la ruta (min desde jornada)
    tardanza_total_min: float = 0.0
    inicio_min: float = 0.0           # cumul al INICIO (salida del hub); span = tiempo_min - inicio_min

    @property
    def n_paradas(self) -> int:
        return len(self.secuencia)


@dataclass
class ModeloNumerico:
    """Instancia numerica lista para el resolvedor. Nodo 0 = HUB."""
    tiempo_min: np.ndarray            # NxN (contextual)
    dist_km: np.ndarray               # NxN
    demanda_m3: List[float]
    demanda_kg: List[float]
    ventanas_min: List[Tuple[int, int]]   # por nodo, relativas al inicio de jornada
    servicio_min: List[float]
    pedido_ids: List[str]             # por nodo (nodo 0 = 'HUB')
    num_vehiculos: int
    cap_m3: List[float]               # por vehiculo
    cap_kg: List[float]
    vehiculo_ids: List[str]
    horizonte_min: int
    # Restricciones operativas (opcionales; vacio = sin restriccion):
    requiere_cuadrilla: List[bool] = field(default_factory=list)   # por nodo (0=HUB=False)
    vehiculo_cuadrilla: List[bool] = field(default_factory=list)   # por vehiculo


def resolver_cvrptw(modelo: ModeloNumerico, perfil: PerfilDecision,
                    params: Parametros, buffer_sla_min=None) -> dict:
    """Resuelve el CVRPTW para un perfil. Devuelve dict con rutas, no_servidos y estado.

    `buffer_sla_min`: buffer de seguridad por nodo (VENTANAS PROBABILISTICAS). Si se entrega,
    la penalizacion de riesgo se aplica sobre `cierre - buffer_j` (margen derivado de la
    variabilidad) en vez de un margen fijo -> el plan a priori apunta a un nivel de servicio.
    """
    if not ORTOOLS_OK:
        return {"status": "or-tools-no-disponible", "rutas": {}, "no_servidos": [],
                "perfil": perfil.perfil}

    n = int(modelo.tiempo_min.shape[0])
    nv = int(modelo.num_vehiculos)
    H = int(modelo.horizonte_min)
    espera = max(0, int(params.espera_max_min)) or H

    mgr = pywrapcp.RoutingIndexManager(n, nv, 0)
    routing = pywrapcp.RoutingModel(mgr)

    serv = [int(round(s)) for s in modelo.servicio_min]
    t_int = np.round(modelo.tiempo_min).astype(int)

    # Transito de tiempo = servicio(i) + viaje(i,j); arribo a j = cumul(i)+transito.
    def transito(fi, ti):
        i, j = mgr.IndexToNode(fi), mgr.IndexToNode(ti)
        return int(t_int[i][j] + serv[i])

    t_cb = routing.RegisterTransitCallback(transito)

    # Coste objetivo = tiempo de viaje ponderado por w_tiempo (perfil).
    w_tiempo = max(0.05, float(perfil.w_tiempo))
    def coste(fi, ti):
        i, j = mgr.IndexToNode(fi), mgr.IndexToNode(ti)
        return int(round(t_int[i][j] * ESCALA * w_tiempo))
    c_cb = routing.RegisterTransitCallback(coste)
    routing.SetArcCostEvaluatorOfAllVehicles(c_cb)

    # Dimension de tiempo con ventanas + espera permitida (slack).
    routing.AddDimension(t_cb, espera, H + espera, False, "Tiempo")
    tdim = routing.GetDimensionOrDie("Tiempo")

    coef_tard = int(round(params.penalizacion_tardanza * perfil.w_tardanza * ESCALA))
    coef_riesgo = int(round(params.penalizacion_riesgo * perfil.w_riesgo * ESCALA))
    for node in range(n):
        idx = mgr.NodeToIndex(node)
        ini, fin = modelo.ventanas_min[node]
        ini = max(0, int(ini)); fin = min(H, int(fin))
        tdim.CumulVar(idx).SetRange(ini, max(ini, fin))
        if node != 0:
            # Penalizacion suave por tardanza (arribo despues del cierre).
            if coef_tard > 0:
                tdim.SetCumulVarSoftUpperBound(idx, fin, coef_tard)
            # Penalizacion suave por riesgo: arribar con poco margen al cierre. El margen es
            # el buffer de nivel de servicio (chance-constrained) si se entrega, o fijo.
            if coef_riesgo > 0:
                buf = (int(round(buffer_sla_min[node]))
                       if buffer_sla_min is not None and node < len(buffer_sla_min)
                       else MARGEN_RIESGO_MIN)
                margen = max(ini, fin - buf)
                tdim.SetCumulVarSoftUpperBound(idx, margen, coef_riesgo)

    # Balance de carga entre rutas (w_balance) via penalizacion del span de tiempo.
    if perfil.w_balance > 0:
        tdim.SetGlobalSpanCostCoefficient(int(round(perfil.w_balance * ESCALA)))

    # Doble capacidad: volumen (m3) y peso (kg). Se escalan a entero.
    def _dim_capacidad(demanda, caps, nombre, escala):
        d_int = [int(round(x * escala)) for x in demanda]
        cb = routing.RegisterUnaryTransitCallback(lambda fi, d=d_int: d[mgr.IndexToNode(fi)])
        routing.AddDimensionWithVehicleCapacity(
            cb, 0, [int(round(c * escala)) for c in caps], True, nombre)
    if any(modelo.cap_m3):
        _dim_capacidad(modelo.demanda_m3, modelo.cap_m3, "Vol", 1000)
    if any(modelo.cap_kg):
        _dim_capacidad(modelo.demanda_kg, modelo.cap_kg, "Peso", 1)

    # --- Restricciones operativas ---
    # (1) Jornada MAXIMA del conductor: el span de la ruta (fin - inicio) <= jornada_max.
    jornada_max = int(getattr(params, "jornada_max_min", H) or H)
    if 0 < jornada_max < H:
        for v in range(nv):
            tdim.SetSpanUpperBoundForVehicle(jornada_max, v)

    # (2) Cuadrillas: los pedidos de instalacion solo los pueden atender vehiculos con cuadrilla.
    veh_cuad = list(modelo.vehiculo_cuadrilla or [])
    req_cuad = list(modelo.requiere_cuadrilla or [])
    if veh_cuad and req_cuad and not all(veh_cuad):     # solo si hay una restriccion real
        crew = [v for v in range(nv) if v < len(veh_cuad) and veh_cuad[v]]
        if crew:
            for node in range(1, n):
                if node < len(req_cuad) and req_cuad[node]:
                    routing.SetAllowedVehiclesForIndex(crew, mgr.NodeToIndex(node))

    # (3) Descanso/almuerzo: cada vehiculo toma un break (min) dentro de la ventana de mediodia.
    descanso = int(getattr(params, "descanso_min", 0) or 0)
    if descanso > 0:
        solver = routing.solver()
        visita = [serv[mgr.IndexToNode(i)] for i in range(routing.Size())]
        b_ini = int(getattr(params, "descanso_desde_min", 180))
        b_fin = int(getattr(params, "descanso_hasta_min", 270))
        for v in range(nv):
            brk = solver.FixedDurationIntervalVar(b_ini, b_fin, descanso, False, f"desc_{v}")
            tdim.SetBreakIntervalsOfVehicle([brk], v, visita)

    # Permitir descartar pedidos infactibles con penalizacion muy alta.
    penalty = 10_000_000
    for node in range(1, n):
        routing.AddDisjunction([mgr.NodeToIndex(node)], penalty)

    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    p.time_limit.FromSeconds(int(params.tiempo_solver_seg))

    sol = routing.SolveWithParameters(p)
    if sol is None:
        return {"status": "sin-solucion", "rutas": {}, "no_servidos": list(range(1, n)),
                "perfil": perfil.perfil}

    rutas: Dict[str, RutaCandidata] = {}
    servidos = set()
    for v in range(nv):
        veh_id = modelo.vehiculo_ids[v] if v < len(modelo.vehiculo_ids) else f"V{v+1:03d}"
        idx = routing.Start(v)
        rc = RutaCandidata(vehiculo_id=veh_id)
        carga_m3 = carga_kg = dist_km = 0.0
        while not routing.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            nxt = sol.Value(routing.NextVar(idx))
            nxt_node = mgr.IndexToNode(nxt)
            if node != 0:
                servidos.add(node)
                carga_m3 += modelo.demanda_m3[node]
                carga_kg += modelo.demanda_kg[node]
                eta = sol.Value(tdim.CumulVar(idx))
                _, fin = modelo.ventanas_min[node]
                rc.secuencia.append(ParadaRuta(
                    idx_nodo=node, pedido_id=modelo.pedido_ids[node],
                    eta_min=float(eta), carga_m3_acum=round(carga_m3, 3),
                    carga_kg_acum=round(carga_kg, 2),
                    tardanza_min=float(max(0, eta - fin)),
                    distancia_km_acum=round(dist_km + modelo.dist_km[node][nxt_node], 3)))
            dist_km += float(modelo.dist_km[node][nxt_node])
            idx = nxt
        if rc.secuencia:
            rc.distancia_km = round(dist_km, 3)
            rc.tiempo_min = float(sol.Value(tdim.CumulVar(routing.End(v))))
            rc.inicio_min = float(sol.Value(tdim.CumulVar(routing.Start(v))))
            rc.tardanza_total_min = round(sum(s.tardanza_min for s in rc.secuencia), 2)
            rutas[veh_id] = rc

    no_servidos = [k for k in range(1, n) if k not in servidos]
    return {"status": "ok", "rutas": rutas, "no_servidos": no_servidos,
            "perfil": perfil.perfil}
