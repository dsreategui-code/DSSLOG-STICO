"""Replanificacion dinamica intra-vehiculo con horizonte limitado (CORTEX-LM).

Ante retraso, incidencia o riesgo alto de incumplimiento, recalcula SOLO los pedidos
PENDIENTES del vehiculo afectado (custodia logistica: no hay trasiego entre camiones),
congelando el pasado y partiendo de un origen virtual (posicion y tiempo actuales).

Evalua tres alternativas:
  A) Mantener la ruta actual (orden pendiente sin cambios).
  B) Reparacion local (or-opt: reubicar paradas proximas).
  C) Reoptimizacion local de los pendientes con OR-Tools, desde el origen virtual.

Penaliza la inestabilidad: solo recomienda replanificar si el beneficio operativo supera
el costo de cambiar la secuencia. Compara ruta actual vs replanificada y emite una
recomendacion explicable. Trabaja con estimaciones; recomienda, no garantiza.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.data_models import Parametros, PerfilDecision
from core.optimizer_ortools import ModeloNumerico, resolver_cvrptw

PENAL_RIESGO = 30.0           # minutos-equivalente por pedido proyectado tarde
PENAL_ESTABILIDAD_MIN = 8.0   # costo (min-equivalente) por cada parada que cambia de orden


@dataclass
class EstadoVehiculo:
    """Estado operativo de un vehiculo a mitad de jornada."""
    vehiculo_id: str
    ruta_planificada: List[int]        # secuencia de nodos (incluye 0=HUB al inicio)
    completadas: List[int] = field(default_factory=list)
    pos_nodo: int = 0                  # posicion actual (ultimo nodo entregado o HUB)
    t_actual_min: float = 0.0          # minutos desde el inicio de jornada
    retraso_acumulado_min: float = 0.0

    def pendientes(self) -> List[int]:
        hechas = set(self.completadas)
        return [n for n in self.ruta_planificada if n != 0 and n not in hechas]


def debe_replanificar(estado: EstadoVehiculo, params: Parametros, *,
                      hay_incidencia: bool = False,
                      iri_pendientes: Optional[Dict[int, float]] = None,
                      proyeccion_incumplimiento: bool = False,
                      forzado: bool = False) -> Tuple[bool, List[str]]:
    """Decide si procede evaluar una replanificacion y por que."""
    motivos = []
    if forzado:
        motivos.append("forzado por el supervisor")
    if estado.retraso_acumulado_min > params.umbral_retraso_replanificar:
        motivos.append(f"retraso acumulado {estado.retraso_acumulado_min:.0f} min "
                       f"> umbral {params.umbral_retraso_replanificar:.0f}")
    if hay_incidencia:
        motivos.append("incidencia activa en la zona/franja")
    if iri_pendientes:
        criticos = [p for p, v in iri_pendientes.items() if v >= params.umbral_riesgo_critico]
        if criticos:
            motivos.append(f"{len(criticos)} pedido(s) con riesgo critico de incumplimiento")
    if proyeccion_incumplimiento:
        motivos.append("proyeccion de incumplimiento de ventanas")
    return (len(motivos) > 0, motivos)


def _proyectar(seq: Sequence[int], origen: int, t0: float, modelo: ModeloNumerico,
               factor: Dict[int, float]) -> dict:
    """Proyeccion DETERMINISTICA de la ejecucion de `seq` desde `origen` a tiempo `t0`
    (minutos desde inicio de jornada). Devuelve tardanza total, nº tarde y detalle."""
    t = float(t0)
    prev = origen
    tardanza_total = 0.0
    tarde = 0
    detalle = []
    for node in seq:
        t += float(modelo.tiempo_min[prev][node]) * factor.get(node, 1.0)
        ini, fin = modelo.ventanas_min[node]
        if t < ini:
            t = ini
        tard = max(0.0, t - fin)
        tardanza_total += tard
        if tard > 1e-6:
            tarde += 1
        detalle.append({"idx_nodo": node, "pedido_id": modelo.pedido_ids[node],
                        "eta_min": round(t, 1), "tardanza_min": round(tard, 1)})
        t += float(modelo.servicio_min[node])
        prev = node
    return {"tardanza_total_min": round(tardanza_total, 1), "n_tarde": tarde,
            "t_fin_min": round(t, 1), "detalle": detalle}


def _costo(proy: dict) -> float:
    return proy["tardanza_total_min"] + PENAL_RIESGO * proy["n_tarde"]


def _cambios_secuencia(a: Sequence[int], b: Sequence[int]) -> int:
    """Nº de posiciones en que difieren dos secuencias de los mismos nodos."""
    return sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))


def _reparacion_local(seq: List[int], origen: int, t0: float, modelo: ModeloNumerico,
                      factor: Dict[int, float]) -> List[int]:
    """Or-opt simple: intenta reubicar cada parada en la mejor posicion (1 pasada)."""
    mejor = list(seq)
    mejor_costo = _costo(_proyectar(mejor, origen, t0, modelo, factor))
    for i in range(len(seq)):
        for j in range(len(seq)):
            if i == j:
                continue
            cand = list(mejor)
            nodo = cand.pop(i)
            cand.insert(j, nodo)
            c = _costo(_proyectar(cand, origen, t0, modelo, factor))
            if c + 1e-9 < mejor_costo:
                mejor, mejor_costo = cand, c
    return mejor


def _submodelo_local(origen: int, pendientes: List[int], t_actual: float,
                     modelo: ModeloNumerico, cap_m3: float, cap_kg: float) -> ModeloNumerico:
    """Construye una instancia de 1 vehiculo desde el origen virtual sobre los pendientes."""
    nodos = [origen] + pendientes
    idx = {n: k for k, n in enumerate(nodos)}
    n = len(nodos)
    tm = np.zeros((n, n)); dm = np.zeros((n, n))
    for a in nodos:
        for b in nodos:
            tm[idx[a]][idx[b]] = modelo.tiempo_min[a][b]
            dm[idx[a]][idx[b]] = modelo.dist_km[a][b]
    H = modelo.horizonte_min
    ventanas = [(0, max(1, int(H - t_actual)))]   # origen virtual: abierto el resto de jornada
    serv = [0.0]
    dem_m3 = [0.0]; dem_kg = [0.0]; pids = ["ORIGEN"]
    for nodo in pendientes:
        ini, fin = modelo.ventanas_min[nodo]
        ventanas.append((max(0, int(ini - t_actual)), max(0, int(fin - t_actual))))
        serv.append(modelo.servicio_min[nodo])
        dem_m3.append(modelo.demanda_m3[nodo])
        dem_kg.append(modelo.demanda_kg[nodo])
        pids.append(modelo.pedido_ids[nodo])
    return ModeloNumerico(
        tiempo_min=tm, dist_km=dm, demanda_m3=dem_m3, demanda_kg=dem_kg,
        ventanas_min=ventanas, servicio_min=serv, pedido_ids=pids,
        num_vehiculos=1, cap_m3=[cap_m3], cap_kg=[cap_kg], vehiculo_ids=["VR"],
        horizonte_min=max(1, int(H - t_actual)))


def _reoptimizacion_local(origen: int, pendientes: List[int], t_actual: float,
                          modelo: ModeloNumerico, params: Parametros,
                          cap_m3: float, cap_kg: float) -> List[int]:
    """Reoptimiza los pendientes con OR-Tools desde el origen virtual. Devuelve el nuevo
    orden de nodos (indices originales). Si falla, devuelve el orden actual de pendientes."""
    sub = _submodelo_local(origen, pendientes, t_actual, modelo, cap_m3, cap_kg)
    perfil = PerfilDecision("puntual", w_tiempo=0.5, w_tardanza=1.0, w_riesgo=0.7)
    p = Parametros(**{**params.__dict__, "tiempo_solver_seg": min(5, params.tiempo_solver_seg)})
    res = resolver_cvrptw(sub, perfil, p)
    if res.get("status") != "ok" or not res.get("rutas"):
        return list(pendientes)
    rc = next(iter(res["rutas"].values()))
    # mapear indices del submodelo de vuelta a indices originales
    nodos = [origen] + pendientes
    orden = [nodos[s.idx_nodo] for s in rc.secuencia]
    # Custodia/cobertura: si el solver descarto algun pendiente (p. ej. ventana ya
    # cerrada), se re-anexa al final preservando su orden. Ningun pedido pendiente del
    # vehiculo se pierde en la replanificacion.
    faltan = [p_ for p_ in pendientes if p_ not in orden]
    return orden + faltan


def replanificar_vehiculo(estado: EstadoVehiculo, modelo: ModeloNumerico, params: Parametros, *,
                          factor_tiempo: Optional[Dict[int, float]] = None,
                          cap_m3: float = 1e9, cap_kg: float = 1e9) -> dict:
    """Evalua A/B/C, penaliza inestabilidad y emite recomendacion explicable."""
    factor = factor_tiempo or {}
    pendientes = estado.pendientes()
    if not pendientes:
        return {"accion": "sin_pendientes", "recomendacion": "Mantener ruta actual",
                "alternativas": {}, "explicacion": "El vehiculo no tiene pedidos pendientes."}

    origen, t0 = estado.pos_nodo, estado.t_actual_min
    seq_A = list(pendientes)
    seq_B = _reparacion_local(seq_A, origen, t0, modelo, factor)
    seq_C = _reoptimizacion_local(origen, pendientes, t0, modelo, params, cap_m3, cap_kg)

    proy = {"A_mantener": _proyectar(seq_A, origen, t0, modelo, factor),
            "B_reparacion": _proyectar(seq_B, origen, t0, modelo, factor),
            "C_reoptimizacion": _proyectar(seq_C, origen, t0, modelo, factor)}
    secuencias = {"A_mantener": seq_A, "B_reparacion": seq_B, "C_reoptimizacion": seq_C}

    costo_A = _costo(proy["A_mantener"])
    # Mejor alternativa de replanificacion (B o C) por costo + penalizacion de inestabilidad.
    candidatos = []
    for k in ("B_reparacion", "C_reoptimizacion"):
        cambios = _cambios_secuencia(seq_A, secuencias[k])
        costo_total = _costo(proy[k]) + PENAL_ESTABILIDAD_MIN * cambios
        candidatos.append((k, costo_total, cambios))
    mejor_k, mejor_costo, mejor_cambios = min(candidatos, key=lambda x: x[1])

    # Aceptar replanificacion solo si el beneficio supera el costo de cambiar.
    beneficio = costo_A - _costo(proy[mejor_k])
    costo_cambio = PENAL_ESTABILIDAD_MIN * mejor_cambios
    aceptar = (beneficio > costo_cambio) and (mejor_cambios > 0)

    if aceptar:
        recomendacion = "Aceptar replanificacion"
        explicacion = (
            f"Se recomienda replanificar ({mejor_k.split('_')[1]}): reduce la tardanza "
            f"proyectada de {proy['A_mantener']['tardanza_total_min']:.0f} a "
            f"{proy[mejor_k]['tardanza_total_min']:.0f} min y los pedidos tarde de "
            f"{proy['A_mantener']['n_tarde']} a {proy[mejor_k]['n_tarde']}, con "
            f"{mejor_cambios} cambio(s) de secuencia. El beneficio ({beneficio:.0f} min) "
            f"supera el costo de inestabilidad ({costo_cambio:.0f} min).")
    else:
        recomendacion = "Mantener ruta actual"
        explicacion = (
            f"Se recomienda mantener la ruta actual: la mejora proyectada "
            f"({max(beneficio, 0):.0f} min) no justifica el costo de cambiar "
            f"{mejor_cambios} parada(s) ({costo_cambio:.0f} min). Estabilidad operativa.")

    return {
        "accion": "replanificar" if aceptar else "mantener",
        "recomendacion": recomendacion,
        "explicacion": explicacion,
        "secuencia_actual": seq_A,
        "secuencia_propuesta": secuencias[mejor_k] if aceptar else seq_A,
        "alternativa_elegida": mejor_k,
        "cambios_secuencia": mejor_cambios,
        "comparacion": {
            "actual": {"tardanza_total_min": proy["A_mantener"]["tardanza_total_min"],
                       "n_tarde": proy["A_mantener"]["n_tarde"],
                       "t_fin_min": proy["A_mantener"]["t_fin_min"]},
            "propuesta": {"tardanza_total_min": proy[mejor_k]["tardanza_total_min"],
                          "n_tarde": proy[mejor_k]["n_tarde"],
                          "t_fin_min": proy[mejor_k]["t_fin_min"]},
        },
        "proyecciones": proy,
    }
