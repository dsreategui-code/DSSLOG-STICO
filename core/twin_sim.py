"""Simulacion estocastica de la jornada para el Gemelo Digital Operativo.

Inyecta incidencias ALEATORIAS y configurables sobre un escenario base y propaga su efecto
sobre las ETAs de las paradas siguientes de cada vehiculo. Cada incidencia tiene una CAUSA
tipificada (congestion, accidente, bloqueo, estacionamiento, ausencia del cliente) tomada de
un catalogo del dominio, con severidad y descripcion. Marca ALERTAS dinamicas y permite
proponer un RE-RUTEO (que decide el usuario).

Metricas (formulas explicitas, sobre los datos de la jornada simulada):
  - OTD  = |{entregas con eta <= ventana_fin}| / N            (a tiempo)
  - OTIF = |{a tiempo Y primer intento exitoso}| / N          (a tiempo y completo)
  - tardanza_min(p) = max(0, eta(p) - ventana_fin(p))
  - variabilidad de operacion = desv. estandar del OTD entre N corridas con incidencias
Es una operacion SIMULADA y reproducible (semilla), no tiempo real.
"""
from __future__ import annotations

import copy
import random
from typing import List, Optional, Tuple

import pandas as pd

from config.cortex_settings import FACTOR_CIRCUITO
from core.risk_engine import UMBRAL_RIESGO, clasificar_iri

MARGEN_ALERTA_MIN = 20.0   # antelacion con que salta una alerta sin incidencia previa
MARGEN_RIESGO_MIN = 25.0   # una parada a <25 min de su ventana ya se considera EN RIESGO

# Catalogo de tipos de incidencia (categorias reales del dominio de ultima milla en Lima).
# 'afecta_otif': la entrega falla en primer intento (ausencia) -> cuenta contra OTIF, no OTD.
# Los retrasos (dmin..dmax) son SIMULADOS; los tipos y pesos reflejan el contexto urbano.
CATALOGO_INCIDENCIAS = [
    {"tipo": "congestion_trafico", "desc": "Congestion de transito",
     "sev": "media", "dmin": 8.0, "dmax": 22.0, "afecta_otif": False, "peso": 0.34},
    {"tipo": "estacionamiento", "desc": "Dificultad de estacionamiento/acceso",
     "sev": "baja", "dmin": 5.0, "dmax": 14.0, "afecta_otif": False, "peso": 0.24},
    {"tipo": "ausencia_cliente", "desc": "Cliente ausente (primer intento fallido)",
     "sev": "media", "dmin": 6.0, "dmax": 15.0, "afecta_otif": True, "peso": 0.18},
    {"tipo": "accidente_via", "desc": "Accidente en via",
     "sev": "alta", "dmin": 20.0, "dmax": 45.0, "afecta_otif": False, "peso": 0.14},
    {"tipo": "bloqueo_manifestacion", "desc": "Bloqueo por manifestacion",
     "sev": "alta", "dmin": 25.0, "dmax": 60.0, "afecta_otif": False, "peso": 0.10},
]
SEV_ORDEN = {"baja": 0, "media": 1, "alta": 2}


def simular_incidencias(escenario: dict, *, tasa: float = 0.12, seed: int = 7,
                        mult_retraso: float = 1.0,
                        catalogo: Optional[list] = None) -> Tuple[dict, List[dict]]:
    """Devuelve (escenario_con_incidencias, lista_incidencias).

    Para cada parada, con probabilidad ``tasa`` ocurre una incidencia de un ``tipo`` sorteado
    del catalogo (por peso); agrega un retraso (escalado por ``mult_retraso``, p. ej. un dia
    critico) que se PROPAGA a las paradas posteriores del mismo vehiculo (cascada). Si el tipo
    es ausencia, la entrega falla en primer intento (afecta OTIF). Reproducible con ``seed``.
    """
    cat = catalogo or CATALOGO_INCIDENCIAS
    tipos = [c["tipo"] for c in cat]
    pesos = [c["peso"] for c in cat]
    por_tipo = {c["tipo"]: c for c in cat}
    rng = random.Random(int(seed))
    esc = copy.deepcopy(escenario)
    incidencias: List[dict] = []
    for veh, paradas in esc["rutas"].items():
        shift = 0.0
        for p in paradas:
            base_eta = float(p["eta_min"]) + shift
            p["eta_min"] = round(base_eta, 1)
            if rng.random() < float(tasa):
                c = por_tipo[rng.choices(tipos, weights=pesos, k=1)[0]]
                extra = round(rng.uniform(c["dmin"], c["dmax"]) * float(mult_retraso), 1)
                p["incidencia"] = True
                p["incidencia_min"] = extra
                p["incidencia_tipo"] = c["tipo"]
                p["incidencia_desc"] = c["desc"]
                p["incidencia_sev"] = c["sev"]
                p["t_incidencia"] = round(base_eta, 1)
                p["primer_intento_ok"] = not c["afecta_otif"]
                incidencias.append({
                    "pedido_id": p["pedido_id"], "vehiculo_id": veh,
                    "hora": _hhmm(base_eta), "t_min": round(base_eta, 1),
                    "tipo": c["tipo"], "descripcion": c["desc"], "severidad": c["sev"],
                    "franja": _franja(base_eta), "retraso_min": extra,
                    "distrito": p.get("distrito", "-"), "afecta_otif": c["afecta_otif"]})
                shift += extra
            else:
                p["incidencia"] = False
                p["incidencia_min"] = 0.0
                p["incidencia_tipo"] = None
                p["incidencia_desc"] = None
                p["incidencia_sev"] = None
                p["t_incidencia"] = None
                p["primer_intento_ok"] = True
            p["tardanza_min"] = round(max(0.0, p["eta_min"] - float(p["ventana_fin_min"])), 1)
    _marcar_alertas(esc)
    return esc, incidencias


def proponer_reruteo(escenario: dict) -> List[dict]:
    """Propuestas de re-secuenciacion (sin aplicar) para cada vehiculo con incidencia: compara
    la ruta actual de sus pendientes contra el orden por ventana mas proxima (EDD) y, SOLO si
    mejora incumplimientos/tardanza, devuelve la propuesta con su sustento y la causa."""
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

        # Dos candidatos: EDD (ventana mas proxima) y Moore-Hodgson (minimiza nº de tardias
        # difiriendo la parada mas costosa). Se elige el mejor y se propone solo si mejora.
        opciones = []
        for orden in (sorted(copy.deepcopy(pend), key=lambda x: float(x["ventana_fin_min"])),
                      _moore_orden(copy.deepcopy(pend), t0, pos0)):
            _recomputar(orden, t0, pos0)
            opciones.append(((_n_tarde(orden), _tardanza_total(orden)), orden))
        k_cand, cand = min(opciones, key=lambda o: o[0])

        if k_cand >= k_base:          # solo se propone si reduce nº de tardias / tardanza
            continue
        inc = paradas[idx]
        propuestas.append({
            "vehiculo_id": veh,
            "incidencia_hora": _hhmm(inc.get("t_incidencia") or inc["eta_min"]),
            "incidencia_distrito": inc.get("distrito", "-"),
            "incidencia_min": float(inc.get("incidencia_min", 0.0)),
            "incidencia_tipo": inc.get("incidencia_tipo"),
            "incidencia_desc": inc.get("incidencia_desc") or "Incidencia",
            "incidencia_sev": inc.get("incidencia_sev") or "media",
            "incidencia_franja": _franja(inc.get("t_incidencia") or inc["eta_min"]),
            "pedido_incidencia": inc.get("pedido_id"),
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
    """Aplica SOLO las propuestas cuyo vehiculo esta en ``aprobadas``. Reordena los pendientes,
    recalcula ETAs, marca alertas y reproyecta geometrias. Conserva todos los pedidos."""
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
    """Atajo programatico: propone y aplica TODAS las mejoras (pruebas y modo batch)."""
    propuestas = proponer_reruteo(escenario)
    esc = aplicar_propuestas(escenario, propuestas, [p["vehiculo_id"] for p in propuestas])
    acciones = [{"vehiculo_id": p["vehiculo_id"], "recuperadas": p["recuperadas"],
                 "tard_antes_min": p["tard_actual_min"],
                 "tard_despues_min": p["tard_propuesto_min"]} for p in propuestas]
    return esc, acciones


# ------------------------------------------------------------------- tablas / metricas
def tabla_operacion(escenario: dict) -> pd.DataFrame:
    """Una fila por pedido con su resultado simulado. OTD/OTIF a nivel pedido:
       a_tiempo = (tardanza<=0);  otif = a_tiempo Y primer intento exitoso."""
    filas = []
    for veh, paradas in escenario["rutas"].items():
        for p in paradas:
            tard = float(p.get("tardanza_min", 0.0))
            a_tiempo = tard <= 0.0
            primer_ok = bool(p.get("primer_intento_ok", True))
            filas.append({"pedido_id": p["pedido_id"], "vehiculo_id": veh,
                          "eta_min": float(p["eta_min"]), "hora": int(p["eta_min"] // 60),
                          "ventana_fin_min": float(p.get("ventana_fin_min", 0.0)),
                          "tardanza_min": tard, "a_tiempo": a_tiempo,
                          "primer_intento_ok": primer_ok,
                          "otif": bool(a_tiempo and primer_ok),
                          "iri": float(p.get("iri", 0.0)),
                          "clasificacion": clasificar_iri(float(p.get("iri", 0.0))),
                          "alerta": bool(p.get("alerta", False)),
                          "incidencia": bool(p.get("incidencia", False)),
                          "incidencia_tipo": p.get("incidencia_tipo"),
                          "distrito": p.get("distrito", "-")})
    return pd.DataFrame(filas)


def resumen_operacion(escenario: dict, incidencias: List[dict] | None = None) -> dict:
    """KPIs agregados de la jornada simulada. OTD, OTIF, tardanza, alertas, incidencias."""
    df = tabla_operacion(escenario)
    n = len(df)
    if not n:
        return {"pedidos": 0, "a_tiempo": 0, "otd": 0.0, "otif": 0.0, "fuera_ventana": 0,
                "fallidas_primer_intento": 0, "tardanza_prom_min": 0.0,
                "tardanza_max_min": 0.0, "en_riesgo": 0, "alertas": 0, "incidencias": 0}
    a_tiempo = int(df["a_tiempo"].sum())
    otif = int(df["otif"].sum())
    tardias = df[~df["a_tiempo"]]
    n_inc = len(incidencias) if incidencias is not None else int(df["incidencia"].sum())
    return {
        "pedidos": n, "a_tiempo": a_tiempo,
        "otd": round(a_tiempo / n, 4),
        "otif": round(otif / n, 4),
        "fuera_ventana": int(n - a_tiempo),
        "fallidas_primer_intento": int((~df["primer_intento_ok"]).sum()),
        "tardanza_prom_min": round(float(tardias["tardanza_min"].mean()), 1) if len(tardias) else 0.0,
        "tardanza_max_min": round(float(df["tardanza_min"].max()), 1),
        "en_riesgo": int((df["iri"] >= UMBRAL_RIESGO).sum()),
        "alertas": int(df["alerta"].sum()),
        "incidencias": n_inc,
    }


def tabla_por_camion(escenario: dict) -> pd.DataFrame:
    """Resultados por vehiculo: pedidos, OTD, OTIF, tardanza, distancia, hora de retorno,
    incidencias. Distancia y retorno via haversine a velocidad constante del modelo."""
    from core.demo_scenario import VELOCIDAD_KMH, _haversine_km
    hub = (escenario["hub"]["lat"], escenario["hub"]["lon"])
    filas = []
    for veh, paradas in escenario["rutas"].items():
        n = len(paradas)
        if not n:
            continue
        a_tiempo = sum(1 for p in paradas if float(p.get("tardanza_min", 0.0)) <= 0.0)
        otif = sum(1 for p in paradas if float(p.get("tardanza_min", 0.0)) <= 0.0
                   and bool(p.get("primer_intento_ok", True)))
        tard_total = round(sum(float(p.get("tardanza_min", 0.0)) for p in paradas), 1)
        inc = sum(1 for p in paradas if p.get("incidencia"))
        prev = hub
        dist = 0.0
        for p in paradas:
            dist += _haversine_km(prev, p["coord"])
            prev = p["coord"]
        dist += _haversine_km(prev, hub)                     # regreso al hub
        ult = paradas[-1]
        retorno = (float(ult["eta_min"]) + float(ult.get("servicio_min", 8.0))
                   + float(ult.get("incidencia_min", 0.0))
                   + _haversine_km(ult["coord"], hub) / VELOCIDAD_KMH * 60.0)
        filas.append({
            "vehiculo_id": veh, "pedidos": n,
            "otd": round(a_tiempo / n, 4), "otif": round(otif / n, 4),
            "a_tiempo": a_tiempo, "fuera_ventana": int(n - a_tiempo),
            "tardanza_total_min": tard_total,
            "distancia_km": round(dist, 2),
            "hora_retorno": _hhmm(retorno), "incidencias": inc,
        })
    return pd.DataFrame(filas).sort_values("vehiculo_id").reset_index(drop=True)


def tabla_alertas(escenario: dict) -> pd.DataFrame:
    """Paradas que dispararon alerta (incumpliran ventana), con la causa de la incidencia del
    vehiculo que las origina."""
    filas = []
    for veh, paradas in escenario["rutas"].items():
        inc = next((p for p in paradas if p.get("incidencia")), None)
        causa = (inc.get("incidencia_desc") if inc else None) or "ventana ajustada"
        sev = (inc.get("incidencia_sev") if inc else None) or "-"
        for p in paradas:
            if not p.get("alerta"):
                continue
            filas.append({"hora_alerta": _hhmm(p.get("t_alerta") or p["eta_min"]),
                          "vehiculo_id": veh, "pedido_id": p["pedido_id"],
                          "distrito": p.get("distrito", "-"),
                          "tardanza_min": float(p.get("tardanza_min", 0.0)),
                          "causa": causa, "severidad": sev})
    df = pd.DataFrame(filas)
    return df.sort_values("hora_alerta").reset_index(drop=True) if not df.empty else df


def tabla_incidencias(incidencias: List[dict]) -> pd.DataFrame:
    """DataFrame de incidencias ocurridas (hora, vehiculo, tipo/causa, severidad, retraso)."""
    if not incidencias:
        return pd.DataFrame(columns=["hora", "vehiculo_id", "pedido_id", "tipo", "descripcion",
                                     "severidad", "franja", "distrito", "retraso_min"])
    df = pd.DataFrame(incidencias)
    return df.sort_values("t_min").reset_index(drop=True)


def agregados_incidencias(incidencias: List[dict]) -> dict:
    """Conteos de incidencias por tipo, por franja y por distrito, e impacto total en minutos."""
    df = tabla_incidencias(incidencias)
    if df.empty:
        return {"por_tipo": pd.DataFrame(), "por_franja": pd.DataFrame(),
                "por_distrito": pd.DataFrame(), "impacto_total_min": 0.0, "n": 0}
    por_tipo = (df.groupby("descripcion")
                .agg(n=("retraso_min", "size"), min_total=("retraso_min", "sum"))
                .reset_index().sort_values("n", ascending=False))
    por_franja = df.groupby("franja").size().reset_index(name="n")
    por_distrito = (df.groupby("distrito").size().reset_index(name="n")
                    .sort_values("n", ascending=False))
    return {"por_tipo": por_tipo, "por_franja": por_franja, "por_distrito": por_distrito,
            "impacto_total_min": round(float(df["retraso_min"].sum()), 1), "n": int(len(df))}


def comparar_rutas(esc_inicial: dict, esc_final: dict) -> pd.DataFrame:
    """Compara, por vehiculo, la secuencia INICIAL vs la FINAL (re-planificada) y su efecto.
    'cambiada' = el orden de paradas difiere."""
    filas = []
    for veh in esc_inicial["rutas"]:
        ini = esc_inicial["rutas"][veh]
        fin = esc_final["rutas"].get(veh, ini)
        seq_ini = [p["pedido_id"] for p in ini]
        seq_fin = [p["pedido_id"] for p in fin]
        tard_ini = round(sum(float(p.get("tardanza_min", 0.0)) for p in ini), 1)
        tard_fin = round(sum(float(p.get("tardanza_min", 0.0)) for p in fin), 1)
        at_ini = sum(1 for p in ini if float(p.get("tardanza_min", 0.0)) <= 0.0)
        at_fin = sum(1 for p in fin if float(p.get("tardanza_min", 0.0)) <= 0.0)
        filas.append({
            "vehiculo_id": veh, "cambiada": seq_ini != seq_fin,
            "orden_inicial": " → ".join(seq_ini),
            "orden_final": " → ".join(seq_fin),
            "a_tiempo_inicial": at_ini, "a_tiempo_final": at_fin,
            "delta_a_tiempo": at_fin - at_ini,
            "tardanza_inicial_min": tard_ini, "tardanza_final_min": tard_fin,
            "delta_tardanza_min": round(tard_fin - tard_ini, 1)})
    return pd.DataFrame(filas).sort_values(["cambiada", "vehiculo_id"],
                                           ascending=[False, True]).reset_index(drop=True)


def variabilidad_operacion(escenario_base: dict, *, tasa: float = 0.12,
                           mult_retraso: float = 1.0, n_corridas: int = 25,
                           seed: int = 0) -> dict:
    """Variabilidad de la operacion: corre la jornada con incidencias sobre N semillas y mide
    la DISPERSION del OTD (objetivo del DSS: menor variabilidad = servicio mas consistente).

    Devuelve media, desviacion estandar y CV del OTD sobre las N corridas.
    """
    otds = []
    for s in range(int(n_corridas)):
        esc_s, _ = simular_incidencias(escenario_base, tasa=tasa, seed=seed + s,
                                       mult_retraso=mult_retraso)
        otds.append(resumen_operacion(esc_s)["otd"])
    if not otds:
        return {"otd_medio": 0.0, "otd_std": 0.0, "cv": 0.0, "n": 0, "muestras": []}
    media = sum(otds) / len(otds)
    var = sum((x - media) ** 2 for x in otds) / len(otds)
    std = var ** 0.5
    return {"otd_medio": round(media, 4), "otd_std": round(std, 4),
            "cv": round(std / media, 4) if media > 0 else 0.0,
            "n": len(otds), "muestras": otds}


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
        t += _haversine_km(prev, p["coord"]) * FACTOR_CIRCUITO / VELOCIDAD_KMH * 60.0
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


def _en_riesgo_ct(paradas: list) -> int:
    """Nº de paradas a <MARGEN_RIESGO_MIN de su ventana (o ya vencidas)."""
    return sum(1 for p in paradas
               if float(p["eta_min"]) > float(p.get("ventana_fin_min", 1e9)) - MARGEN_RIESGO_MIN)


def _moore_orden(pend: list, t0: float, pos0) -> list:
    """Moore-Hodgson (aproximado): minimiza el Nº de entregas tardias difiriendo al final la
    parada mas costosa cuando una llegaria tarde. Tiempos de proceso = viaje (en orden EDD) +
    servicio + incidencia. El orden resultante se recalcula luego con el viaje real."""
    from core.demo_scenario import VELOCIDAD_KMH, _haversine_km
    edd = sorted(pend, key=lambda x: float(x["ventana_fin_min"]))
    proc, prev = {}, pos0
    for p in edd:
        proc[id(p)] = (_haversine_km(prev, p["coord"]) * FACTOR_CIRCUITO / VELOCIDAD_KMH * 60.0
                       + float(p.get("servicio_min", 8.0)) + float(p.get("incidencia_min", 0.0)))
        prev = p["coord"]
    sched, deferred, t = [], [], float(t0)
    for p in edd:
        sched.append(p)
        t += proc[id(p)]
        arr = t - float(p.get("servicio_min", 8.0)) - float(p.get("incidencia_min", 0.0))
        if arr > float(p["ventana_fin_min"]):        # llegaria tarde -> difiere la mas costosa
            worst = max(sched, key=lambda q: proc[id(q)])
            sched.remove(worst)
            deferred.append(worst)
            t -= proc[id(worst)]
    return sched + deferred


def _tardanza_total(paradas: list) -> float:
    return sum(float(p.get("tardanza_min", 0.0)) for p in paradas)


def _franja(minutos: float) -> str:
    m = float(minutos)
    if m < 12 * 60:
        return "mañana"
    if m < 15 * 60:
        return "mediodia"
    return "tarde"


def _hhmm(minutos: float) -> str:
    m = int(round(minutos))
    return f"{m // 60:02d}:{m % 60:02d}"
