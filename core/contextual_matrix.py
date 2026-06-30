"""Matriz contextual de tiempos del motor CORTEX-LM.

Ajusta la matriz BASE de tiempos de OSRM (o de cache/precomputada) por el contexto urbano
de Lima Metropolitana, de forma MULTIPLICATIVA y TRAZABLE:

    T_contextual[i][j] = T_base[i][j] * F_trafico[j] * F_zona[j] * F_evento[j]
                                     * F_seguridad[j] * F_servicio[j] * F_incidencia[j]

Los factores se resuelven por NODO DESTINO j (la dificultad se concentra en la zona a la
que se llega: acceso, estacionamiento, seguridad, franja horaria, evento del calendario e
incidencias activas conocidas). Es una simplificacion documentada: el arco (i, j) hereda la
dificultad contextual del destino j. Cada factor se acota a un rango razonable para evitar
matrices degeneradas. La funcion devuelve ademas el desglose por nodo para que el DSS pueda
EXPLICAR por que un tramo es mas lento.

Notas honestas:
  - El trafico es un factor por franja/macrozona tomado de tablas (NO trafico real de API).
  - Las incidencias en planificacion son estocasticas (van en la simulacion); aqui solo se
    aplican incidencias CONOCIDAS/ACTIVAS (p. ej. durante una replanificacion).
  - F_servicio aproxima sobrecostos de aproximacion/estacionamiento del destino; la DURACION
    de servicio en si se modela aparte (tiempos_servicio en la simulacion SimPy).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from core.data_models import (EventoCalendario, FranjaTrafico, Hub, Incidencia,
                              Pedido, Zona)
from utils.formatters import hhmm_to_minutes

CLAMP_FACTOR = (0.5, 3.0)        # rango admisible de cada factor multiplicativo
CLAMP_TOTAL = (0.5, 6.0)         # rango admisible del factor total por nodo


def _clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def construir_nodos(hub: Hub, pedidos: Sequence[Pedido]) -> List[dict]:
    """Lista de nodos del problema: nodo 0 = HUB, 1..N = pedidos (en orden)."""
    nodos = [{"idx": 0, "distrito": hub.distrito, "tipo_pedido": "hub",
              "requiere_instalacion": False, "es_hub": True}]
    for k, p in enumerate(pedidos, start=1):
        nodos.append({"idx": k, "distrito": p.distrito, "tipo_pedido": p.tipo_pedido,
                      "requiere_instalacion": p.requiere_instalacion, "es_hub": False})
    return nodos


def resolver_franja(hora_hhmm: str, trafico: Sequence[FranjaTrafico],
                    macrozona: Optional[str] = None) -> Optional[FranjaTrafico]:
    """Devuelve la FranjaTrafico cuyo rango horario contiene `hora_hhmm` (y macrozona si se
    indica). None si no hay coincidencia."""
    t = hhmm_to_minutes(hora_hhmm)
    candidatas = [f for f in trafico if (macrozona is None or f.macrozona == macrozona
                                         or f.macrozona in ("", "todas"))]
    for f in candidatas:
        ini, fin = hhmm_to_minutes(f.hora_inicio), hhmm_to_minutes(f.hora_fin)
        if ini <= t <= fin:
            return f
    return None


def _indice_zonas(zonas: Sequence[Zona]) -> Dict[str, Zona]:
    return {z.distrito: z for z in zonas}


def _macrozona_de(distrito: str, zidx: Dict[str, Zona]) -> str:
    z = zidx.get(distrito)
    return z.macrozona if z else ""


def factores_por_nodo(nodos: List[dict], zonas: Sequence[Zona],
                      trafico: Sequence[FranjaTrafico],
                      eventos: Optional[Sequence[EventoCalendario]] = None,
                      incidencias_activas: Optional[Sequence[Incidencia]] = None,
                      fecha: Optional[str] = None, hora_ref: str = "09:00",
                      clamp: tuple = CLAMP_FACTOR) -> pd.DataFrame:
    """Desglose TRAZABLE de factores por nodo destino. Nodo 0 (HUB) = todos 1.0."""
    zidx = _indice_zonas(zonas)
    eventos = list(eventos or [])
    incidencias_activas = list(incidencias_activas or [])
    lo, hi = clamp

    filas = []
    for nodo in nodos:
        distrito = nodo["distrito"]
        macro = _macrozona_de(distrito, zidx)
        if nodo["es_hub"]:
            filas.append({"idx": 0, "distrito": distrito, "macrozona": macro,
                          "f_trafico": 1.0, "f_zona": 1.0, "f_evento": 1.0,
                          "f_seguridad": 1.0, "f_servicio": 1.0, "f_incidencia": 1.0,
                          "f_total": 1.0})
            continue

        z = zidx.get(distrito)
        # F_zona: acceso x estacionamiento del destino.
        f_zona = _clamp((z.factor_acceso * z.factor_estacionamiento) if z else 1.0, lo, hi)
        # F_seguridad: > 1 penaliza zonas de mayor riesgo.
        f_seg = _clamp(z.factor_seguridad if z else 1.0, lo, hi)
        # F_trafico: por franja horaria de referencia + macrozona.
        fr = resolver_franja(hora_ref, trafico, macro)
        f_traf = _clamp(fr.factor_trafico if fr else 1.0, lo, hi)
        # F_evento: producto de eventos del calendario activos en `fecha` que afecten al nodo.
        f_evt = 1.0
        for ev in eventos:
            if fecha is not None and str(ev.fecha) != str(fecha):
                continue
            za = str(ev.zonas_afectadas).strip().lower()
            global_ = za in ("", "todas", "todos")
            if global_ or distrito.lower() in za or macro.lower() in za:
                f_evt *= ev.factor_trafico
        f_evt = _clamp(f_evt, lo, hi)
        # F_servicio: sobrecosto de aproximacion del destino (instalacion = mas complejo).
        f_serv = 1.15 if nodo.get("requiere_instalacion") else 1.0
        f_serv = _clamp(f_serv, lo, hi)
        # F_incidencia: incidencias conocidas/activas que afectan al destino.
        f_inc = 1.0
        for inc in incidencias_activas:
            afecta = ((inc.distrito and inc.distrito == distrito)
                      or (inc.macrozona and inc.macrozona == macro))
            if afecta:
                f_inc *= inc.impacto_tiempo
        f_inc = _clamp(f_inc, lo, hi)

        f_total = _clamp(f_traf * f_zona * f_evt * f_seg * f_serv * f_inc,
                         CLAMP_TOTAL[0], CLAMP_TOTAL[1])
        filas.append({"idx": nodo["idx"], "distrito": distrito, "macrozona": macro,
                      "f_trafico": round(f_traf, 4), "f_zona": round(f_zona, 4),
                      "f_evento": round(f_evt, 4), "f_seguridad": round(f_seg, 4),
                      "f_servicio": round(f_serv, 4), "f_incidencia": round(f_inc, 4),
                      "f_total": round(f_total, 4)})
    return pd.DataFrame(filas)


def construir_matriz_contextual(base_min: np.ndarray, nodos: List[dict],
                                zonas: Sequence[Zona], trafico: Sequence[FranjaTrafico],
                                eventos: Optional[Sequence[EventoCalendario]] = None,
                                incidencias_activas: Optional[Sequence[Incidencia]] = None,
                                fecha: Optional[str] = None, hora_ref: str = "09:00",
                                clamp: tuple = CLAMP_FACTOR) -> dict:
    """Devuelve {'matriz': ndarray NxN contextual, 'factores': DataFrame, 'formula': str,
    'base': ndarray}. El arco (i, j) se multiplica por el factor total del destino j."""
    base_min = np.asarray(base_min, dtype=float)
    n = base_min.shape[0]
    factores = factores_por_nodo(nodos, zonas, trafico, eventos, incidencias_activas,
                                 fecha, hora_ref, clamp)
    f_total = factores.set_index("idx")["f_total"].reindex(range(n)).fillna(1.0).to_numpy()

    matriz = base_min * f_total[np.newaxis, :]   # cada columna j escalada por f_total[j]
    np.fill_diagonal(matriz, 0.0)
    return {
        "matriz": np.round(matriz, 4),
        "factores": factores,
        "base": base_min,
        "formula": "T_contextual[i][j] = T_base[i][j] * (F_trafico * F_zona * F_evento "
                   "* F_seguridad * F_servicio * F_incidencia)[j]",
    }
