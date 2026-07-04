"""Modelo de incertidumbre y conjunto de ambiguedad (DRO) del cerebro CORTEX-LM.

Dos responsabilidades:
  1. Derivar la incertidumbre POR NODO (probabilidad/impacto de incidencia y ausencia del
     cliente) a partir de los datos de contexto (incidencias.xlsx + zonas). Esto conecta las
     incidencias a la simulacion de planificacion (antes se ignoraban).
  2. Definir el CONJUNTO DE AMBIGUEDAD para Optimizacion Distribucionalmente Robusta (DRO):
     un conjunto de configuraciones de la distribucion (nominal + "Lima peor") sobre el que
     se evalua el PEOR CASO. Como los datos son sinteticos y solo aproximan a Lima, no se
     confia en la distribucion nominal: se busca robustez ante distribuciones vecinas.

El "radio de ambiguedad" es implicito en cuanto se alejan las configuraciones del nominal;
es un parametro de diseno, justificable y ajustable (mas adelante, por backtesting con datos
reales). NO se conecta a ninguna API externa.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class ConfigIncertidumbre:
    """Una distribucion del conjunto de ambiguedad (escenario de incertidumbre)."""
    nombre: str
    sigma_viaje: float          # dispersion log-normal IDIOSINCRATICA del viaje (por tramo)
    mult_incidencia: float      # escala la probabilidad de incidencia
    mult_congestion: float      # escala (infla) los tiempos base
    mult_ausencia: float        # escala la probabilidad de ausencia
    # Variabilidad SISTEMICA (correlacionada): un factor por DIA que afecta a todos los tramos
    # a la vez (un dia de lluvia/paro pone lenta media Lima). Es la que NO se promedia y genera
    # la variabilidad real del OTD dia a dia.
    sigma_sistemico: float = 0.10


def conjunto_ambiguedad(radio: str = "medio") -> List[ConfigIncertidumbre]:
    """Conjunto de ambiguedad DRO (variante parametrica). `radio` controla que tan lejos del
    nominal se explora (mayor radio = mas robusto y mas conservador)."""
    nominal = ConfigIncertidumbre("nominal", 0.25, 1.0, 1.00, 1.0, sigma_sistemico=0.10)
    if radio == "bajo":
        peores = [ConfigIncertidumbre("congestion_alta", 0.30, 1.2, 1.06, 1.10, sigma_sistemico=0.13)]
    elif radio == "alto":
        peores = [ConfigIncertidumbre("congestion_alta", 0.34, 1.4, 1.12, 1.20, sigma_sistemico=0.16),
                  ConfigIncertidumbre("dia_critico", 0.42, 1.8, 1.20, 1.40, sigma_sistemico=0.24)]
    else:  # medio
        peores = [ConfigIncertidumbre("congestion_alta", 0.32, 1.3, 1.10, 1.15, sigma_sistemico=0.15),
                  ConfigIncertidumbre("dia_critico", 0.38, 1.6, 1.15, 1.30, sigma_sistemico=0.22)]
    return [nominal] + peores


def perfil_td_franjas(trafico: Sequence, jornada_inicio: str = "09:00",
                      hora_ref: str = "09:00") -> List[Tuple[float, float, float]]:
    """Perfil de trafico DEPENDIENTE DE LA HORA para la simulacion (TD-VRP).

    La matriz contextual ya lleva HORNEADO el factor de `hora_ref`. Este perfil devuelve, por
    franja, el multiplicador RELATIVO `f_traf(franja) / f_traf(hora_ref)` (en minutos desde el
    inicio de jornada), para que un tramo recorrido a las 18:00 sea mas lento que a las 11:00
    sin duplicar el factor ya horneado. Formato: [(ini_min, fin_min, mult), ...].
    """
    from utils.formatters import hhmm_to_minutes
    t0 = hhmm_to_minutes(jornada_inicio)
    glob = [f for f in (trafico or [])
            if (not getattr(f, "macrozona", "")
                or str(f.macrozona).lower() in ("", "todas", "todos"))]
    glob = glob or list(trafico or [])
    tr = hhmm_to_minutes(hora_ref)
    f_ref = 1.0
    for f in glob:
        if hhmm_to_minutes(f.hora_inicio) <= tr <= hhmm_to_minutes(f.hora_fin):
            f_ref = float(f.factor_trafico)
            break
    franjas = []
    for f in glob:
        ini = float(hhmm_to_minutes(f.hora_inicio) - t0)
        fin = float(hhmm_to_minutes(f.hora_fin) - t0)
        mult = round(float(f.factor_trafico) / f_ref, 4) if f_ref else 1.0
        franjas.append((ini, fin, mult))
    return sorted(franjas)


def _idx_macrozona(zonas) -> dict:
    return {z.distrito: z.macrozona for z in (zonas or [])}


def probabilidades_por_nodo(pedidos: Sequence, incidencias: Sequence, zonas: Sequence,
                            franja: Optional[str] = None
                            ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Deriva, por nodo (0 = HUB; 1..N = pedidos), la probabilidad e impacto de incidencia y
    la probabilidad de ausencia del cliente, cruzando con incidencias.xlsx y zonas."""
    mz = _idx_macrozona(zonas)
    n = len(pedidos) + 1
    incid_prob = np.zeros(n)
    incid_delay = np.zeros(n)
    ausencia = np.zeros(n)
    for k, p in enumerate(pedidos, start=1):
        macro = mz.get(p.distrito, "")
        prob, delay = 0.0, 0.0
        for inc in (incidencias or []):
            afecta = ((inc.distrito and inc.distrito == p.distrito)
                      or (inc.macrozona and inc.macrozona == macro))
            if not afecta:
                continue
            if franja and inc.franja and inc.franja != franja:
                continue
            if inc.probabilidad > prob:       # se toma la incidencia mas probable del nodo
                prob, delay = inc.probabilidad, inc.duracion_min
        incid_prob[k] = prob
        incid_delay[k] = delay
        # Ausencia: residencial es mas propenso a no estar que comercial (heuristica documentada).
        ausencia[k] = 0.08 if str(p.detalle_cliente).lower().startswith("resid") else 0.04
    return incid_prob, incid_delay, ausencia


def aplicar_config(incid_prob: np.ndarray, ausencia: np.ndarray,
                   cfg: ConfigIncertidumbre) -> Tuple[np.ndarray, np.ndarray]:
    """Escala las probabilidades por nodo segun una configuracion del conjunto de ambiguedad,
    acotando a [0, 1]."""
    ip = np.clip(incid_prob * cfg.mult_incidencia, 0.0, 1.0)
    au = np.clip(ausencia * cfg.mult_ausencia, 0.0, 1.0)
    return ip, au


# --------------------------------------------------------------------------- #
# Ventanas probabilisticas (chance-constrained): buffer de nivel de servicio
# --------------------------------------------------------------------------- #
# Cuantil normal z_alpha para el nivel de servicio alpha (P(a tiempo) >= alpha).
_Z_ALPHA = {0.80: 0.8416, 0.85: 1.0364, 0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600}


def z_alpha(alpha: float) -> float:
    return _Z_ALPHA[min(_Z_ALPHA, key=lambda k: abs(k - alpha))]


def buffer_sla_por_nodo(tiempo_min, cv: float = 0.25, alpha: float = 0.9) -> List[float]:
    """Buffer de seguridad por nodo (min) para VENTANAS PROBABILISTICAS.

    En vez de un margen fijo, el buffer del cliente j crece con la variabilidad esperada del
    tiempo para alcanzarlo: `buffer_j = z_alpha * cv * T[0][j]` (T = matriz contextual). Asi
    los clientes mas lejanos/congestionados reciben mas colchon, aproximando la restriccion
    `P(llegada_j <= cierre_j) >= alpha`. Es una aproximacion documentada (la varianza real se
    acumula a lo largo de la ruta; aqui se usa el tiempo directo como proxy monotono).
    """
    z = z_alpha(alpha)
    T0 = np.asarray(tiempo_min, dtype=float)[0]
    return [float(z * cv * T0[j]) for j in range(len(T0))]   # nodo 0 = 0 (T0[0]=0)
