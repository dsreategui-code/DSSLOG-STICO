"""Reporte unificado de KPIs del motor CORTEX-LM (para dashboards y export).

Toma la salida del pipeline (core.planner.planificar) y arma tablas tidy: comparacion de
candidatas, IRI por pedido y KPIs de la solucion recomendada. No recalcula nada: solo
organiza lo ya estimado por simulacion/riesgo.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

COLUMNAS_CANDIDATAS = ["perfil", "cobertura", "otd", "otif", "tardanza_prom_min",
                       "tardanza_p90_min", "pedidos_en_riesgo", "distancia_km",
                       "tiempo_max_min", "n_rutas"]


def tabla_candidatas(resultado: dict) -> pd.DataFrame:
    """Comparacion de rutas candidatas (una fila por perfil) con KPIs plan + simulacion."""
    evals = resultado.get("evaluaciones", [])
    filas = [{"perfil": e["perfil"], **e["kpis"]} for e in evals]
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    cols = [c for c in COLUMNAS_CANDIDATAS if c in df.columns]
    otras = [c for c in df.columns if c not in cols]
    return df[cols + otras]


def tabla_iri(resultado: dict) -> pd.DataFrame:
    """IRI por pedido de la candidata recomendada."""
    iri = resultado.get("iri_recomendada")
    return iri.copy() if iri is not None else pd.DataFrame(
        columns=["pedido_id", "vehiculo_id", "ventana_fin", "eta_p50", "eta_p90",
                 "iri", "clasificacion"])


def kpis_recomendada(resultado: dict) -> dict:
    """KPIs de la solucion recomendada (la candidata elegida)."""
    reco = resultado.get("perfil_recomendado")
    for e in resultado.get("evaluaciones", []):
        if e["perfil"] == reco:
            return {"perfil": reco, **e["kpis"]}
    return {}
