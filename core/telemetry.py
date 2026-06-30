"""Telemetria SIMULADA del gemelo digital operativo.

Genera la tabla de telemetria (avance de los vehiculos por ticks) a partir de un escenario
planificado/simulado. Alimenta el mapa PyDeck y los controles de la vista. Es una
reconstruccion simulada del avance de la operacion (gemelo digital operativo), NO datos
GPS ni tiempo real fisico.

Columnas: tick, tiempo_simulado, vehiculo_id, lat, lon, estado_vehiculo, pedido_actual,
retraso_acumulado, alerta, ruta_tipo.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from geo.interpolation import construir_trayectoria, posicion_en_tiempo

UMBRAL_ALERTA_RETRASO_MIN = 15.0


def _trayectorias(escenario: dict) -> Dict[str, object]:
    hub = (escenario["hub"]["lat"], escenario["hub"]["lon"])
    t0 = float(escenario.get("t_inicio_min", 540))
    trays = {}
    for veh, paradas in escenario["rutas"].items():
        trays[veh] = construir_trayectoria(veh, hub, paradas, t0)
    return trays


def _retraso_acumulado(paradas: List[dict], t: float) -> float:
    return round(sum(float(p.get("tardanza_min", 0.0)) for p in paradas
                     if float(p["eta_min"]) <= t), 1)


def construir_telemetria(escenario: dict, paso_tick_min: float = 5.0,
                         ruta_tipo_por_veh: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Genera la telemetria por ticks para todos los vehiculos del escenario."""
    trays = _trayectorias(escenario)
    if not trays:
        return pd.DataFrame(columns=["tick", "tiempo_simulado", "vehiculo_id", "lat", "lon",
                                     "estado_vehiculo", "pedido_actual", "retraso_acumulado",
                                     "alerta", "ruta_tipo"])
    t0 = float(escenario.get("t_inicio_min", 540))
    t_fin = max(tr.t_fin for tr in trays.values())
    ruta_tipo_por_veh = ruta_tipo_por_veh or {}

    filas = []
    tick = 0
    t = t0
    while t <= t_fin + 1e-6:
        for veh, tray in trays.items():
            pos = posicion_en_tiempo(tray, t)
            retraso = _retraso_acumulado(escenario["rutas"][veh], t)
            estado = pos["estado"]
            if estado == "en_ruta" and retraso > UMBRAL_ALERTA_RETRASO_MIN:
                estado = "retrasado"
            filas.append({
                "tick": tick, "tiempo_simulado": round(t, 1), "vehiculo_id": veh,
                "lat": round(pos["lat"], 6), "lon": round(pos["lon"], 6),
                "estado_vehiculo": estado, "pedido_actual": pos["pedido_actual"],
                "retraso_acumulado": retraso,
                "alerta": bool(retraso > UMBRAL_ALERTA_RETRASO_MIN),
                "ruta_tipo": ruta_tipo_por_veh.get(veh, "planificada"),
            })
        tick += 1
        t = t0 + tick * paso_tick_min
    return pd.DataFrame(filas)


def estado_pedidos_en_tick(escenario: dict, t: float) -> pd.DataFrame:
    """Estado de cada pedido en el instante `t` para colorear el mapa."""
    filas = []
    for veh, paradas in escenario["rutas"].items():
        for p in paradas:
            eta = float(p["eta_min"])
            serv = float(p.get("servicio_min", 0.0))
            iri = float(p.get("iri", 0.0))
            if t >= eta + serv:
                estado = "entregado"
            elif eta <= t < eta + serv:
                estado = "en_servicio"
            elif iri >= 0.61:
                estado = "en_riesgo"
            else:
                estado = "pendiente"
            filas.append({"pedido_id": p["pedido_id"], "lat": p["coord"][0],
                          "lon": p["coord"][1], "vehiculo_id": veh, "estado": estado,
                          "eta_min": eta, "iri": round(iri, 3),
                          "tardanza_min": float(p.get("tardanza_min", 0.0))})
    return pd.DataFrame(filas)
