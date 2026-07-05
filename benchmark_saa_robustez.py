"""Benchmark de ROBUSTEZ POR DISENO: ALNS deterministico vs ALNS robusto (SAA + objetivo CVaR).

Corre, sobre instancias reales del dataset (a distintos tamanos), el mismo ALNS con dos
objetivos — el deterministico (viaje + tardanza nominal, con buffer SLA fijo) y el robusto
(viaje + E[tardanza] + beta*CVaR_alpha(tardanza) via Sample Average Approximation con numeros
aleatorios comunes) — partiendo del MISMO warm de OR-Tools. Mide la tardanza FUERA DE MUESTRA
sobre un conjunto de validacion de escenarios FRESCOS (semilla distinta, mas numerosos) para
evitar el sobreajuste a los escenarios de entrenamiento.

Es la evidencia central de la tesis: optimizar el objetivo robusto reduce la COLA de tardanza
(CVaR) y su variabilidad a distancia similar. Usa el catalogo de incidencias unificado
(core.uncertainty), el factor sistemico del dia y el trafico dependiente de la hora.

Uso:  .venv\\Scripts\\python.exe benchmark_saa_robustez.py [tam1 tam2 ...]
"""
from __future__ import annotations

import sys

from core.contextual_matrix import construir_matriz_contextual, construir_nodos
from core.candidate_generator import preparar_modelo
from core.data_models import PerfilDecision
from core.optimizer_ortools import resolver_cvrptw
from core.planner import matriz_base_tiempos
from core.saa import comparar_robustez
from core.uncertainty import (buffer_sla_por_nodo, perfil_td_franjas,
                              probabilidades_por_nodo)
from services.cortex_loader import cargar_contexto

TAMANOS_DEFECTO = [16, 24, 32]
ALPHA, BETA = 0.9, 1.0
N_VAL = 400            # escenarios de validacion fuera de muestra
SEED_VAL = 99991


def _modelo_y_warm(ctx, params, n_pedidos):
    hub, veh = ctx["hub"], ctx["vehiculos"]
    pedidos = ctx["pedidos"][:n_pedidos]
    base = matriz_base_tiempos(hub, pedidos, params, None)      # OSRM->cache->haversine
    nodos = construir_nodos(hub, pedidos)
    cm = construir_matriz_contextual(base["tiempo_min"], nodos, ctx["zonas"], ctx["trafico"],
                                     eventos=ctx["eventos"], fecha=None, hora_ref="09:00")
    modelo = preparar_modelo(hub, pedidos, veh, cm["matriz"], base["dist_km"],
                             tiempos_servicio=ctx.get("tiempos_servicio"),
                             jornada_inicio=hub.hora_apertura, jornada_fin=hub.hora_cierre,
                             frac_cuadrillas=float(params.frac_cuadrillas))
    buf = buffer_sla_por_nodo(cm["matriz"], cv=float(params.cv_tiempo),
                              alpha=float(params.nivel_servicio))
    warm = resolver_cvrptw(modelo, PerfilDecision("robusta", w_tiempo=0.6, w_tardanza=1.0,
                                                  w_riesgo=1.0), params, buf)
    ip, idl, au = probabilidades_por_nodo(pedidos, ctx["incidencias"], ctx["zonas"])
    ftd = perfil_td_franjas(ctx["trafico"], jornada_inicio=hub.hora_apertura, hora_ref="09:00")
    return modelo, warm, (ip, idl, au, ftd)


def main(tamanos):
    ctx = cargar_contexto()
    params = ctx["parametros"]
    params.tiempo_solver_seg = max(int(params.tiempo_solver_seg), 8)
    params.iteraciones_alns = max(int(params.iteraciones_alns), 500)

    print(f"Benchmark robustez por diseno (ALNS determinista vs SAA+CVaR)  "
          f"alpha={ALPHA} beta={BETA} n_val={N_VAL}\n")
    cab = (f"{'pedidos':>7} | {'objetivo':^12} | {'dist_km':>8} | {'tard_media':>10} | "
           f"{'tard_p90':>9} | {'CVaR_tard':>9}")
    print(cab); print("-" * len(cab))
    for n in tamanos:
        modelo, warm, (ip, idl, au, ftd) = _modelo_y_warm(ctx, params, n)
        r = comparar_robustez(modelo, params, ip, idl, au, warm=warm, alpha=ALPHA, beta=BETA,
                              n_train=int(params.n_escenarios_saa), n_val=N_VAL,
                              sigma_viaje=float(params.cv_tiempo), sigma_sistemico=0.10,
                              franjas_td=ftd, seed_train=int(params.semilla_base),
                              seed_val=SEED_VAL)
        for etq, k in (("determinista", "determinista"), ("robusto SAA", "robusto_saa")):
            m = r[k]
            print(f"{n:>7} | {etq:^12} | {m['distancia_km']:>8.1f} | {m['tard_media_min']:>10.1f} "
                  f"| {m['tard_p90_min']:>9.1f} | {m['cvar_tard_min']:>9.1f}")
        print(f"{'':>7} | {'-> reduccion':^12} | {-r['sobrecosto_distancia_km']:>8.1f} | "
              f"{r['reduccion_tard_media_min']:>10.1f} | {'':>9} | {r['reduccion_cvar_min']:>9.1f}")
        print("-" * len(cab))


if __name__ == "__main__":
    tams = [int(x) for x in sys.argv[1:]] or TAMANOS_DEFECTO
    main(tams)
