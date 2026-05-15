"""Calculo de indicadores y agregados de la jornada simulada."""
from typing import Dict
import numpy as np
import pandas as pd

from utils.constants import (
    ESTADO_A_TIEMPO, ESTADO_FUERA_VENTANA, ESTADO_FALLIDA,
    ESTADO_REPLANIFICADA, ESTADO_PENDIENTE, ESTADO_EN_RIESGO,
)
from utils.formatters import hhmm_to_minutes


def _safe_div(a, b):
    return (a / b * 100.0) if b else 0.0


def compute_kpis(entregas: pd.DataFrame, alertas: list = None) -> Dict[str, float]:
    """Calcula el set completo de indicadores a partir del dataframe de entregas."""
    if entregas is None or entregas.empty:
        return {}

    total = len(entregas)
    completadas = int((entregas["estado"] != ESTADO_PENDIENTE).sum())
    a_tiempo = int((entregas["estado"] == ESTADO_A_TIEMPO).sum())
    fuera = int((entregas["estado"] == ESTADO_FUERA_VENTANA).sum())
    fallidas = int((entregas["estado"] == ESTADO_FALLIDA).sum())
    pendientes = int((entregas["estado"] == ESTADO_PENDIENTE).sum())
    replanificadas = int((entregas["estado"] == ESTADO_REPLANIFICADA).sum())

    # Exito en primer intento: entregadas sin incidencia bloqueante
    exito_primer = int(((entregas["estado"] == ESTADO_A_TIEMPO) |
                        (entregas["estado"] == ESTADO_FUERA_VENTANA)).sum() - fuera)
    exito_primer = max(exito_primer, 0)

    retrasos = entregas["retraso_min"].dropna()
    retraso_prom = float(retrasos.mean()) if not retrasos.empty else 0.0
    retraso_max = float(retrasos.max()) if not retrasos.empty else 0.0
    desv = float(retrasos.std(ddof=0)) if not retrasos.empty else 0.0
    cv = (desv / retraso_prom * 100.0) if retraso_prom > 0 else 0.0

    tiempo_op = float(entregas["tiempo_op_min"].max()) if "tiempo_op_min" in entregas.columns and not entregas.empty else 0.0
    tiempo_prom_entrega = float(entregas["tiempo_total_min"].mean()) if "tiempo_total_min" in entregas.columns else 0.0
    tiempo_prom_parada = float(entregas["tiempo_servicio_real_min"].mean()) if "tiempo_servicio_real_min" in entregas.columns else 0.0

    n_alertas = len(alertas) if alertas else 0

    return {
        "otd": _safe_div(a_tiempo, completadas),
        "otif": _safe_div(a_tiempo, total),
        "exito_primer_intento": _safe_div(exito_primer, completadas),
        "entregas_a_tiempo": a_tiempo,
        "entregas_fuera_ventana": fuera,
        "entregas_fallidas": fallidas,
        "pedidos_pendientes": pendientes,
        "entregas_replanificadas": replanificadas,
        "tiempo_total_operacion_min": tiempo_op,
        "tiempo_promedio_entrega_min": tiempo_prom_entrega,
        "tiempo_promedio_parada_min": tiempo_prom_parada,
        "retraso_promedio_min": retraso_prom,
        "retraso_maximo_min": retraso_max,
        "desviacion_estandar_min": desv,
        "coef_variacion_pct": cv,
        "alertas_generadas": n_alertas,
        "total_pedidos": total,
        "entregas_completadas": completadas,
    }


def compute_otd_evolution(entregas: pd.DataFrame, step_min: int = 15) -> pd.DataFrame:
    """OTD acumulado en intervalos de step_min, expresado en HH:MM."""
    if entregas is None or entregas.empty:
        return pd.DataFrame(columns=["hora", "otd", "completadas", "a_tiempo"])
    df = entregas[entregas["estado"] != ESTADO_PENDIENTE].copy()
    if df.empty:
        return pd.DataFrame(columns=["hora", "otd", "completadas", "a_tiempo"])

    df["fin_servicio_min"] = df["fin_servicio_min"].astype(int)
    inicio = (df["fin_servicio_min"].min() // step_min) * step_min
    fin = ((df["fin_servicio_min"].max() // step_min) + 1) * step_min

    rows = []
    for t in range(inicio, fin + 1, step_min):
        sub = df[df["fin_servicio_min"] <= t]
        completadas = len(sub)
        a_tiempo = int((sub["estado"] == ESTADO_A_TIEMPO).sum())
        otd = _safe_div(a_tiempo, completadas)
        rows.append({
            "tiempo_min": t,
            "hora": f"{t // 60:02d}:{t % 60:02d}",
            "completadas": completadas,
            "a_tiempo": a_tiempo,
            "otd": otd,
        })
    return pd.DataFrame(rows)


def compute_vehicle_performance(entregas: pd.DataFrame,
                                vehiculos: pd.DataFrame) -> pd.DataFrame:
    """Resumen por vehiculo: pedidos asignados, OTD, uso capacidad, retraso."""
    if entregas is None or entregas.empty or vehiculos is None:
        return pd.DataFrame()

    agg = entregas.groupby("vehiculo_id").agg(
        pedidos_asignados=("pedido_id", "count"),
        a_tiempo=("estado", lambda s: int((s == ESTADO_A_TIEMPO).sum())),
        completadas=("estado", lambda s: int((s != ESTADO_PENDIENTE).sum())),
        fallidas=("estado", lambda s: int((s == ESTADO_FALLIDA).sum())),
        retraso_prom=("retraso_min", "mean"),
        peso_total=("peso_kg", "sum") if "peso_kg" in entregas.columns else ("retraso_min", "count"),
    ).reset_index()
    agg["otd"] = agg.apply(lambda r: _safe_div(r["a_tiempo"], r["completadas"]), axis=1)

    if "peso_kg" not in entregas.columns:
        agg["peso_total"] = 0

    cap = vehiculos[["vehiculo_id", "capacidad_unidades", "capacidad_kg"]]
    out = agg.merge(cap, on="vehiculo_id", how="left")
    out["uso_capacidad_pct"] = out.apply(
        lambda r: _safe_div(r["pedidos_asignados"], r["capacidad_unidades"]),
        axis=1,
    )
    out["uso_capacidad_kg_pct"] = out.apply(
        lambda r: _safe_div(r["peso_total"], r["capacidad_kg"]),
        axis=1,
    )
    out["retraso_prom"] = out["retraso_prom"].fillna(0).round(1)
    out["otd"] = out["otd"].round(1)
    out["uso_capacidad_pct"] = out["uso_capacidad_pct"].round(1)
    return out.sort_values("otd", ascending=False).reset_index(drop=True)


def compute_replanning_stats(decisiones: list) -> Dict[str, int]:
    """Contadores de sugeridas / aprobadas / rechazadas / pedidos recuperados."""
    if not decisiones:
        return {"sugeridas": 0, "aprobadas": 0, "rechazadas": 0, "pedidos_recuperados": 0}
    sugeridas = len(decisiones)
    aprobadas = sum(1 for d in decisiones if d.get("decision") == "aprobada")
    rechazadas = sum(1 for d in decisiones if d.get("decision") == "rechazada")
    recuperados = sum(int(d.get("pedidos_recuperados", 0)) for d in decisiones)
    return {
        "sugeridas": sugeridas,
        "aprobadas": aprobadas,
        "rechazadas": rechazadas,
        "pedidos_recuperados": recuperados,
    }


def aggregate_iterations(iteraciones: pd.DataFrame) -> pd.DataFrame:
    """Promedios y desviaciones por escenario sobre iteraciones Monte Carlo."""
    if iteraciones is None or iteraciones.empty:
        return pd.DataFrame()
    agg = iteraciones.groupby("escenario").agg(
        otd_prom=("otd", "mean"),
        otd_std=("otd", "std"),
        otif_prom=("otif", "mean"),
        retraso_prom=("retraso_promedio_min", "mean"),
        cv_prom=("coef_variacion_pct", "mean"),
        n=("otd", "count"),
    ).reset_index()
    agg["cv_otd_pct"] = (agg["otd_std"] / agg["otd_prom"] * 100.0).replace(
        [np.inf, -np.inf], 0
    ).fillna(0).round(2)
    for c in ["otd_prom", "otd_std", "otif_prom", "retraso_prom", "cv_prom"]:
        agg[c] = agg[c].fillna(0).round(2)
    return agg
