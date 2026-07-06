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
