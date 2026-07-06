"""Evaluacion distribucionalmente robusta (DRO) de una ruta candidata.

Nucleo del cerebro CORTEX-LM rediseñado. En vez de puntuar una candidata por su desempeño
promedio bajo UNA distribucion, la estresa contra un CONJUNTO DE AMBIGUEDAD (nominal +
"Lima peor") y la puntua por su PEOR CASO ajustado por riesgo:

    score_robusto = max_{cfg in ambiguedad}  ( E[tardanza] + beta * CVaR_alpha(tardanza) )

Menor score = mejor (mas barato en riesgo y mas robusto a que la distribucion sintetica no
sea la real). Es Optimizacion Distribucionalmente Robusta en su version basada en
simulacion. La simulacion incluye variabilidad de viaje, incidencias y ausencia del cliente.

Trabaja con estimaciones de simulacion; recomienda soluciones robustas, no optimos.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np

from core.risk_engine import (calcular_iri, cvar, kpis_montecarlo, otd_por_escenario,
                              tardanza_por_escenario, var)
from core.simulator_simpy import contexto_desde_resultado, montecarlo
from core.uncertainty import (aplicar_config, conjunto_ambiguedad,
                              probabilidades_por_nodo)


def _cobertura(resultado: dict, modelo) -> float:
    servidos = sum(rc.n_paradas for rc in resultado.get("rutas", {}).values())
    n = len(modelo.pedido_ids) - 1
    return round(servidos / n, 4) if n else 0.0


def _distancia(resultado: dict) -> float:
    return round(sum(rc.distancia_km for rc in resultado.get("rutas", {}).values()), 2)


def evaluar_robusto(resultado: dict, modelo, pedidos: Sequence, incidencias: Sequence,
                    zonas: Sequence, params, *, ambiguedad=None, alpha: float = 0.9,
                    beta: float = 1.0, iteraciones: Optional[int] = None,
                    franjas_td: Optional[Sequence] = None) -> dict:
    """Evalua una candidata sobre el conjunto de ambiguedad. Devuelve KPIs nominal y de peor
    caso, el score robusto (peor caso ajustado por riesgo) y el IRI nominal."""
    ambiguedad = ambiguedad or conjunto_ambiguedad("medio")
    iters = int(iteraciones or min(int(params.iteraciones_montecarlo), 60))
    semilla = int(params.semilla_base)

    incid_prob, incid_delay, ausencia = probabilidades_por_nodo(pedidos, incidencias, zonas)
    distancia = _distancia(resultado)
    cobertura = _cobertura(resultado, modelo)
    # Tardanza del PLAN en un dia perfecto (sin incertidumbre): un plan que ya llega tarde con
    # todo en orden es intrinsecamente peor.
    tardanza_plan = round(sum(rc.tardanza_total_min
                              for rc in resultado.get("rutas", {}).values()), 2)
    # Pedidos NO servidos (descartados por el optimizador): abandonar un cliente es un fallo que
    # la seleccion debe penalizar, no premiar.
    n_clientes = max(0, len(getattr(modelo, "pedido_ids", [])) - 1)   # nodo 0 = HUB
    servidos_ct = sum(rc.n_paradas for rc in resultado.get("rutas", {}).values())
    n_no_servidos = max(0, n_clientes - servidos_ct)

    por_config = {}
    for cfg in ambiguedad:
        ip, au = aplicar_config(incid_prob, ausencia, cfg)
        ctx = contexto_desde_resultado(resultado, modelo, incid_prob=ip,
                                       incid_delay_min=incid_delay, ausencia_prob=au,
                                       sigma_viaje=cfg.sigma_viaje,
                                       sigma_sistemico=getattr(cfg, "sigma_sistemico", 0.0),
                                       franjas_td=franjas_td)
        ctx.tiempo_min = ctx.tiempo_min * cfg.mult_congestion   # estresa los tiempos
        muestras = montecarlo(ctx, iteraciones=iters, semilla_base=semilla)
        iri_df = calcular_iri(muestras)
        kmc = kpis_montecarlo(muestras, iri_df)
        tard = tardanza_por_escenario(muestras)
        score = float(np.mean(tard) + beta * cvar(tard, alpha)) if tard.size else 0.0
        # Variabilidad del nivel de servicio: desviacion estandar del OTD ENTRE escenarios
        # Monte Carlo (menor = operacion mas consistente; es el objetivo del DSS).
        otd_esc = otd_por_escenario(muestras)
        variab_otd = float(np.std(otd_esc)) if otd_esc is not None and len(otd_esc) else 0.0
        por_config[cfg.nombre] = {
            "otd": kmc.get("otd", 0.0),
            "otif": kmc.get("otif", 0.0),
            "otd_peor_dia": round(float(otd_esc.min()), 4) if len(otd_esc) else 0.0,
            "variab_otd": round(variab_otd, 4),
            "tardanza_prom_min": kmc.get("tardanza_prom_min", 0.0),
            "tardanza_std_min": kmc.get("tardanza_std_min", 0.0),
            "cvar_tardanza_min": round(cvar(tard, alpha), 2),
            "var_tardanza_min": round(var(tard, alpha), 2),
            "pedidos_en_riesgo": kmc.get("pedidos_en_riesgo", 0),
            "score": round(score, 3),
            "iri": iri_df,
        }

    nominal = por_config[ambiguedad[0].nombre]
    peor_nombre = max(por_config, key=lambda k: por_config[k]["score"])
    peor = por_config[peor_nombre]

    return {
        "perfil": resultado.get("perfil"),
        "cobertura": cobertura,
        "distancia_km": distancia,
        "tardanza_plan_min": tardanza_plan,      # tardanza en dia perfecto (nominal del plan)
        "n_no_servidos": n_no_servidos,          # clientes abandonados (penalizados en la seleccion)
        "score_robusto": peor["score"],          # DRO: peor caso ajustado por riesgo (menor=mejor)
        "config_peor_caso": peor_nombre,
        "otd_nominal": nominal["otd"],
        "otif_nominal": nominal["otif"],
        "otd_peor": peor["otd"],
        "variabilidad_otd": nominal["variab_otd"],
        "cvar_nominal_min": nominal["cvar_tardanza_min"],
        "cvar_peor_min": peor["cvar_tardanza_min"],
        "pedidos_en_riesgo_nominal": nominal["pedidos_en_riesgo"],
        "pedidos_en_riesgo_peor": peor["pedidos_en_riesgo"],
        "iri": nominal["iri"],
        "por_config": {k: {kk: vv for kk, vv in v.items() if kk != "iri"}
                       for k, v in por_config.items()},
        "resultado": resultado,
        # 'kpis' plano para compatibilidad con los reportes/vistas existentes.
        "kpis": {
            "cobertura": cobertura, "otd": nominal["otd"], "otif": nominal["otif"],
            "otd_peor": peor["otd"], "variabilidad": nominal["variab_otd"],
            "tardanza_prom_min": nominal["tardanza_prom_min"],
            "cvar_nominal_min": nominal["cvar_tardanza_min"],
            "cvar_peor_min": peor["cvar_tardanza_min"],
            "pedidos_en_riesgo": peor["pedidos_en_riesgo"],
            "score_robusto": peor["score"], "distancia_km": distancia,
        },
    }


def recomendar_robusto(evaluaciones: Sequence[dict], *, penal_no_servido: float = 90.0) -> dict:
    """Selecciona la MEJOR candidata entre TODAS (OR-Tools + ALNS) con un objetivo UNIFICADO,
    consciente de riesgo Y de cobertura:

        score_total = score_robusto  +  penal_no_servido * (pedidos NO servidos)

    Antes la seleccion filtraba por COBERTURA ABSOLUTA (y elegia el plan de cobertura total de menor
    riesgo), lo que la forzaba a planes ALNS de cobertura total pero FRAGILES. Ahora OR-Tools y ALNS
    compiten en la MISMA cancha:
      - `score_robusto` = peor caso ajustado por riesgo (E[tardanza]+β·CVaR sobre el peor config).
        Ya penaliza los planes que llegan tarde (incluido "tarde en dia perfecto") => la robustez se
        extrae donde de verdad reduce el riesgo, no fabricando tardanza.
      - `penal_no_servido` cuenta cada cliente ABANDONADO como un fallo (no una ventaja): sin esto la
        seleccion premiaba descartar los pedidos dificiles.
    Si servir todo (ALNS) reduce el riesgo total, gana; si un plan mas limpio que descarta 1-2
    dificiles (OR-Tools) es menos arriesgado en conjunto, gana ese. Resultado: robusto dominante-o-
    igual al determinista, y mejor bajo estres cuando el plan esta apretado (que es donde la
    robustez tiene trabajo)."""
    if not evaluaciones:
        return {"recomendada": None, "ranking": [], "explicacion": "Sin candidatas viables."}

    def score_total(e):
        return e["score_robusto"] + penal_no_servido * e.get("n_no_servidos", 0)

    ranking = sorted(evaluaciones, key=score_total)
    mejor = ranking[0]
    exp = _explicar_robusto(mejor, ranking)
    return {"recomendada": mejor["perfil"], "ranking": ranking, "explicacion": exp,
            "elegida": mejor}


def _explicar_robusto(mejor: dict, ranking: List[dict]) -> str:
    base = (f"Se recomienda el perfil '{mejor['perfil']}' por ser el mas ROBUSTO: menor "
            f"riesgo en el peor escenario de incertidumbre ('{mejor['config_peor_caso']}'), "
            f"con OTD {mejor['otd_peor'] * 100:.0f}% incluso ahi y CVaR de tardanza "
            f"{mejor['cvar_peor_min']:.0f} min.")
    if len(ranking) > 1:
        seg = ranking[1]
        base += (f" Frente a '{seg['perfil']}', su peor caso es mejor "
                 f"({mejor['score_robusto']:.0f} vs {seg['score_robusto']:.0f} en score de "
                 f"riesgo) a un costo de {mejor['distancia_km']:.0f} km.")
    return base
