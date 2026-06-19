"""Metricas del benchmark principal ALM RRC (comparables con literatura).

Todas las metricas se calculan con la MATRIZ REAL de tiempos del ALM RRC, de modo
que la ruta real del conductor y la propuesta por el DSS se evaluan en la misma escala.

Indicadores del benchmark PRINCIPAL (alineados con la literatura del ALM RRC):
    - SDstop          : Sequence Deviation a nivel de parada (formula oficial Cook et al.).
    - SDzone          : Sequence Deviation a nivel de zona (orden de zonas visitadas).
    - ERPratio        : penalizacion promedio por desviacion (Edit distance w/ Real Penalty
                        sobre la matriz de tiempos, normalizada por numero de paradas).
    - score_aprox     : SDstop * ERPratio. Proxy del score oficial de Amazon.
                        Se nombra explicitamente "aproximado": replica la estructura del
                        score (SD x ERP) con una penalizacion de gap documentada, pero NO
                        es el binario oficial de Amazon (que usa una normalizacion propia).
    - tiempo_real_min / tiempo_propuesto_min / brecha_pct
    - tiempo_computo_seg / n_paradas
    - route_score (original del dataset): SOLO como filtro/segmentacion, no es salida del DSS.

Definiciones (transparentes y verificables):

SDstop(A, B):
    Con A = secuencia real (incluye depot en posicion 0) y B = secuencia propuesta
    (mismo conjunto, depot en posicion 0):
        comp_i = posicion en B de la i-esima parada de A
        SD = (2 / (n(n-1))) * ( sum_i |comp_{i+1} - comp_i| - (n-1) )
    SD = 0 si B respeta el mismo orden que A. n = numero de elementos (incl. depot).

ERP (Edit distance with Real Penalty):
    Distancia de edicion entre A y B donde el costo de emparejar dos paradas es el
    tiempo de viaje real entre ellas y el costo de "gap" (insertar/eliminar) es una
    penalizacion g = mediana de los tiempos de viaje de la ruta (escala propia de la
    ruta, documentada). ERPratio = ERP_total / n_paradas (minutos por parada).
"""
from typing import Dict, List, Optional
import statistics

from benchmark.adapter import CasoBenchmark


# ---------------------------------------------------------------------------
# Tiempos
# ---------------------------------------------------------------------------

def tiempo_total(secuencia: List[str], caso: CasoBenchmark,
                 incluir_servicio: bool = True) -> float:
    """Tiempo total (min) de recorrer una secuencia desde el depot, sin retorno."""
    if not secuencia:
        return 0.0
    t = 0.0
    actual = caso.depot_stop_id
    for stop in secuencia:
        t += caso.tiempo(actual, stop)
        if incluir_servicio:
            t += caso.servicio_min.get(stop, 0.0)
        actual = stop
    return round(t, 2)


# ---------------------------------------------------------------------------
# Sequence Deviation (formula oficial Cook et al. 2021)
# ---------------------------------------------------------------------------

def _seq_dev(actual: List[str], sub: List[str]) -> Optional[float]:
    """Sequence Deviation oficial entre dos ordenes del mismo conjunto.

    actual y sub deben contener el mismo conjunto de elementos (incl. depot).
    Devuelve None si no es calculable.
    """
    if not actual or not sub:
        return None
    set_sub = set(sub)
    # Solo elementos presentes en ambos, en el orden de 'actual'.
    actual_f = [x for x in actual if x in set_sub]
    n = len(actual_f)
    if n < 2:
        return None
    pos_sub = {x: i for i, x in enumerate(sub)}
    comp = [pos_sub[x] for x in actual_f]
    comp_sum = sum(abs(comp[i + 1] - comp[i]) for i in range(n - 1))
    sd = (2.0 / (n * (n - 1))) * (comp_sum - (n - 1))
    return round(sd, 4)


def sd_stop(caso: CasoBenchmark, propuesta: List[str]) -> Optional[float]:
    """SDstop: sequence deviation a nivel de parada (depot anclado en posicion 0)."""
    actual = [caso.depot_stop_id] + list(caso.secuencia_real)
    sub = [caso.depot_stop_id] + list(propuesta)
    return _seq_dev(actual, sub)


def _orden_zonas(caso: CasoBenchmark, secuencia: List[str]) -> List[str]:
    """Orden de zonas por primera visita a lo largo de la secuencia."""
    visto = set()
    orden = []
    for stop in secuencia:
        z = caso.zonas.get(stop, "SIN_ZONA")
        if z not in visto:
            visto.add(z)
            orden.append(z)
    return orden


def sd_zone(caso: CasoBenchmark, propuesta: List[str]) -> Optional[float]:
    """SDzone: sequence deviation a nivel de zona (orden de zonas visitadas)."""
    z_real = _orden_zonas(caso, caso.secuencia_real)
    z_prop = _orden_zonas(caso, propuesta)
    return _seq_dev(z_real, z_prop)


# ---------------------------------------------------------------------------
# ERP (Edit distance with Real Penalty) sobre la matriz de tiempos
# ---------------------------------------------------------------------------

def _gap_penalty(caso: CasoBenchmark) -> float:
    """Penalizacion de gap g: mediana de los tiempos de viaje de la ruta (min)."""
    vals = [v for v in caso.matriz_min.values() if v > 0]
    if not vals:
        return 1.0
    try:
        return float(statistics.median(vals))
    except statistics.StatisticsError:
        return float(sum(vals) / len(vals))


def _erp_total(caso: CasoBenchmark, propuesta: List[str]) -> Optional[float]:
    """ERP entre la secuencia real y la propuesta (DP iterativo, O(n^2)).

    Costo de emparejar a<->b = tiempo de viaje real(a,b); costo de gap = g.
    """
    a = [caso.depot_stop_id] + list(caso.secuencia_real)
    b = [caso.depot_stop_id] + list(propuesta)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    g = _gap_penalty(caso)

    # dp[i][j] = ERP entre a[:i] y b[:j]
    dp = [[0.0] * (nb + 1) for _ in range(na + 1)]
    for i in range(1, na + 1):
        dp[i][0] = dp[i - 1][0] + g
    for j in range(1, nb + 1):
        dp[0][j] = dp[0][j - 1] + g
    for i in range(1, na + 1):
        ai = a[i - 1]
        for j in range(1, nb + 1):
            bj = b[j - 1]
            match = dp[i - 1][j - 1] + caso.tiempo(ai, bj)
            gap_a = dp[i - 1][j] + g
            gap_b = dp[i][j - 1] + g
            dp[i][j] = min(match, gap_a, gap_b)
    return round(dp[na][nb], 4)


def erp_ratio(caso: CasoBenchmark, propuesta: List[str]) -> Optional[float]:
    """ERPratio = ERP_total / n_paradas (penalizacion promedio por desviacion, min)."""
    total = _erp_total(caso, propuesta)
    if total is None:
        return None
    n = max(1, caso.n_paradas)
    return round(total / n, 4)


# ---------------------------------------------------------------------------
# Score aproximado (estructura del score oficial: SD x ERP)
# ---------------------------------------------------------------------------

def score_aproximado(sd: Optional[float], erp_r: Optional[float]) -> Optional[float]:
    """score_aprox = SDstop * ERPratio. Proxy documentado del score ALM RRC."""
    if sd is None or erp_r is None:
        return None
    return round(sd * erp_r, 4)


# ---------------------------------------------------------------------------
# Fila consolidada y resumen
# ---------------------------------------------------------------------------

def evaluar_ruta(caso: CasoBenchmark, opt_result: Dict) -> Dict:
    """Construye la fila consolidada del benchmark PRINCIPAL para una ruta."""
    propuesta = opt_result.get("secuencia_propuesta", [])
    real = caso.secuencia_real

    if not real or len(real) < 2:
        return {
            "route_id": caso.route_id,
            "station_code": caso.meta.get("station_code", ""),
            "route_score": caso.meta.get("route_score", ""),
            "n_paradas": caso.n_paradas,
            "sd_stop": None, "sd_zone": None, "erp_ratio_min": None,
            "score_aprox": None,
            "tiempo_real_min": None, "tiempo_propuesto_min": None, "brecha_pct": None,
            "motor_usado": opt_result.get("motor_usado", ""),
            "tiempo_computo_seg": opt_result.get("tiempo_computo_seg", None),
            "status": "ruta_sin_secuencia_real",
        }

    t_real = tiempo_total(real, caso)
    t_prop = tiempo_total(propuesta, caso)
    brecha = round((t_prop - t_real) / t_real * 100, 2) if t_real > 0 else None

    sd = sd_stop(caso, propuesta)
    sdz = sd_zone(caso, propuesta)
    erp_r = erp_ratio(caso, propuesta)

    return {
        "route_id": caso.route_id,
        "station_code": caso.meta.get("station_code", ""),
        "route_score": caso.meta.get("route_score", ""),   # filtro/segmentacion
        "n_paradas": caso.n_paradas,
        "sd_stop": sd,
        "sd_zone": sdz,
        "erp_ratio_min": erp_r,
        "score_aprox": score_aproximado(sd, erp_r),
        "tiempo_real_min": t_real,
        "tiempo_propuesto_min": t_prop,
        "brecha_pct": brecha,
        "motor_usado": opt_result.get("motor_usado", ""),
        "tiempo_computo_seg": opt_result.get("tiempo_computo_seg", None),
        "status": opt_result.get("status", "ok"),
    }


# Columnas canonicas del benchmark principal (orden de salida).
COLUMNAS_RESULTADO = [
    "route_id", "station_code", "route_score", "n_paradas",
    "sd_stop", "sd_zone", "erp_ratio_min", "score_aprox",
    "tiempo_real_min", "tiempo_propuesto_min", "brecha_pct",
    "motor_usado", "tiempo_computo_seg", "status",
]


def resumen_global(filas: List[Dict]) -> Dict:
    """Agrega los resultados de varias rutas (solo filas exitosas)."""
    ok = [f for f in filas if f.get("status") == "ok" and f.get("tiempo_real_min", 0)]
    if not ok:
        return {}

    def _prom(clave):
        vals = [f[clave] for f in ok if f.get(clave) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    return {
        "rutas_evaluadas": len(ok),
        "sd_stop_promedio": _prom("sd_stop"),
        "sd_zone_promedio": _prom("sd_zone"),
        "erp_ratio_promedio_min": _prom("erp_ratio_min"),
        "score_aprox_promedio": _prom("score_aprox"),
        "brecha_pct_promedio": round(_prom("brecha_pct"), 2) if _prom("brecha_pct") is not None else None,
        "tiempo_real_min_promedio": round(_prom("tiempo_real_min"), 2) if _prom("tiempo_real_min") is not None else None,
        "tiempo_propuesto_min_promedio": round(_prom("tiempo_propuesto_min"), 2) if _prom("tiempo_propuesto_min") is not None else None,
        "tiempo_computo_seg_promedio": _prom("tiempo_computo_seg"),
        "paradas_promedio": round(_prom("n_paradas"), 1) if _prom("n_paradas") is not None else None,
    }
