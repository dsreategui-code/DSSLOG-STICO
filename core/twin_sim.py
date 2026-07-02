"""Simulacion estocastica de la jornada para el Gemelo Digital Operativo.

Inyecta incidencias ALEATORIAS y configurables sobre un escenario base (trafico, acceso,
ausencia del cliente) y propaga su efecto sobre las ETAs de las paradas siguientes de cada
vehiculo. Es una operacion SIMULADA y reproducible (semilla), no tiempo real: sirve para que
el gemelo muestre como se degrada la operacion y para alimentar los dashboards de resultados.
"""
from __future__ import annotations

import copy
import random
from typing import List, Tuple

import pandas as pd

from core.risk_engine import UMBRAL_RIESGO, clasificar_iri


def simular_incidencias(escenario: dict, *, tasa: float = 0.12, factor: float = 1.6,
                        seed: int = 7) -> Tuple[dict, List[dict]]:
    """Devuelve (escenario_con_incidencias, lista_incidencias).

    Para cada parada, con probabilidad ``tasa`` ocurre una incidencia que agrega un retraso;
    ese retraso se PROPAGA a las paradas posteriores del mismo vehiculo (efecto cascada). Con
    la misma ``seed`` la jornada es identica (reproducible).
    """
    rng = random.Random(int(seed))
    esc = copy.deepcopy(escenario)
    incidencias: List[dict] = []
    for veh, paradas in esc["rutas"].items():
        shift = 0.0
        for p in paradas:
            base_eta = float(p["eta_min"]) + shift
            p["eta_min"] = round(base_eta, 1)
            if rng.random() < float(tasa):
                serv = float(p.get("servicio_min", 8.0))
                extra = round(serv * (float(factor) - 1.0) + rng.uniform(4.0, 18.0), 1)
                p["incidencia"] = True
                p["incidencia_min"] = extra
                p["t_incidencia"] = round(base_eta, 1)
                incidencias.append({"pedido_id": p["pedido_id"], "vehiculo_id": veh,
                                    "hora": _hhmm(base_eta), "t_min": round(base_eta, 1),
                                    "retraso_min": extra, "distrito": p.get("distrito", "-")})
                shift += extra
            else:
                p["incidencia"] = False
                p["incidencia_min"] = 0.0
                p["t_incidencia"] = None
            p["tardanza_min"] = round(max(0.0, p["eta_min"] - float(p["ventana_fin_min"])), 1)
    return esc, incidencias


def tabla_operacion(escenario: dict) -> pd.DataFrame:
    """Una fila por pedido con su resultado simulado (ETA, tardanza, IRI, incidencia)."""
    filas = []
    for veh, paradas in escenario["rutas"].items():
        for p in paradas:
            iri = float(p.get("iri", 0.0))
            tard = float(p.get("tardanza_min", 0.0))
            filas.append({"pedido_id": p["pedido_id"], "vehiculo_id": veh,
                          "eta_min": float(p["eta_min"]), "hora": int(p["eta_min"] // 60),
                          "ventana_fin_min": float(p.get("ventana_fin_min", 0.0)),
                          "tardanza_min": tard, "a_tiempo": tard <= 0.0,
                          "iri": iri, "clasificacion": clasificar_iri(iri),
                          "incidencia": bool(p.get("incidencia", False)),
                          "distrito": p.get("distrito", "-")})
    return pd.DataFrame(filas)


def resumen_operacion(escenario: dict, incidencias: List[dict] | None = None) -> dict:
    """KPIs agregados de la jornada simulada (para la fila de KPIs del gemelo)."""
    df = tabla_operacion(escenario)
    n = len(df)
    a_tiempo = int(df["a_tiempo"].sum()) if n else 0
    tardias = df[~df["a_tiempo"]] if n else df
    n_inc = len(incidencias) if incidencias is not None else (int(df["incidencia"].sum()) if n else 0)
    return {"pedidos": n, "a_tiempo": a_tiempo,
            "otd": (a_tiempo / n) if n else 0.0,
            "tardanza_prom_min": float(tardias["tardanza_min"].mean()) if len(tardias) else 0.0,
            "tardanza_max_min": float(df["tardanza_min"].max()) if n else 0.0,
            "en_riesgo": int((df["iri"] >= UMBRAL_RIESGO).sum()) if n else 0,
            "incidencias": n_inc}


def _hhmm(minutos: float) -> str:
    m = int(round(minutos))
    return f"{m // 60:02d}:{m % 60:02d}"
