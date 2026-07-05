"""Sample Average Approximation (SAA) para ROBUSTEZ POR DISENO dentro del ALNS.

El ALNS (core.alns) optimizaba un costo DETERMINISTA (viaje + tardanza sobre la matriz
contextual, con un buffer SLA fijo como unico gesto ante la incertidumbre). Este modulo hace
que la robustez se busque DENTRO de la metaheuristica: pre-sortea UNA sola vez, con numeros
aleatorios comunes (CRN), un paquete de S escenarios de incertidumbre y evalua cada solucion
del ALNS sobre TODOS ellos, optimizando

    objetivo = viaje + w_tard * ( E[tardanza] + beta * CVaR_alpha(tardanza) )

(Rockafellar-Uryasev). Al reusar el MISMO paquete de escenarios en toda la busqueda (CRN), la
comparacion entre soluciones es de baja varianza y el ALNS no persigue ruido. Es una
Aproximacion por Promedio de Muestras (SAA) del problema estocastico.

Los escenarios son COHERENTES con el simulador SimPy (core.simulator_simpy) y usan el MISMO
catalogo de incidencias unificado (core.uncertainty.probabilidades_por_nodo): factor sistemico
del dia (correlacionado), ruido idiosincratico de viaje por nodo, incidencias, ausencia del
cliente y servicio triangular. Es simulacion: trabaja con distribuciones, no con datos reales.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from core.risk_engine import cvar as _cvar

PENAL_REINTENTO_MIN = 10.0     # penalizacion de servicio si el cliente esta ausente (reintento)


@dataclass
class EscenariosSAA:
    """Paquete de S escenarios pre-sorteados (CRN) para evaluar soluciones en el ALNS."""
    S: int
    n: int
    factor_dia: np.ndarray          # (S,)   factor sistemico del dia por escenario (E=1)
    mult: np.ndarray                # (S,n)  multiplicador idiosincratico de viaje por nodo (E=1)
    incidente: np.ndarray           # (S,n)  bool: ocurre incidencia al llegar al nodo
    incid_delay: np.ndarray         # (n,)   demora (min) de la incidencia del nodo (x factor_dia)
    serv_eff: np.ndarray            # (S,n)  servicio efectivo (triangular + reintento si ausente)
    ventana_ini: np.ndarray         # (n,)
    ventana_fin: np.ndarray         # (n,)
    franjas_td: List[Tuple[float, float, float]]   # perfil TD (mult por franja, relativo a hora_ref)


def construir_escenarios(modelo, incid_prob: Sequence[float], incid_delay: Sequence[float],
                         ausencia_prob: Sequence[float], *, n_escenarios: int = 20,
                         sigma_viaje: float = 0.25, sigma_sistemico: float = 0.10,
                         franjas_td: Optional[Sequence] = None, seed: int = 42,
                         penal_reintento_min: float = PENAL_REINTENTO_MIN) -> EscenariosSAA:
    """Pre-sortea el paquete de escenarios (CRN, reproducible con `seed`). Nodo 0 = HUB.

    `incid_prob/incid_delay/ausencia_prob` vienen de core.uncertainty.probabilidades_por_nodo
    (mismo catalogo de incidencias que el simulador SimPy y el Gemelo Digital)."""
    S = max(1, int(n_escenarios))
    n = int(modelo.tiempo_min.shape[0])
    rs = np.random.RandomState(int(seed))

    ip = np.zeros(n); ip[:len(incid_prob)] = np.asarray(incid_prob, dtype=float)[:n]
    idl = np.zeros(n); idl[:len(incid_delay)] = np.asarray(incid_delay, dtype=float)[:n]
    au = np.zeros(n); au[:len(ausencia_prob)] = np.asarray(ausencia_prob, dtype=float)[:n]

    # Factor SISTEMICO del dia: uno por escenario, comun a todos los nodos (correlacion). E=1.
    if sigma_sistemico and sigma_sistemico > 0:
        factor_dia = np.exp(rs.normal(-0.5 * sigma_sistemico ** 2, sigma_sistemico, size=S))
    else:
        factor_dia = np.ones(S)

    # Ruido IDIOSINCRATICO de viaje por (escenario, nodo). E[multiplicador] = 1.
    mu = -0.5 * sigma_viaje ** 2
    mult = np.exp(rs.normal(mu, sigma_viaje, size=(S, n)))

    incidente = rs.random_sample((S, n)) < ip[np.newaxis, :]
    ausente = rs.random_sample((S, n)) < au[np.newaxis, :]

    # Servicio triangular por nodo (min/moda/max); nodos sin banda usan la moda (evita left==right).
    serv_min = np.asarray(_lista(modelo, "servicio_min"), dtype=float)
    serv_moda = serv_min.copy()
    smin = np.maximum(0.0, 0.6 * serv_min)
    smax = np.where(serv_min > 0, 1.8 * serv_min, 0.0)
    serv_base = np.empty((S, n))
    for node in range(n):
        if smax[node] > smin[node] and smin[node] <= serv_moda[node] <= smax[node]:
            serv_base[:, node] = rs.triangular(smin[node], serv_moda[node], smax[node], size=S)
        else:
            serv_base[:, node] = serv_moda[node]
    serv_eff = serv_base + ausente * float(penal_reintento_min)

    ven = modelo.ventanas_min
    return EscenariosSAA(
        S=S, n=n, factor_dia=factor_dia, mult=mult, incidente=incidente, incid_delay=idl,
        serv_eff=serv_eff,
        ventana_ini=np.asarray([v[0] for v in ven], dtype=float),
        ventana_fin=np.asarray([v[1] for v in ven], dtype=float),
        franjas_td=list(franjas_td) if franjas_td else [])


def _lista(modelo, attr):
    return list(getattr(modelo, attr))


def _td_mult_vec(franjas: List[Tuple[float, float, float]], t: np.ndarray) -> np.ndarray:
    """Multiplicador de trafico dependiente de la hora, vectorizado (primera franja que aplica,
    como en simulator_simpy._td_mult). 1.0 fuera de toda franja."""
    m = np.ones_like(t)
    if not franjas:
        return m
    puesto = np.zeros_like(t, dtype=bool)
    for ini, fin, mult in franjas:
        cond = (~puesto) & (t >= ini) & (t <= fin)
        if cond.any():
            m = np.where(cond, mult, m)
            puesto |= cond
    return m


def tardanza_por_escenario(routes: List[List[int]], modelo, esc: EscenariosSAA) -> np.ndarray:
    """Tardanza TOTAL (min) de la solucion en cada uno de los S escenarios (vector de largo S).

    Recorre cada ruta acumulando el tiempo de forma vectorizada sobre los escenarios: viaje =
    T_base * factor_dia * mult_td(hora) * ruido_nodo (+ demora de incidencia * factor_dia),
    espera a la apertura de ventana, y suma el exceso sobre la ventana de cierre real."""
    S = esc.S
    T = modelo.tiempo_min
    fd = esc.factor_dia
    vini, vfin = esc.ventana_ini, esc.ventana_fin
    tard = np.zeros(S)
    for ruta in routes:
        if not ruta:
            continue
        t = np.zeros(S)
        prev = 0
        for node in ruta:
            td = _td_mult_vec(esc.franjas_td, t)
            viaje = float(T[prev][node]) * fd * td * esc.mult[:, node]
            viaje = viaje + esc.incidente[:, node] * (esc.incid_delay[node] * fd)
            t = t + viaje
            if vini[node] > 0.0:
                t = np.maximum(t, vini[node])         # esperar apertura de ventana
            tard += np.maximum(0.0, t - vfin[node])   # exceso sobre el cierre REAL de ventana
            t = t + esc.serv_eff[:, node]
            prev = node
    return tard


def evaluar_escenarios(routes: List[List[int]], modelo, w_tard: float, esc: EscenariosSAA,
                       alpha: float = 0.9, beta: float = 1.0, jornada_max: float = 0.0) -> dict:
    """Costo ROBUSTO (a minimizar) de una solucion: viaje deterministico + w_tard*(E[tardanza]
    + beta*CVaR_alpha(tardanza)) sobre los S escenarios, + penalizaciones de capacidad/no
    servidos/jornada. La tardanza se mide contra la ventana REAL (los escenarios ya modelan el
    riesgo; reemplazan al buffer SLA fijo)."""
    from core.alns import PEN_CAP, PEN_UNSERVED, _cap, _carga, _pen_jornada
    t_mat = modelo.tiempo_min
    travel = 0.0
    cap_viol = 0
    servidos = set()
    for r, ruta in enumerate(routes):
        if not ruta:
            continue
        if _carga(modelo, ruta, "m3") > _cap(modelo, r, "m3") + 1e-6:
            cap_viol += 1
        if _carga(modelo, ruta, "kg") > _cap(modelo, r, "kg") + 1e-6:
            cap_viol += 1
        prev = 0
        for c in ruta:
            travel += t_mat[prev][c]
            prev = c
            servidos.add(c)
        travel += t_mat[prev][0]
    unserved = (len(modelo.pedido_ids) - 1) - len(servidos)

    tard_vec = tardanza_por_escenario(routes, modelo, esc)
    mean_tard = float(tard_vec.mean()) if tard_vec.size else 0.0
    cvar_tard = float(_cvar(tard_vec, alpha)) if tard_vec.size else 0.0
    pen_jor = _pen_jornada(routes, modelo, jornada_max)
    costo = (travel + w_tard * (mean_tard + beta * cvar_tard)
             + PEN_CAP * cap_viol + PEN_UNSERVED * unserved + pen_jor)
    return {"costo": costo, "travel": travel, "tard": mean_tard, "tard_media": mean_tard,
            "cvar_tard": cvar_tard, "unserved": unserved, "cap_viol": cap_viol,
            "pen_jornada": pen_jor}


def _metricas_solucion(res: dict, modelo, val: EscenariosSAA, alpha: float) -> dict:
    """Metricas FUERA DE MUESTRA de una solucion sobre escenarios de validacion frescos."""
    routes = [[s.idx_nodo for s in rc.secuencia] for rc in res["best"]["rutas"].values()]
    tv = tardanza_por_escenario(routes, modelo, val)
    dist = round(sum(rc.distancia_km for rc in res["best"]["rutas"].values()), 2)
    servidos = sum(rc.n_paradas for rc in res["best"]["rutas"].values())
    return {
        "distancia_km": dist,
        "servidos": int(servidos),
        "tard_media_min": round(float(tv.mean()), 2) if tv.size else 0.0,
        "tard_p90_min": round(float(np.percentile(tv, 90)), 2) if tv.size else 0.0,
        "cvar_tard_min": round(float(_cvar(tv, alpha)), 2) if tv.size else 0.0,
    }


def comparar_robustez(modelo, params, incid_prob: Sequence[float], incid_delay: Sequence[float],
                      ausencia_prob: Sequence[float], *, warm: Optional[dict] = None,
                      alpha: float = 0.9, beta: float = 1.0, w_tard: float = 10.0,
                      n_train: Optional[int] = None, n_val: int = 200,
                      sigma_viaje: float = 0.25, sigma_sistemico: float = 0.10,
                      franjas_td: Optional[Sequence] = None, seed_train: Optional[int] = None,
                      seed_val: int = 99991) -> dict:
    """Benchmark 'robustez POR DISENO': corre el ALNS DETERMINISTA y el ALNS ROBUSTO (SAA+CVaR)
    sobre la MISMA instancia (mismo warm) y compara su tardanza FUERA DE MUESTRA sobre escenarios
    de validacion frescos (semilla distinta, mas numerosos). Devuelve las metricas de ambos y la
    reduccion de CVaR/variabilidad. Es la evidencia de que optimizar el objetivo robusto reduce
    la COLA de tardanza (a distancia similar), no solo en los escenarios de entrenamiento."""
    from core.alns import optimizar
    n_train = int(n_train if n_train is not None else getattr(params, "n_escenarios_saa", 20))
    seed_train = int(seed_train if seed_train is not None else getattr(params, "semilla_base", 42))
    train = construir_escenarios(modelo, incid_prob, incid_delay, ausencia_prob,
                                 n_escenarios=n_train, sigma_viaje=sigma_viaje,
                                 sigma_sistemico=sigma_sistemico, franjas_td=franjas_td,
                                 seed=seed_train)
    val = construir_escenarios(modelo, incid_prob, incid_delay, ausencia_prob,
                               n_escenarios=int(n_val), sigma_viaje=sigma_viaje,
                               sigma_sistemico=sigma_sistemico, franjas_td=franjas_td,
                               seed=int(seed_val))
    det = optimizar(modelo, params, warm=warm, w_tard=w_tard)
    rob = optimizar(modelo, params, warm=warm, w_tard=w_tard, escenarios=train,
                    alpha=alpha, beta=beta)
    m_det = _metricas_solucion(det, modelo, val, alpha)
    m_rob = _metricas_solucion(rob, modelo, val, alpha)
    return {
        "determinista": m_det,
        "robusto_saa": m_rob,
        "reduccion_cvar_min": round(m_det["cvar_tard_min"] - m_rob["cvar_tard_min"], 2),
        "reduccion_tard_media_min": round(m_det["tard_media_min"] - m_rob["tard_media_min"], 2),
        "sobrecosto_distancia_km": round(m_rob["distancia_km"] - m_det["distancia_km"], 2),
        "n_train": n_train, "n_val": int(n_val), "alpha": alpha, "beta": beta,
    }
