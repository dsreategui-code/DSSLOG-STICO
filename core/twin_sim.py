"""Simulacion estocastica de la jornada para el Gemelo Digital Operativo.

Inyecta incidencias ALEATORIAS y configurables sobre un escenario base (trafico, acceso,
ausencia del cliente) y propaga su efecto sobre las ETAs de las paradas siguientes de cada
vehiculo. Marca ALERTAS dinamicas (una parada salta en riesgo en cuanto la cascada la condena
a incumplir su ventana, no por el IRI estatico del plan) y permite un RE-RUTEO automatico del
cerebro que re-secuencia los pendientes de los vehiculos alertados para recuperar OTD.
Es una operacion SIMULADA y reproducible (semilla), no tiempo real.
"""
from __future__ import annotations

import copy
import random
from typing import List, Tuple

import pandas as pd

from core.risk_engine import UMBRAL_RIESGO, clasificar_iri

MARGEN_ALERTA_MIN = 20.0   # antelacion con que salta una alerta sin incidencia previa


def simular_incidencias(escenario: dict, *, tasa: float = 0.12, factor: float = 1.6,
                        seed: int = 7) -> Tuple[dict, List[dict]]:
    """Devuelve (escenario_con_incidencias, lista_incidencias).

    Para cada parada, con probabilidad ``tasa`` ocurre una incidencia que agrega un retraso;
    ese retraso se PROPAGA a las paradas posteriores del mismo vehiculo (efecto cascada). Con
    la misma ``seed`` la jornada es identica (reproducible). Marca alertas dinamicas.
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
    _marcar_alertas(esc)
    return esc, incidencias


def proponer_reruteo(escenario: dict) -> List[dict]:
    """Genera PROPUESTAS de re-secuenciacion (sin aplicarlas): para cada vehiculo con una
    incidencia, compara la ruta actual de sus pendientes contra el orden por ventana mas
    proxima (EDD) y, SOLO si mejora los incumplimientos/tardanza, devuelve una propuesta con
    su sustento. La decision (aprobar/mantener) queda en manos del usuario.

    Las paradas hasta la incidencia quedan fijas (ya en curso); se reordenan las siguientes.
    """
    propuestas: List[dict] = []
    for veh, paradas in escenario["rutas"].items():
        idx = next((i for i, p in enumerate(paradas) if p.get("incidencia")), None)
        if idx is None:
            continue
        fijas, pend = paradas[:idx + 1], paradas[idx + 1:]
        if len(pend) < 2:
            continue
        ancla = fijas[-1]
        t0 = float(ancla["eta_min"]) + float(ancla.get("servicio_min", 8.0)) \
            + float(ancla.get("incidencia_min", 0.0))
        pos0 = ancla["coord"]

        base = copy.deepcopy(pend)
        _recomputar(base, t0, pos0)
        k_base = (_n_tarde(base), _tardanza_total(base))

        cand = sorted(copy.deepcopy(pend), key=lambda x: float(x["ventana_fin_min"]))
        _recomputar(cand, t0, pos0)
        k_cand = (_n_tarde(cand), _tardanza_total(cand))

        if k_cand >= k_base:          # solo se propone si mejora
            continue
        inc = paradas[idx]
        propuestas.append({
            "vehiculo_id": veh,
            "incidencia_hora": _hhmm(inc.get("t_incidencia") or inc["eta_min"]),
            "incidencia_distrito": inc.get("distrito", "-"),
            "incidencia_min": float(inc.get("incidencia_min", 0.0)),
            "n_pendientes": len(pend),
            "orden_actual": [p["pedido_id"] for p in base],
            "orden_propuesto": [p["pedido_id"] for p in cand],
            "tarde_actual": int(k_base[0]), "tarde_propuesto": int(k_cand[0]),
            "tard_actual_min": round(k_base[1], 1),
            "tard_propuesto_min": round(k_cand[1], 1),
            "recuperadas": int(k_base[0] - k_cand[0]),
            "reduccion_min": round(k_base[1] - k_cand[1], 1),
        })
    return propuestas


def aplicar_propuestas(escenario: dict, propuestas: List[dict], aprobadas) -> dict:
    """Aplica al escenario SOLO las propuestas cuyo vehiculo esta en ``aprobadas`` (iterable
    de vehiculo_id). Reordena los pendientes segun el orden propuesto, recalcula ETAs, marca
    alertas y reproyecta geometrias. Conserva todos los pedidos (custodia, sin transferencias).
    """
    aprobadas = set(aprobadas)
    por_veh = {p["vehiculo_id"]: p for p in propuestas}
    esc = copy.deepcopy(escenario)
    for veh in aprobadas:
        prop = por_veh.get(veh)
        if prop is None or veh not in esc["rutas"]:
            continue
        paradas = esc["rutas"][veh]
        idx = next((i for i, p in enumerate(paradas) if p.get("incidencia")), None)
        if idx is None:
            continue
        fijas, pend = paradas[:idx + 1], paradas[idx + 1:]
        pid_a_parada = {p["pedido_id"]: p for p in pend}
        nuevo = [pid_a_parada[pid] for pid in prop["orden_propuesto"] if pid in pid_a_parada]
        nuevo += [p for p in pend if p not in nuevo]      # salvaguarda: no perder paradas
        ancla = fijas[-1]
        t0 = float(ancla["eta_min"]) + float(ancla.get("servicio_min", 8.0)) \
            + float(ancla.get("incidencia_min", 0.0))
        _recomputar(nuevo, t0, ancla["coord"])
        paradas[:] = fijas + nuevo
    _reproyectar_geometrias(esc)
    _marcar_alertas(esc)
    return esc


def mitigar_con_reruteo(escenario: dict) -> Tuple[dict, List[dict]]:
    """Atajo programatico: propone y aplica TODAS las mejoras (usado en pruebas y modo batch).
    En la UI la decision es del usuario (proponer_reruteo + aplicar_propuestas)."""
    propuestas = proponer_reruteo(escenario)
    esc = aplicar_propuestas(escenario, propuestas, [p["vehiculo_id"] for p in propuestas])
    acciones = [{"vehiculo_id": p["vehiculo_id"], "recuperadas": p["recuperadas"],
                 "tard_antes_min": p["tard_actual_min"],
                 "tard_despues_min": p["tard_propuesto_min"]} for p in propuestas]
    return esc, acciones


def tabla_operacion(escenario: dict) -> pd.DataFrame:
    """Una fila por pedido con su resultado simulado (ETA, tardanza, IRI, alerta, incidencia)."""
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
                          "alerta": bool(p.get("alerta", False)),
                          "incidencia": bool(p.get("incidencia", False)),
                          "distrito": p.get("distrito", "-")})
    return pd.DataFrame(filas)


def tabla_alertas(escenario: dict) -> pd.DataFrame:
    """Paradas que dispararon alerta (incumpliran ventana), con su motivo."""
    filas = []
    for veh, paradas in escenario["rutas"].items():
        for p in paradas:
            if not p.get("alerta"):
                continue
            motivo = "incidencia en cascada" if p.get("t_incidencia") is not None \
                or any(q.get("incidencia") for q in paradas) else "ventana ajustada"
            filas.append({"hora_alerta": _hhmm(p.get("t_alerta") or p["eta_min"]),
                          "vehiculo_id": veh, "pedido_id": p["pedido_id"],
                          "distrito": p.get("distrito", "-"),
                          "tardanza_min": float(p.get("tardanza_min", 0.0)),
                          "motivo": motivo})
    df = pd.DataFrame(filas)
    return df.sort_values("hora_alerta").reset_index(drop=True) if not df.empty else df


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
            "alertas": int(df["alerta"].sum()) if n else 0,
            "incidencias": n_inc}


# --------------------------------------------------------------------------- helpers
def _marcar_alertas(escenario: dict) -> None:
    """Marca alerta=True en las paradas que incumpliran ventana y fija t_alerta (cuando se
    hace evidente el riesgo): al momento de la incidencia que la causa, o con antelacion."""
    t_ini = float(escenario.get("t_inicio_min", 540))
    for paradas in escenario["rutas"].values():
        inc_ts = [float(p["t_incidencia"]) for p in paradas
                  if p.get("incidencia") and p.get("t_incidencia") is not None]
        primera = min(inc_ts) if inc_ts else None
        for p in paradas:
            late = float(p.get("tardanza_min", 0.0)) > 0.0
            p["alerta"] = bool(late)
            if not late:
                p["t_alerta"] = None
            elif primera is not None and primera <= float(p["eta_min"]):
                p["t_alerta"] = round(primera, 1)
            else:
                p["t_alerta"] = round(max(t_ini, float(p["eta_min"]) - MARGEN_ALERTA_MIN), 1)


def _recomputar(paradas: list, t_start: float, pos_start) -> None:
    """Recalcula eta_min/tardanza_min de una secuencia desde (t_start, pos_start) con
    velocidad constante (haversine) + servicio + retraso de incidencia por parada."""
    from core.demo_scenario import VELOCIDAD_KMH, _haversine_km
    t, prev = float(t_start), pos_start
    for p in paradas:
        t += _haversine_km(prev, p["coord"]) / VELOCIDAD_KMH * 60.0
        p["eta_min"] = round(t, 1)
        p["tardanza_min"] = round(max(0.0, t - float(p["ventana_fin_min"])), 1)
        t += float(p.get("servicio_min", 8.0)) + float(p.get("incidencia_min", 0.0))
        prev = p["coord"]


def _reproyectar_geometrias(escenario: dict) -> None:
    hub = escenario["hub"]
    for veh, paradas in escenario["rutas"].items():
        escenario["geometrias"][veh] = ([[hub["lon"], hub["lat"]]]
                                        + [[p["coord"][1], p["coord"][0]] for p in paradas])


def _n_tarde(paradas: list) -> int:
    return sum(1 for p in paradas if float(p.get("tardanza_min", 0.0)) > 0.0)


def _tardanza_total(paradas: list) -> float:
    return sum(float(p.get("tardanza_min", 0.0)) for p in paradas)


def _hhmm(minutos: float) -> str:
    m = int(round(minutos))
    return f"{m // 60:02d}:{m % 60:02d}"
