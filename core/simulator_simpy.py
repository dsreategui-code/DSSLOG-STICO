"""Simulacion estocastica de la operacion (SimPy) para el motor CORTEX-LM.

Simula por EVENTOS DISCRETOS la ejecucion de una solucion (conjunto de rutas candidatas)
bajo variabilidad: tiempo de viaje aleatorio (log-normal de media 1 sobre la matriz
contextual), tiempo de servicio triangular, incidencias (demoras puntuales), ausencia del
cliente (afecta First Attempt Success) y espera a la apertura de ventana. Cada vehiculo es
un proceso SimPy independiente (custodia logistica por vehiculo: no hay trasiego entre
camiones).

Monte Carlo: N realizaciones reproducibles (semilla por iteracion). Produce muestras por
pedido para estimar el Indice de Riesgo de Incumplimiento y los KPIs (ver core.risk_engine).

Es simulacion: trabaja con distribuciones, NO con trafico real ni tiempos fisicos reales.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import simpy


@dataclass
class ContextoSim:
    """Insumos numericos de la simulacion. Nodo 0 = HUB."""
    tiempo_min: np.ndarray                  # NxN matriz contextual (deterministica base)
    rutas: Dict[str, List[int]]             # vehiculo -> secuencia de nodos (sin contar HUB inicial repetido)
    ventana_ini: List[float]
    ventana_fin: List[float]
    serv_min: List[float]
    serv_moda: List[float]
    serv_max: List[float]
    pedido_ids: List[str]
    incid_prob: List[float] = field(default_factory=list)
    incid_delay_min: List[float] = field(default_factory=list)
    ausencia_prob: List[float] = field(default_factory=list)
    sigma_viaje: float = 0.25                # dispersion IDIOSINCRATICA por tramo
    sigma_sistemico: float = 0.0             # variabilidad SISTEMICA por dia (correlacionada)
    # Perfil dependiente de la hora (TD): [(ini_min, fin_min, mult)], mult relativo a hora_ref.
    franjas_td: List[Tuple[float, float, float]] = field(default_factory=list)
    permitir_reintento: bool = True
    penal_reintento_min: float = 10.0

    def __post_init__(self):
        n = int(self.tiempo_min.shape[0])
        if not self.incid_prob:
            self.incid_prob = [0.0] * n
        if not self.incid_delay_min:
            self.incid_delay_min = [0.0] * n
        if not self.ausencia_prob:
            self.ausencia_prob = [0.0] * n


def _td_mult(franjas: List[Tuple[float, float, float]], t: float) -> float:
    """Multiplicador de trafico dependiente de la hora en el minuto `t` (1.0 si no hay perfil)."""
    for ini, fin, m in franjas:
        if ini <= t <= fin:
            return m
    return 1.0


def _proceso_vehiculo(env: "simpy.Environment", veh_id: str, ruta: List[int],
                      ctx: ContextoSim, rng: random.Random, registros: list,
                      factor_dia: float = 1.0):
    """Proceso SimPy de un vehiculo: recorre su ruta acumulando tiempos estocasticos.

    `factor_dia`: factor SISTEMICO comun a todos los vehiculos de la corrida (correlacion).
    El tiempo de viaje ademas depende de la HORA de salida del tramo (TD, `franjas_td`).
    """
    mu = -0.5 * ctx.sigma_viaje ** 2          # asegura E[multiplicador idiosincratico] = 1
    prev = ruta[0]                            # HUB (0)
    for node in ruta[1:]:
        td = _td_mult(ctx.franjas_td, env.now)         # congestion segun la hora de salida
        viaje = (float(ctx.tiempo_min[prev][node]) * factor_dia * td
                 * rng.lognormvariate(mu, ctx.sigma_viaje))
        if rng.random() < ctx.incid_prob[node]:
            viaje += ctx.incid_delay_min[node] * factor_dia   # un dia malo alarga las incidencias
        yield env.timeout(max(0.0, viaje))
        llegada = env.now
        if llegada < ctx.ventana_ini[node]:    # esperar apertura de ventana
            yield env.timeout(ctx.ventana_ini[node] - llegada)
        ausente = rng.random() < ctx.ausencia_prob[node]
        serv = rng.triangular(ctx.serv_min[node], ctx.serv_max[node], ctx.serv_moda[node])
        if ausente and ctx.permitir_reintento:
            serv += ctx.penal_reintento_min
        yield env.timeout(max(0.0, serv))
        fin = ctx.ventana_fin[node]
        registros.append({
            "vehiculo_id": veh_id, "pedido_id": ctx.pedido_ids[node], "idx_nodo": node,
            "eta_min": float(llegada), "ventana_fin": float(fin),
            "a_tiempo": bool(llegada <= fin + 1e-9),
            "tardanza_min": float(max(0.0, llegada - fin)),
            "primer_intento_ok": bool(not ausente),
        })
        prev = node


def simular_una_corrida(ctx: ContextoSim, seed: int = 0) -> List[dict]:
    """Una realizacion estocastica de toda la operacion. Devuelve registros por entrega."""
    env = simpy.Environment()
    rng = random.Random(seed)
    registros: list = []
    # Factor SISTEMICO del dia: se sortea UNA vez y afecta a TODOS los vehiculos de la corrida
    # (correlacion). E[factor_dia] = 1. Un dia "malo" pone lenta media Lima a la vez.
    if ctx.sigma_sistemico and ctx.sigma_sistemico > 0:
        factor_dia = rng.lognormvariate(-0.5 * ctx.sigma_sistemico ** 2, ctx.sigma_sistemico)
    else:
        factor_dia = 1.0
    for veh_id, ruta in ctx.rutas.items():
        seq = ruta if ruta and ruta[0] == 0 else [0] + list(ruta)
        env.process(_proceso_vehiculo(env, veh_id, seq, ctx, rng, registros, factor_dia))
    env.run()
    return registros


def montecarlo(ctx: ContextoSim, iteraciones: int = 100, semilla_base: int = 42) -> pd.DataFrame:
    """N realizaciones reproducibles. Devuelve un DataFrame de muestras (una fila por
    (pedido, iteracion))."""
    filas = []
    for it in range(iteraciones):
        for reg in simular_una_corrida(ctx, seed=semilla_base + it * 7):
            reg = dict(reg)
            reg["iteracion"] = it
            filas.append(reg)
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------- #
# Constructor desde una ruta candidata del optimizador CORTEX
# --------------------------------------------------------------------------- #
def contexto_desde_resultado(resultado: dict, modelo, *,
                             incid_prob: Optional[Sequence[float]] = None,
                             incid_delay_min: Optional[Sequence[float]] = None,
                             ausencia_prob: Optional[Sequence[float]] = None,
                             sigma_viaje: float = 0.25, sigma_sistemico: float = 0.0,
                             franjas_td: Optional[Sequence] = None) -> ContextoSim:
    """Construye el ContextoSim desde un resultado de core.optimizer_ortools + ModeloNumerico.

    El tiempo de servicio triangular se deriva del valor de planificacion (moda) con una
    banda por defecto; los valores reales min/moda/max provienen de tiempos_servicio.xlsx
    cuando esten disponibles.
    """
    n = int(modelo.tiempo_min.shape[0])
    rutas = {veh: [0] + [s.idx_nodo for s in rc.secuencia]
             for veh, rc in resultado.get("rutas", {}).items()}
    moda = list(modelo.servicio_min)
    serv_min = [max(0.0, 0.6 * m) for m in moda]
    serv_max = [1.8 * m if m > 0 else 0.0 for m in moda]
    return ContextoSim(
        tiempo_min=np.asarray(modelo.tiempo_min, dtype=float), rutas=rutas,
        ventana_ini=[v[0] for v in modelo.ventanas_min],
        ventana_fin=[v[1] for v in modelo.ventanas_min],
        serv_min=serv_min, serv_moda=moda, serv_max=serv_max,
        pedido_ids=list(modelo.pedido_ids),
        incid_prob=list(incid_prob) if incid_prob is not None else [0.0] * n,
        incid_delay_min=list(incid_delay_min) if incid_delay_min is not None else [0.0] * n,
        ausencia_prob=list(ausencia_prob) if ausencia_prob is not None else [0.0] * n,
        sigma_viaje=sigma_viaje, sigma_sistemico=sigma_sistemico,
        franjas_td=list(franjas_td) if franjas_td is not None else [],
    )
