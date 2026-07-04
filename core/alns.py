"""ALNS (Adaptive Large Neighborhood Search) para CVRPTW del cerebro CORTEX-LM.

Metaheuristica de Ropke & Pisinger (2006): mejora una solucion inicial (tipicamente la de
OR-Tools) alternando operadores de DESTRUCCION (quitar clientes) y REPARACION (reinsertar),
con pesos ADAPTATIVOS por desempeño y aceptacion tipo recocido simulado. Produce soluciones
de alta calidad y un conjunto de elites DIVERSAS que luego se evaluan de forma robusta (DRO).

Trabaja sobre la matriz contextual y respeta capacidad (m3/kg), ventanas (con espera) y las
ventanas probabilisticas (buffer de nivel de servicio). Es heuristica: entrega soluciones de
alta calidad, no optimos garantizados.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from core.data_models import PerfilDecision
from core.optimizer_ortools import ModeloNumerico, ParadaRuta, RutaCandidata

PEN_CAP = 1e6
PEN_UNSERVED = 1e7


def _cap(modelo: ModeloNumerico, r: int, kind: str) -> float:
    caps = modelo.cap_m3 if kind == "m3" else modelo.cap_kg
    c = caps[r] if r < len(caps) else (caps[-1] if caps else 0.0)
    return c if c > 0 else float("inf")


def _carga(modelo, ruta, kind):
    dem = modelo.demanda_m3 if kind == "m3" else modelo.demanda_kg
    return sum(dem[c] for c in ruta)


def _evaluar(routes: List[List[int]], modelo: ModeloNumerico,
             buffer: Optional[List[float]], w_tard: float) -> dict:
    """Costo (a minimizar) y metricas de una solucion. Lateness usa el buffer SLA."""
    t_mat, serv, ven = modelo.tiempo_min, modelo.servicio_min, modelo.ventanas_min
    travel = tard = 0.0
    cap_viol = 0
    servidos = set()
    for r, ruta in enumerate(routes):
        if not ruta:
            continue
        if _carga(modelo, ruta, "m3") > _cap(modelo, r, "m3") + 1e-6:
            cap_viol += 1
        if _carga(modelo, ruta, "kg") > _cap(modelo, r, "kg") + 1e-6:
            cap_viol += 1
        t = 0.0
        prev = 0
        for c in ruta:
            t += t_mat[prev][c]
            travel += t_mat[prev][c]
            ini, fin = ven[c]
            if t < ini:
                t = ini
            fin_eff = max(ini, fin - (buffer[c] if buffer else 0.0))
            if t > fin_eff:
                tard += (t - fin_eff)
            t += serv[c]
            prev = c
            servidos.add(c)
        travel += t_mat[prev][0]
    unserved = (len(modelo.pedido_ids) - 1) - len(servidos)
    costo = travel + w_tard * tard + PEN_CAP * cap_viol + PEN_UNSERVED * unserved
    return {"costo": costo, "travel": travel, "tard": tard, "unserved": unserved,
            "cap_viol": cap_viol}


def _copiar(routes):
    return [list(r) for r in routes]


# --------------------------------------------------------------------------- #
# Operadores de destruccion
# --------------------------------------------------------------------------- #
def _todos(routes):
    return [(r, i, c) for r, ruta in enumerate(routes) for i, c in enumerate(ruta)]


def destruir_aleatorio(routes, q, modelo, rng):
    clientes = [c for ruta in routes for c in ruta]
    rng.shuffle(clientes)
    quitar = set(clientes[:q])
    for ruta in routes:
        ruta[:] = [c for c in ruta if c not in quitar]
    return list(quitar)


def destruir_peor(routes, q, modelo, rng):
    t = modelo.tiempo_min
    detours = []
    for r, ruta in enumerate(routes):
        for i, c in enumerate(ruta):
            prev = ruta[i - 1] if i > 0 else 0
            nxt = ruta[i + 1] if i < len(ruta) - 1 else 0
            det = t[prev][c] + t[c][nxt] - t[prev][nxt]
            detours.append((det, c))
    detours.sort(reverse=True)
    quitar = set(c for _, c in detours[:q])
    for ruta in routes:
        ruta[:] = [c for c in ruta if c not in quitar]
    return list(quitar)


# --------------------------------------------------------------------------- #
# Operadores de reparacion
# --------------------------------------------------------------------------- #
def _mejor_insercion(routes, c, modelo):
    """(costo, r, pos) de la mejor insercion factible de c (o None). Respeta capacidad y
    cuadrilla: un pedido de instalacion solo entra en la ruta de un vehiculo con cuadrilla."""
    t = modelo.tiempo_min
    req = modelo.requiere_cuadrilla or []
    vc = modelo.vehiculo_cuadrilla or []
    necesita_crew = bool(vc and c < len(req) and req[c] and not all(vc))
    mejor = None
    for r, ruta in enumerate(routes):
        if necesita_crew and not (r < len(vc) and vc[r]):
            continue
        if (_carga(modelo, ruta, "m3") + modelo.demanda_m3[c] > _cap(modelo, r, "m3") + 1e-6 or
                _carga(modelo, ruta, "kg") + modelo.demanda_kg[c] > _cap(modelo, r, "kg") + 1e-6):
            continue
        for pos in range(len(ruta) + 1):
            prev = ruta[pos - 1] if pos > 0 else 0
            nxt = ruta[pos] if pos < len(ruta) else 0
            costo = t[prev][c] + t[c][nxt] - t[prev][nxt]
            if mejor is None or costo < mejor[0]:
                mejor = (costo, r, pos)
    return mejor


def reparar_greedy(routes, removidos, modelo, rng):
    rng.shuffle(removidos)
    for c in removidos:
        m = _mejor_insercion(routes, c, modelo)
        if m is None:
            routes.append([c])           # nueva ruta si no cabe en ninguna
        else:
            routes[m[1]].insert(m[2], c)


def reparar_regret(routes, removidos, modelo, rng):
    pend = list(removidos)
    while pend:
        mejor_c, mejor_regret, mejor_ins = None, -1.0, None
        for c in pend:
            costos = []
            for r, ruta in enumerate(routes):
                m = _mejor_insercion([ruta], c, modelo)  # costo en esa ruta
                if m is not None:
                    costos.append((m[0], r, m[2]))
            costos.sort()
            if not costos:
                ins = None
                regret = PEN_UNSERVED
            else:
                mejor_local = costos[0]
                segundo = costos[1][0] if len(costos) > 1 else mejor_local[0] + 1000.0
                regret = segundo - mejor_local[0]
                ins = mejor_local
            if regret > mejor_regret:
                mejor_c, mejor_regret, mejor_ins = c, regret, ins
        pend.remove(mejor_c)
        if mejor_ins is None:
            routes.append([mejor_c])
        else:
            routes[mejor_ins[1]].insert(mejor_ins[2], mejor_c)


# --------------------------------------------------------------------------- #
# Conversion a resultado (compatible con robust_evaluation / escenario)
# --------------------------------------------------------------------------- #
def _a_resultado(routes, modelo, perfil_nombre) -> dict:
    t, serv, ven = modelo.tiempo_min, modelo.servicio_min, modelo.ventanas_min
    rutas = {}
    servidos = set()
    v = 0
    for ruta in routes:
        if not ruta:
            continue
        veh = modelo.vehiculo_ids[v] if v < len(modelo.vehiculo_ids) else f"V{v+1:03d}"
        v += 1
        rc = RutaCandidata(vehiculo_id=veh)
        tt = 0.0
        prev = 0
        cm3 = ckg = dist = 0.0
        for c in ruta:
            tt += t[prev][c]
            dist += modelo.dist_km[prev][c]
            ini, fin = ven[c]
            if tt < ini:
                tt = ini
            cm3 += modelo.demanda_m3[c]
            ckg += modelo.demanda_kg[c]
            rc.secuencia.append(ParadaRuta(
                idx_nodo=c, pedido_id=modelo.pedido_ids[c], eta_min=float(tt),
                carga_m3_acum=round(cm3, 3), carga_kg_acum=round(ckg, 2),
                tardanza_min=float(max(0.0, tt - fin)),
                distancia_km_acum=round(dist, 3)))
            tt += serv[c]
            prev = c
            servidos.add(c)
        dist += modelo.dist_km[prev][0]
        rc.distancia_km = round(dist, 3)
        rc.tiempo_min = round(tt + t[prev][0], 1)
        rc.tardanza_total_min = round(sum(s.tardanza_min for s in rc.secuencia), 2)
        rutas[veh] = rc
    no_servidos = [k for k in range(1, len(modelo.pedido_ids)) if k not in servidos]
    return {"status": "ok", "rutas": rutas, "no_servidos": no_servidos, "perfil": perfil_nombre}


# --------------------------------------------------------------------------- #
# Bucle ALNS
# --------------------------------------------------------------------------- #
def _desde_warm(warm: dict, nv: int) -> List[List[int]]:
    routes = [[] for _ in range(max(nv, len(warm.get("rutas", {}))))]
    for i, rc in enumerate(warm.get("rutas", {}).values()):
        routes[i] = [s.idx_nodo for s in rc.secuencia]
    return routes


def optimizar(modelo: ModeloNumerico, params, *, perfil: Optional[PerfilDecision] = None,
              buffer_sla=None, warm: Optional[dict] = None, w_tard: float = 10.0,
              n_elites: int = 3) -> dict:
    """Ejecuta ALNS. Devuelve {'best': resultado, 'elites': [resultado,...]}."""
    rng = random.Random(int(params.semilla_base))
    nv = int(modelo.num_vehiculos)
    N = len(modelo.pedido_ids) - 1
    nombre = f"alns-{perfil.perfil}" if perfil else "alns"

    if warm and warm.get("rutas"):
        routes = _desde_warm(warm, nv)
    else:
        routes = [[] for _ in range(nv)]
        reparar_regret(routes, list(range(1, N + 1)), modelo, rng)

    cur = routes
    cur_m = _evaluar(cur, modelo, buffer_sla, w_tard)
    best, best_m = _copiar(cur), dict(cur_m)
    elites = [(best_m["costo"], _copiar(best))]

    destruir = [destruir_aleatorio, destruir_peor]
    reparar = [reparar_greedy, reparar_regret]
    wd = [1.0, 1.0]
    wr = [1.0, 1.0]
    sd = [0.0, 0.0]
    sr = [0.0, 0.0]
    cd = [0, 0]
    cr = [0, 0]

    iters = int(getattr(params, "iteraciones_alns", 250))
    T = max(1.0, 0.05 * best_m["costo"])
    cooling = (1e-3) ** (1.0 / max(1, iters))
    qmin, qmax = 1, max(1, min(int(0.3 * N) + 1, 12))

    def _elige(w):
        tot = sum(w)
        x = rng.random() * tot
        acc = 0.0
        for i, wi in enumerate(w):
            acc += wi
            if x <= acc:
                return i
        return len(w) - 1

    for it in range(iters):
        di = _elige(wd)
        ri = _elige(wr)
        q = rng.randint(qmin, qmax)
        cand = _copiar(cur)
        removidos = destruir[di](cand, q, modelo, rng)
        reparar[ri](cand, removidos, modelo, rng)
        cand_m = _evaluar(cand, modelo, buffer_sla, w_tard)

        cd[di] += 1
        cr[ri] += 1
        premio = 0.0
        if cand_m["costo"] < best_m["costo"] - 1e-9:
            best, best_m = _copiar(cand), dict(cand_m)
            elites.append((cand_m["costo"], _copiar(cand)))
            premio = 3.0
        elif cand_m["costo"] < cur_m["costo"] - 1e-9:
            premio = 2.0
        elif rng.random() < math.exp(-(cand_m["costo"] - cur_m["costo"]) / max(T, 1e-9)):
            premio = 1.0
        if premio > 0 and cand_m["costo"] < cur_m["costo"] + T:
            cur, cur_m = cand, cand_m
        sd[di] += premio
        sr[ri] += premio
        T *= cooling
        if (it + 1) % 30 == 0:      # actualizacion adaptativa de pesos
            for i in range(2):
                if cd[i]:
                    wd[i] = 0.8 * wd[i] + 0.2 * (sd[i] / cd[i])
                if cr[i]:
                    wr[i] = 0.8 * wr[i] + 0.2 * (sr[i] / cr[i])
            sd = [0.0, 0.0]; sr = [0.0, 0.0]; cd = [0, 0]; cr = [0, 0]

    # elites diversas por costo (unicas)
    elites.sort(key=lambda e: e[0])
    vistos = set()
    res_elites = []
    for _, sol in elites:
        clave = tuple(tuple(r) for r in sol if r)
        if clave in vistos:
            continue
        vistos.add(clave)
        res_elites.append(_a_resultado(sol, modelo, nombre))
        if len(res_elites) >= n_elites + 1:
            break
    return {"best": _a_resultado(best, modelo, nombre),
            "elites": res_elites[1:] if len(res_elites) > 1 else []}
