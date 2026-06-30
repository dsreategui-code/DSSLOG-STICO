"""Interpolacion de la posicion de un vehiculo a lo largo de su ruta, por tiempo simulado.

Convierte la secuencia de paradas (con ETA y tiempo de servicio) en una TRAYECTORIA por
segmentos (viaje / servicio) y permite consultar la posicion (lat, lon) y el estado del
vehiculo en cualquier instante de la jornada. Alimenta la telemetria del gemelo digital.

Es una reconstruccion simulada del avance, NO posicion GPS real.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Coord = Tuple[float, float]  # (lat, lon)


@dataclass
class Segmento:
    t0: float
    t1: float
    p0: Coord
    p1: Coord
    tipo: str            # 'viaje' | 'servicio' | 'espera'
    pedido_id: str = ""


@dataclass
class Trayectoria:
    vehiculo_id: str
    segmentos: List[Segmento] = field(default_factory=list)
    t_inicio: float = 0.0
    t_fin: float = 0.0


def construir_trayectoria(vehiculo_id: str, hub_latlon: Coord,
                          paradas: List[dict], t_inicio: float) -> Trayectoria:
    """`paradas`: lista ordenada de {coord:(lat,lon), eta_min, servicio_min, pedido_id}.

    Construye segmentos de viaje (de una parada a la siguiente, en [salida_prev, eta]) y de
    servicio (estacionario en la parada, en [eta, eta+servicio]).
    """
    segmentos: List[Segmento] = []
    prev_coord = hub_latlon
    t_salida = float(t_inicio)
    for par in paradas:
        eta = float(par["eta_min"])
        llegada = max(eta, t_salida)            # no viajar "hacia atras" en el tiempo
        segmentos.append(Segmento(t_salida, llegada, prev_coord, par["coord"], "viaje",
                                  par.get("pedido_id", "")))
        serv = float(par.get("servicio_min", 0.0))
        segmentos.append(Segmento(llegada, llegada + serv, par["coord"], par["coord"],
                                  "servicio", par.get("pedido_id", "")))
        prev_coord = par["coord"]
        t_salida = llegada + serv
    return Trayectoria(vehiculo_id, segmentos, float(t_inicio), t_salida)


def posicion_en_tiempo(tray: Trayectoria, t: float) -> dict:
    """Posicion y estado del vehiculo en el instante `t` (min desde inicio de jornada)."""
    if not tray.segmentos or t <= tray.t_inicio:
        c = tray.segmentos[0].p0 if tray.segmentos else (0.0, 0.0)
        return {"lat": c[0], "lon": c[1], "estado": "disponible", "pedido_actual": ""}
    if t >= tray.t_fin:
        c = tray.segmentos[-1].p1
        return {"lat": c[0], "lon": c[1], "estado": "finalizado", "pedido_actual": ""}
    for seg in tray.segmentos:
        if seg.t0 <= t <= seg.t1:
            if seg.tipo == "servicio":
                return {"lat": seg.p0[0], "lon": seg.p0[1], "estado": "en_servicio",
                        "pedido_actual": seg.pedido_id}
            frac = (t - seg.t0) / (seg.t1 - seg.t0) if seg.t1 > seg.t0 else 1.0
            lat = seg.p0[0] + frac * (seg.p1[0] - seg.p0[0])
            lon = seg.p0[1] + frac * (seg.p1[1] - seg.p0[1])
            return {"lat": lat, "lon": lon, "estado": "en_ruta", "pedido_actual": seg.pedido_id}
    c = tray.segmentos[-1].p1
    return {"lat": c[0], "lon": c[1], "estado": "finalizado", "pedido_actual": ""}
