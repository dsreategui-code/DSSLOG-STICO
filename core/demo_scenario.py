"""Escenario demo autocontenido para el gemelo digital operativo.

Construye un escenario (HUB, pedidos, vehiculos, rutas con ETA, geometrias) a partir del
dataset demo existente, con una asignacion simple por vecino mas cercano y proyeccion de
ETAs (distancia haversine / velocidad). Sirve para DEMOSTRAR la vista PyDeck mientras el
pipeline completo de planificacion (Fase 8) se cablea. No reemplaza al motor CORTEX-LM:
cuando el pipeline produzca un escenario real, la vista lo usara en su lugar.
"""
from __future__ import annotations

import math
from typing import List

from services.data_loader import load_dataset
from utils.formatters import hhmm_to_minutes

VELOCIDAD_KMH = 18.0
T_INICIO_MIN = 9 * 60      # 09:00
SERVICIO_DEFECTO_MIN = 8.0


def _haversine_km(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    R = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _tour_vecino_mas_cercano(hub, puntos: List[dict]) -> List[dict]:
    restantes = list(puntos)
    tour = []
    actual = hub
    while restantes:
        restantes.sort(key=lambda p: _haversine_km(actual, p["coord"]))
        sig = restantes.pop(0)
        tour.append(sig)
        actual = sig["coord"]
    return tour


def construir_escenario_demo(num_vehiculos: int = 6) -> dict:
    ds = load_dataset()
    alm = ds["almacen"].iloc[0]
    hub = {"nombre": str(alm.get("nombre", "HUB")), "lat": float(alm["latitud"]),
           "lon": float(alm["longitud"])}
    hub_coord = (hub["lat"], hub["lon"])

    pedidos_df = ds["pedidos"]
    puntos = []
    for _, r in pedidos_df.iterrows():
        puntos.append({
            "pedido_id": str(r["pedido_id"]),
            "coord": (float(r["latitud"]), float(r["longitud"])),
            "distrito": str(r.get("distrito", "")),
            "detalle_cliente": str(r.get("detalle_cliente", "")),
            "ventana_fin_min": hhmm_to_minutes(str(r.get("ventana_fin", "19:00"))),
            "servicio_min": float(r.get("tiempo_servicio_min", SERVICIO_DEFECTO_MIN) or SERVICIO_DEFECTO_MIN),
        })

    tour = _tour_vecino_mas_cercano(hub_coord, puntos)
    nv = max(1, int(num_vehiculos))
    cs = math.ceil(len(tour) / nv)
    veh_ids = [v for v in ds["vehiculos"]["vehiculo_id"].astype(str).tolist()][:nv] or \
              [f"V{i+1:02d}" for i in range(nv)]

    rutas = {}
    geometrias = {}
    for vi in range(nv):
        chunk = tour[vi * cs:(vi + 1) * cs]
        if not chunk:
            continue
        veh = veh_ids[vi] if vi < len(veh_ids) else f"V{vi+1:02d}"
        paradas = []
        t = float(T_INICIO_MIN)
        prev = hub_coord
        for p in chunk:
            viaje = _haversine_km(prev, p["coord"]) / VELOCIDAD_KMH * 60.0
            t += viaje
            eta = t
            tardanza = max(0.0, eta - p["ventana_fin_min"])
            # IRI proxy para la demo: crece al acercarse/exceder el cierre de ventana.
            margen = p["ventana_fin_min"] - eta
            iri = 0.0 if margen > 45 else (1.0 if margen < 0 else round(1 - margen / 45.0, 3))
            paradas.append({
                "pedido_id": p["pedido_id"], "coord": p["coord"], "eta_min": round(eta, 1),
                "servicio_min": p["servicio_min"], "tardanza_min": round(tardanza, 1),
                "iri": iri, "ventana_fin_min": p["ventana_fin_min"],
                "distrito": p["distrito"], "detalle_cliente": p.get("detalle_cliente", "")})
            t += p["servicio_min"]
            prev = p["coord"]
        rutas[veh] = paradas
        geometrias[veh] = [[hub["lon"], hub["lat"]]] + [[pp["coord"][1], pp["coord"][0]]
                                                        for pp in paradas]

    return {"hub": hub, "rutas": rutas, "geometrias": geometrias,
            "t_inicio_min": float(T_INICIO_MIN), "jornada_fin_min": 19 * 60,
            "vehiculos": list(rutas.keys()),
            "n_pedidos": sum(len(v) for v in rutas.values())}


# --------------------------------------------------------------------------- #
# Puente al replanificador CORTEX (usa el motor real sobre el escenario demo)
# --------------------------------------------------------------------------- #
def _modelo_vehiculo(escenario: dict, veh: str):
    """Construye un ModeloNumerico de 1 vehiculo (HUB + sus paradas) por haversine."""
    import numpy as np
    from core.optimizer_ortools import ModeloNumerico
    hub = (escenario["hub"]["lat"], escenario["hub"]["lon"])
    paradas = escenario["rutas"][veh]
    coords = [hub] + [p["coord"] for p in paradas]
    n = len(coords)
    H = int(escenario["jornada_fin_min"] - escenario["t_inicio_min"])
    tm = np.zeros((n, n)); dm = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                km = _haversine_km(coords[i], coords[j])
                dm[i][j] = km
                tm[i][j] = km / VELOCIDAD_KMH * 60.0
    ventanas = [(0, H)]
    serv = [0.0]
    pids = ["HUB"]
    for p in paradas:
        fin = int(p["ventana_fin_min"] - escenario["t_inicio_min"])
        ventanas.append((0, max(1, min(H, fin))))
        serv.append(float(p["servicio_min"]))
        pids.append(p["pedido_id"])
    return ModeloNumerico(
        tiempo_min=tm, dist_km=dm, demanda_m3=[0.0] * n, demanda_kg=[0.0] * n,
        ventanas_min=ventanas, servicio_min=serv, pedido_ids=pids, num_vehiculos=1,
        cap_m3=[1e9], cap_kg=[1e9], vehiculo_ids=[veh], horizonte_min=H)


def replan_vehiculo_demo(escenario: dict, veh: str, params, *,
                         t_actual_rel_min: float = 0.0, completadas_n: int = 0,
                         incidencia_factor: float = 1.4) -> dict:
    """Ejecuta el replanificador CORTEX real sobre un vehiculo del escenario demo, con una
    incidencia que infla el tiempo de los tramos pendientes."""
    from core.replanner import EstadoVehiculo, replanificar_vehiculo
    modelo = _modelo_vehiculo(escenario, veh)
    n = len(modelo.pedido_ids)                       # HUB + paradas
    ruta = list(range(1, n))                          # nodos de las paradas en orden actual
    completadas = ruta[:max(0, int(completadas_n))]
    pos = completadas[-1] if completadas else 0
    factor = {k: incidencia_factor for k in range(1, n)}
    estado = EstadoVehiculo(veh, ruta_planificada=[0] + ruta, completadas=completadas,
                            pos_nodo=pos, t_actual_min=float(t_actual_rel_min),
                            retraso_acumulado_min=0.0)
    res = replanificar_vehiculo(estado, modelo, params, factor_tiempo=factor)
    res["pedido_ids"] = modelo.pedido_ids
    return res
