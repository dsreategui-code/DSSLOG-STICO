"""Recomendador explicable del DSS CORTEX-LM.

Selecciona entre las rutas candidatas (una por perfil de decision) usando una FUNCION DE
UTILIDAD DSS que NO prioriza solo la menor distancia: pondera cumplimiento (OTD/OTIF),
tardanza (P90), pedidos en riesgo y costo operativo, y exige cobertura. Devuelve la
candidata recomendada, el ranking y una EXPLICACION en lenguaje natural con la comparacion
frente a las demas. Trabaja con estimaciones de simulacion; recomienda, no garantiza.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from core.risk_engine import calcular_iri, kpis_montecarlo
from core.simulator_simpy import contexto_desde_resultado, montecarlo

# Pesos de la utilidad DSS. Signo: + (mas es mejor) / - (menos es mejor).
PESOS_DEFECTO: Dict[str, float] = {
    "otd": 1.0,
    "otif": 0.8,
    "tardanza_p90_min": -0.6,
    "pedidos_en_riesgo": -0.7,
    "distancia_km": -0.3,
    "tiempo_max_min": -0.2,
}
# La cobertura no se normaliza: se penaliza fuerte cada fraccion de pedidos NO servidos,
# de modo que una candidata que deja clientes sin atender casi nunca supera a una completa.
PENAL_COBERTURA = 10.0


def _normalizar(serie: pd.Series, mayor_mejor: bool) -> pd.Series:
    lo, hi = float(serie.min()), float(serie.max())
    if hi - lo < 1e-12:
        return pd.Series(1.0, index=serie.index)        # todos iguales => neutro
    norm = (serie - lo) / (hi - lo)
    return norm if mayor_mejor else (1.0 - norm)


def recomendar(evaluaciones: Sequence[dict], pesos: Optional[Dict[str, float]] = None) -> dict:
    """evaluaciones: [{'perfil':..., 'kpis': {...}}]. Devuelve recomendada + ranking +
    explicacion + tabla de comparacion."""
    pesos = pesos or PESOS_DEFECTO
    df = pd.DataFrame([{"perfil": e["perfil"], **e["kpis"]} for e in evaluaciones])
    if df.empty:
        return {"recomendada": None, "ranking": df, "explicacion": "Sin candidatas.",
                "comparacion": df}

    utilidad = pd.Series(0.0, index=df.index)
    for metrica, peso in pesos.items():
        if metrica not in df.columns:
            continue
        score = _normalizar(df[metrica].astype(float), mayor_mejor=(peso > 0))
        utilidad += abs(peso) * score
    if "cobertura" in df.columns:
        utilidad -= PENAL_COBERTURA * (1.0 - df["cobertura"].astype(float))
    df = df.assign(utilidad=utilidad.round(4)).sort_values(
        "utilidad", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))

    recomendada = df.iloc[0]
    explicacion = _explicar(df)
    return {"recomendada": recomendada["perfil"], "ranking": df,
            "explicacion": explicacion, "comparacion": df}


def _explicar(ranking: pd.DataFrame) -> str:
    """Texto de por que se recomienda la primera frente a la segunda."""
    if len(ranking) == 1:
        r = ranking.iloc[0]
        return (f"Se recomienda la ruta del perfil '{r['perfil']}' (unica candidata viable): "
                f"OTD {r.get('otd', 0) * 100:.0f}%, {int(r.get('pedidos_en_riesgo', 0))} "
                f"pedidos en riesgo, {r.get('distancia_km', 0):.0f} km.")
    a, b = ranking.iloc[0], ranking.iloc[1]
    motivos = []
    if a.get("otd", 0) > b.get("otd", 0) + 1e-6:
        motivos.append(f"mejor OTD ({a['otd'] * 100:.0f}% vs {b['otd'] * 100:.0f}%)")
    if a.get("pedidos_en_riesgo", 0) < b.get("pedidos_en_riesgo", 0):
        motivos.append(f"menos pedidos en riesgo ({int(a['pedidos_en_riesgo'])} vs "
                       f"{int(b['pedidos_en_riesgo'])})")
    if a.get("tardanza_p90_min", 0) < b.get("tardanza_p90_min", 0) - 1e-6:
        motivos.append(f"menor tardanza P90 ({a['tardanza_p90_min']:.0f} vs "
                       f"{b['tardanza_p90_min']:.0f} min)")
    if a.get("distancia_km", 1e9) < b.get("distancia_km", 1e9) - 1e-6:
        motivos.append(f"menor distancia ({a['distancia_km']:.0f} vs {b['distancia_km']:.0f} km)")
    razon = "; ".join(motivos) if motivos else "mejor balance global de los indicadores"
    costo = ""
    if a.get("distancia_km", 0) > b.get("distancia_km", 0) + 1e-6:
        costo = (f" Cuesta +{(a['distancia_km'] / max(b['distancia_km'], 1e-9) - 1) * 100:.0f}% "
                 f"de distancia frente a '{b['perfil']}', justificado por el mejor cumplimiento.")
    return (f"Se recomienda la ruta del perfil '{a['perfil']}' frente a '{b['perfil']}' por "
            f"{razon}.{costo}")


def evaluar_candidatas(candidatas: Sequence[dict], modelo, params, *,
                       incid_prob=None, incid_delay_min=None, ausencia_prob=None,
                       sigma_viaje: float = 0.25) -> List[dict]:
    """Orquesta sim. estocastica + riesgo para cada candidata y arma sus KPIs combinados
    (plan + Monte Carlo) listos para `recomendar`. Devuelve tambien IRI por candidata."""
    evaluaciones = []
    for cand in candidatas:
        res = cand["resultado"]
        if res.get("status") != "ok" or not res.get("rutas"):
            continue
        ctx = contexto_desde_resultado(res, modelo, incid_prob=incid_prob,
                                       incid_delay_min=incid_delay_min,
                                       ausencia_prob=ausencia_prob, sigma_viaje=sigma_viaje)
        muestras = montecarlo(ctx, iteraciones=int(params.iteraciones_montecarlo),
                              semilla_base=int(params.semilla_base))
        iri_df = calcular_iri(muestras)
        kpis_mc = kpis_montecarlo(muestras, iri_df)
        kpis = {**cand["kpis"], **kpis_mc}     # plan + simulacion (mc sobrescribe otd, etc.)
        evaluaciones.append({"perfil": cand["perfil"], "kpis": kpis,
                             "iri": iri_df, "resultado": res})
    return evaluaciones
