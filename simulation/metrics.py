"""Calculo de indicadores y agregados de la jornada simulada.

Reglas:
- No dividir por cero (helper `_safe_div`).
- No mezclar minutos con horas (todos los tiempos se exponen en minutos).
- CV = desv / promedio (luego x100). Si el promedio es muy bajo (<1 min),
  el indicador no es aplicable: se devuelve None para que la UI muestre
  "No aplicable" en lugar de un porcentaje absurdo.
"""
from typing import Dict, Optional
import numpy as np
import pandas as pd

from utils.constants import (
    ESTADO_A_TIEMPO, ESTADO_FUERA_VENTANA, ESTADO_FALLIDA,
    ESTADO_REPLANIFICADA, ESTADO_PENDIENTE, ESTADO_EN_RIESGO,
)


# Umbral minimo del promedio para que el CV sea informativo.
# Por debajo, el cociente desv/promedio se vuelve numericamente inestable.
CV_MEAN_MIN_MIN = 1.0

# Incidencias que implican un fallo de entrega / reintento (el cliente no estaba
# o no se pudo acceder al punto). Solo estas penalizan el "exito en primer intento".
# Las demas incidencias (trafico, estacionamiento, demora de instalacion/pago) son
# demoras puras: la entrega SI se concreta al primer intento, solo llega mas tarde.
INCIDENCIAS_REINTENTO = {
    "cliente_no_encontrado", "cliente_ausente",
    "direccion_incompleta",
    "zona_dificil_acceso", "acceso_restringido", "restriccion_acceso",
    "rechazo_entrega",
}


def _safe_div(a, b) -> float:
    """Division segura en porcentaje. Devuelve 0 si el denominador es 0."""
    return (a / b * 100.0) if b else 0.0


def _safe_cv(desv: float, promedio: float) -> Optional[float]:
    """CV = std / mean * 100. Devuelve None si la media es muy baja o cero."""
    if promedio is None or promedio < CV_MEAN_MIN_MIN:
        return None
    return float(desv) / float(promedio) * 100.0


def compute_kpis(entregas: pd.DataFrame, alertas: list = None) -> Dict[str, float]:
    """Calcula el set completo de indicadores a partir del dataframe de entregas.

    Si el dataframe esta vacio devuelve un dict vacio. Todas las divisiones son
    defensivas. El CV puede devolverse como None cuando no es aplicable.
    """
    if entregas is None or entregas.empty:
        return {}

    total = int(len(entregas))
    completadas = int((entregas["estado"] != ESTADO_PENDIENTE).sum())
    a_tiempo = int((entregas["estado"] == ESTADO_A_TIEMPO).sum())
    fuera = int((entregas["estado"] == ESTADO_FUERA_VENTANA).sum())
    fallidas = int((entregas["estado"] == ESTADO_FALLIDA).sum())
    pendientes = int((entregas["estado"] == ESTADO_PENDIENTE).sum())
    replanificadas = int((entregas["estado"] == ESTADO_REPLANIFICADA).sum())

    # Exito en primer intento: entregas completadas que NO sufrieron una
    # incidencia de reintento (cliente ausente, direccion incompleta, acceso
    # restringido, rechazo). Las demoras puras (trafico, estacionamiento, etc.)
    # NO cuentan como fallo: la entrega se concreto al primer intento.
    completadas_estados = [ESTADO_A_TIEMPO, ESTADO_FUERA_VENTANA]
    completadas_mask = entregas["estado"].isin(completadas_estados)
    if "incidencia" in entregas.columns:
        reintento = completadas_mask & \
            entregas["incidencia"].fillna("").isin(INCIDENCIAS_REINTENTO)
        exito_primer = int(completadas_mask.sum() - reintento.sum())
    else:
        exito_primer = int(completadas_mask.sum())

    # Retrasos: solo de entregas completadas (no pendientes ni fallidas).
    retrasos_serie = entregas.loc[
        entregas["estado"].isin([ESTADO_A_TIEMPO, ESTADO_FUERA_VENTANA]),
        "retraso_min",
    ].dropna()
    retraso_prom = float(retrasos_serie.mean()) if not retrasos_serie.empty else 0.0
    retraso_max = float(retrasos_serie.max()) if not retrasos_serie.empty else 0.0
    desv = float(retrasos_serie.std(ddof=0)) if len(retrasos_serie) > 1 else 0.0

    # CV: se calcula sobre la submuestra de entregas con retraso real (> 0).
    # Mezclar ceros (a tiempo) con tardanzas grandes produce CV ficticios de
    # 300-500% que no son informativos. Si hay menos de 3 entregas tardias,
    # el indicador no es aplicable.
    retrasos_pos = retrasos_serie[retrasos_serie > 0.01]
    if len(retrasos_pos) >= 3:
        mean_pos = float(retrasos_pos.mean())
        std_pos = float(retrasos_pos.std(ddof=0))
        cv = _safe_cv(std_pos, mean_pos)
    else:
        cv = None

    # Tiempo total de operacion: hora del ultimo fin de servicio REAL.
    # Se mide solo sobre entregas completadas; los pendientes tienen tiempo_op
    # fijo en jornada_fin y no deben inflar el indicador.
    tiempo_op = 0.0
    if "tiempo_op_min" in entregas.columns:
        op_completadas = entregas.loc[
            entregas["estado"] != ESTADO_PENDIENTE, "tiempo_op_min"
        ]
        serie_op = pd.to_numeric(op_completadas, errors="coerce").dropna()
        if not serie_op.empty:
            tiempo_op = float(serie_op.max())

    # Tiempo promedio por entrega: tiempo ACTIVO dedicado (viaje + servicio +
    # incidencia). Excluye la espera ociosa por ventana, que es tiempo muerto del
    # vehiculo y distorsiona la interpretacion del esfuerzo por entrega.
    tiempo_prom_entrega = 0.0
    completadas_df = entregas[entregas["estado"] != ESTADO_PENDIENTE]
    if not completadas_df.empty:
        if {"tiempo_viaje_min", "tiempo_servicio_real_min"}.issubset(completadas_df.columns):
            activo = (
                pd.to_numeric(completadas_df["tiempo_viaje_min"], errors="coerce").fillna(0)
                + pd.to_numeric(completadas_df["tiempo_servicio_real_min"], errors="coerce").fillna(0)
            )
            if "tiempo_incidencia_min" in completadas_df.columns:
                activo = activo + pd.to_numeric(
                    completadas_df["tiempo_incidencia_min"], errors="coerce"
                ).fillna(0)
            tiempo_prom_entrega = float(activo.mean())
        elif "tiempo_total_min" in completadas_df.columns:
            tiempo_prom_entrega = float(completadas_df["tiempo_total_min"].mean())

    # Tiempo promedio en parada (solo servicio).
    tiempo_prom_parada = 0.0
    if "tiempo_servicio_real_min" in entregas.columns:
        servicio_df = entregas[entregas["tiempo_servicio_real_min"].fillna(0) > 0]
        if not servicio_df.empty:
            tiempo_prom_parada = float(servicio_df["tiempo_servicio_real_min"].mean())

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
        "coef_variacion_pct": cv,  # puede ser None -> "No aplicable" en UI
        "alertas_generadas": n_alertas,
        "total_pedidos": total,
        "entregas_completadas": completadas,
    }


def compute_otd_evolution(entregas: pd.DataFrame, step_min: int = 15) -> pd.DataFrame:
    """OTD acumulado en intervalos de step_min, expresado en HH:MM."""
    cols = ["tiempo_min", "hora", "otd", "completadas", "a_tiempo"]
    if entregas is None or entregas.empty:
        return pd.DataFrame(columns=cols)
    df = entregas[entregas["estado"] != ESTADO_PENDIENTE].copy()
    if df.empty or "fin_servicio_min" not in df.columns:
        return pd.DataFrame(columns=cols)

    df["fin_servicio_min"] = pd.to_numeric(df["fin_servicio_min"], errors="coerce")
    df = df.dropna(subset=["fin_servicio_min"])
    if df.empty:
        return pd.DataFrame(columns=cols)
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
    """Resumen por vehiculo: pedidos asignados, OTD, uso capacidad, retraso,
    tiempo de servicio total y promedio."""
    if entregas is None or entregas.empty or vehiculos is None:
        return pd.DataFrame()

    base_cols = {
        "pedidos_asignados": ("pedido_id", "count"),
        "a_tiempo":          ("estado", lambda s: int((s == ESTADO_A_TIEMPO).sum())),
        "completadas":       ("estado", lambda s: int((s != ESTADO_PENDIENTE).sum())),
        "fallidas":          ("estado", lambda s: int((s == ESTADO_FALLIDA).sum())),
        "retraso_prom":      ("retraso_min", "mean"),
    }
    if "peso_kg" in entregas.columns:
        base_cols["peso_total"] = ("peso_kg", "sum")
    if "tiempo_servicio_real_min" in entregas.columns:
        base_cols["tiempo_servicio_total"] = ("tiempo_servicio_real_min", "sum")
        base_cols["tiempo_servicio_prom"] = ("tiempo_servicio_real_min", "mean")

    agg = entregas.groupby("vehiculo_id").agg(**base_cols).reset_index()
    agg["otd"] = agg.apply(lambda r: _safe_div(r["a_tiempo"], r["completadas"]), axis=1)

    if "peso_total" not in agg.columns:
        agg["peso_total"] = 0
    if "tiempo_servicio_total" not in agg.columns:
        agg["tiempo_servicio_total"] = 0.0
        agg["tiempo_servicio_prom"] = 0.0

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
    out["uso_capacidad_kg_pct"] = out["uso_capacidad_kg_pct"].round(1)
    out["tiempo_servicio_total"] = out["tiempo_servicio_total"].fillna(0).round(1)
    out["tiempo_servicio_prom"] = out["tiempo_servicio_prom"].fillna(0).round(1)
    return out.sort_values("otd", ascending=False).reset_index(drop=True)


def compute_service_time_metrics(entregas: pd.DataFrame) -> Dict:
    """Indicadores de tiempo de servicio (parada en cliente).

    Devuelve:
        servicio_total_min, servicio_promedio_min,
        servicio_pct_jornada (porcentaje del tiempo total explicado por servicio),
        por_vehiculo: DataFrame [vehiculo_id, servicio_total, servicio_prom, n],
        por_tipo:     DataFrame [tipo_servicio, servicio_total, servicio_prom, n, otd_pct].
    """
    vacio = {
        "servicio_total_min": 0.0,
        "servicio_promedio_min": 0.0,
        "servicio_pct_jornada": 0.0,
        "por_vehiculo": pd.DataFrame(),
        "por_tipo": pd.DataFrame(),
    }
    if entregas is None or entregas.empty or \
            "tiempo_servicio_real_min" not in entregas.columns:
        return vacio

    df = entregas[entregas["tiempo_servicio_real_min"].fillna(0) > 0].copy()
    if df.empty:
        return vacio

    total = float(df["tiempo_servicio_real_min"].sum())
    promedio = float(df["tiempo_servicio_real_min"].mean())

    # Porcentaje del tiempo de operacion explicado por servicio.
    # Sumamos tiempo de operacion por vehiculo (no por entrega para no duplicar).
    pct_jornada = 0.0
    if "tiempo_op_min" in entregas.columns:
        tiempo_op_por_veh = entregas.groupby("vehiculo_id")["tiempo_op_min"].max()
        servicio_por_veh = df.groupby("vehiculo_id")["tiempo_servicio_real_min"].sum()
        total_op = float(tiempo_op_por_veh.fillna(0).sum())
        total_serv = float(servicio_por_veh.fillna(0).sum())
        pct_jornada = _safe_div(total_serv, total_op)

    por_vehiculo = (
        df.groupby("vehiculo_id")
          .agg(
              servicio_total=("tiempo_servicio_real_min", "sum"),
              servicio_prom=("tiempo_servicio_real_min", "mean"),
              n=("pedido_id", "count"),
          )
          .reset_index()
          .round({"servicio_total": 1, "servicio_prom": 1})
          .sort_values("servicio_total", ascending=False)
    )

    # Por tipo de servicio, agregando OTD
    if "tipo_servicio" in df.columns:
        agg_tipo = df.groupby("tipo_servicio").agg(
            servicio_total=("tiempo_servicio_real_min", "sum"),
            servicio_prom=("tiempo_servicio_real_min", "mean"),
            n=("pedido_id", "count"),
            a_tiempo=("estado", lambda s: int((s == ESTADO_A_TIEMPO).sum())),
            completadas=("estado", lambda s: int((s != ESTADO_PENDIENTE).sum())),
        ).reset_index()
        agg_tipo["otd_pct"] = agg_tipo.apply(
            lambda r: _safe_div(r["a_tiempo"], r["completadas"]), axis=1
        ).round(1)
        agg_tipo = agg_tipo.drop(columns=["a_tiempo", "completadas"])
        agg_tipo = agg_tipo.round({"servicio_total": 1, "servicio_prom": 1})
        agg_tipo = agg_tipo.sort_values("servicio_total", ascending=False).reset_index(drop=True)
    else:
        agg_tipo = pd.DataFrame()

    return {
        "servicio_total_min": round(total, 1),
        "servicio_promedio_min": round(promedio, 1),
        "servicio_pct_jornada": round(pct_jornada, 1),
        "por_vehiculo": por_vehiculo,
        "por_tipo": agg_tipo,
    }


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
    """Promedios y desviaciones por escenario sobre iteraciones Monte Carlo.

    El CV se calcula como std/mean*100 sobre el OTD; si la media de OTD es
    insuficiente o cero, queda como 0 (suficiente para comparativas).
    """
    if iteraciones is None or iteraciones.empty:
        return pd.DataFrame()

    # Convertir CVs None a NaN para que mean los ignore en lugar de explotar.
    df = iteraciones.copy()
    if "coef_variacion_pct" in df.columns:
        df["coef_variacion_pct"] = pd.to_numeric(
            df["coef_variacion_pct"], errors="coerce"
        )

    agg = df.groupby("escenario").agg(
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
