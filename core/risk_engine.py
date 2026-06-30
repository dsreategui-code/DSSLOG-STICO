"""Motor de riesgo del DSS CORTEX-LM: Indice de Riesgo de Incumplimiento (IRI) y KPIs.

A partir de las muestras Monte Carlo (core.simulator_simpy), estima por pedido la
probabilidad de incumplir su ventana, la clasifica, y agrega los KPIs logisticos de la
solucion. Trabaja con probabilidades empiricas; no garantiza resultados.

IRI_i = P(ETA_i > ventana_fin_i)  (proporcion de realizaciones que incumplen).
Clasificacion:  Bajo 0.00-0.30 | Moderado 0.31-0.60 | Alto 0.61-0.80 | Critico 0.81-1.00
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

UMBRAL_RIESGO = 0.60   # IRI por encima de esto => pedido "en riesgo" (Alto/Critico)


def clasificar_iri(iri: float) -> str:
    if iri <= 0.30:
        return "Bajo"
    if iri <= 0.60:
        return "Moderado"
    if iri <= 0.80:
        return "Alto"
    return "Critico"


def calcular_iri(muestras: pd.DataFrame) -> pd.DataFrame:
    """DataFrame por pedido con IRI, clasificacion y percentiles de ETA."""
    if muestras is None or muestras.empty:
        return pd.DataFrame(columns=["pedido_id", "vehiculo_id", "ventana_fin",
                                     "eta_p50", "eta_p90", "iri", "clasificacion"])
    filas = []
    for pid, d in muestras.groupby("pedido_id"):
        iri = float((d["eta_min"] > d["ventana_fin"]).mean())
        filas.append({
            "pedido_id": pid,
            "vehiculo_id": d["vehiculo_id"].iloc[0],
            "ventana_fin": float(d["ventana_fin"].iloc[0]),
            "eta_p50": round(float(np.percentile(d["eta_min"], 50)), 1),
            "eta_p90": round(float(np.percentile(d["eta_min"], 90)), 1),
            "iri": round(iri, 4),
            "clasificacion": clasificar_iri(iri),
        })
    df = pd.DataFrame(filas).sort_values("iri", ascending=False).reset_index(drop=True)
    return df


def kpis_montecarlo(muestras: pd.DataFrame, iri_df: Optional[pd.DataFrame] = None) -> dict:
    """KPIs logisticos agregados sobre las muestras Monte Carlo."""
    if muestras is None or muestras.empty:
        return {}
    a_tiempo = muestras["a_tiempo"].astype(bool)
    primer = muestras["primer_intento_ok"].astype(bool)
    tard = muestras["tardanza_min"].astype(float)
    if iri_df is None:
        iri_df = calcular_iri(muestras)
    return {
        "otd": round(float(a_tiempo.mean()), 4),
        "otif": round(float((a_tiempo & primer).mean()), 4),
        "pct_dentro_ventana": round(float(a_tiempo.mean()), 4),
        "first_attempt_success": round(float(primer.mean()), 4),
        "tardanza_prom_min": round(float(tard.mean()), 2),
        "tardanza_std_min": round(float(tard.std(ddof=0)), 2),
        "tardanza_p75_min": round(float(np.percentile(tard, 75)), 2),
        "tardanza_p90_min": round(float(np.percentile(tard, 90)), 2),
        "pedidos_en_riesgo": int((iri_df["iri"] > UMBRAL_RIESGO).sum()) if not iri_df.empty else 0,
        "pedidos_criticos": int((iri_df["clasificacion"] == "Critico").sum()) if not iri_df.empty else 0,
        "n_pedidos": int(muestras["pedido_id"].nunique()),
        "iteraciones": int(muestras["iteracion"].nunique()) if "iteracion" in muestras else 1,
    }
