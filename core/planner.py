"""Pipeline de planificacion del DSS CORTEX-LM.

Orquesta el flujo completo de planificacion inicial uniendo todos los modulos del motor:

  contexto -> factibilidad -> matriz base (OSRM/cache/respaldo) -> matriz contextual ->
  rutas candidatas (perfiles) -> simulacion estocastica + riesgo (IRI) -> recomendacion
  explicable -> escenario para el gemelo digital.

Trabaja con heuristicas, metaheuristicas y simulacion: produce soluciones de buena calidad
y una recomendacion, NO optimos garantizados. La matriz base usa OSRM local; si no esta
disponible ni hay cache, usa una matriz de respaldo (haversine) claramente marcada.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from config.cortex_settings import FACTOR_CIRCUITO, VELOCIDAD_RESPALDO_KMH
from core.candidate_generator import generar_candidatas, preparar_modelo
from core.contextual_matrix import construir_matriz_contextual, construir_nodos
from core.feasibility import verificar
from core.recommender import evaluar_candidatas, recomendar
from utils.formatters import hhmm_to_minutes

T_INICIO_DEFECTO = 9 * 60


def _haversine_km(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    R = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _matrices_haversine(coords, velocidad_kmh: float):
    n = len(coords)
    t = np.zeros((n, n)); d = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                km = _haversine_km(coords[i], coords[j]) * FACTOR_CIRCUITO   # distancia por calle aprox.
                d[i][j] = km
                t[i][j] = km / max(velocidad_kmh, 1.0) * 60.0
    return t, d


def matriz_base_tiempos(hub, pedidos, params, osrm=None) -> dict:
    """Matriz base de tiempos (min) y distancias (km). OSRM -> cache -> respaldo haversine."""
    coords = [hub.coord] + [p.coord for p in pedidos]
    if params.usar_osrm and osrm is not None:
        try:
            m = osrm.matriz_base(coords, usar_cache=params.usar_cache_osrm)
            return {"tiempo_min": m["duracion_min"], "dist_km": m["distancia_km"],
                    "origen": m["origen"]}
        except Exception:  # noqa: BLE001  (OSRM no disponible y sin cache: respaldo)
            pass
    t, d = _matrices_haversine(coords, VELOCIDAD_RESPALDO_KMH)
    return {"tiempo_min": t, "dist_km": d, "origen": "haversine_respaldo"}


def _escenario_desde_evaluacion(contexto, pedidos, modelo, evaluacion) -> dict:
    """Construye el escenario del gemelo digital desde la candidata recomendada."""
    hub = contexto["hub"]
    iri_map = {}
    if evaluacion is not None and evaluacion.get("iri") is not None:
        iri_map = dict(zip(evaluacion["iri"]["pedido_id"], evaluacion["iri"]["iri"]))
    res = evaluacion["resultado"] if evaluacion else {"rutas": {}}
    rutas = {}
    geometrias = {}
    for veh, rc in res.get("rutas", {}).items():
        paradas = []
        for s in rc.secuencia:
            idx = s.idx_nodo
            p = pedidos[idx - 1]
            paradas.append({
                "pedido_id": p.pedido_id, "coord": (p.lat, p.lon),
                "eta_min": round(T_INICIO_DEFECTO + s.eta_min, 1),
                "servicio_min": float(modelo.servicio_min[idx]),
                "tardanza_min": round(s.tardanza_min, 1),
                "iri": float(iri_map.get(p.pedido_id, 0.0)),
                "ventana_fin_min": hhmm_to_minutes(p.ventana_fin),
                "distrito": p.distrito})
        if paradas:
            rutas[veh] = paradas
            geometrias[veh] = ([[hub.lon, hub.lat]]
                               + [[pp["coord"][1], pp["coord"][0]] for pp in paradas])
    return {"hub": {"nombre": hub.nombre, "lat": hub.lat, "lon": hub.lon},
            "rutas": rutas, "geometrias": geometrias,
            "t_inicio_min": float(T_INICIO_DEFECTO), "jornada_fin_min": 19 * 60,
            "vehiculos": list(rutas.keys()), "n_pedidos": sum(len(v) for v in rutas.values())}


def planificar(contexto: dict, *, fecha: Optional[str] = None, osrm=None,
               max_pedidos: Optional[int] = None, hora_ref: str = "09:00",
               robusto: bool = True, radio_ambiguedad: str = "medio",
               alpha: float = 0.9, beta: float = 1.0) -> dict:
    """Ejecuta el pipeline completo. Devuelve factibilidad, matriz, candidatas, recomendacion
    y el escenario para el gemelo digital.

    Si `robusto` (por defecto), la seleccion entre candidatas es DISTRIBUCIONALMENTE ROBUSTA
    (DRO): cada candidata se estresa contra un conjunto de ambiguedad y se elige la de mejor
    PEOR CASO ajustado por riesgo (CVaR). Si es False, usa la seleccion por utilidad promedio.
    """
    hub = contexto["hub"]
    pedidos = contexto["pedidos"][:max_pedidos] if max_pedidos else contexto["pedidos"]
    vehiculos = contexto["vehiculos"]
    params = contexto["parametros"]

    # Si no se inyecto un cliente OSRM y los parametros lo piden, se crea uno por defecto
    # (endpoint OSRM_BASE_URL). Si OSRM no responde, matriz_base_tiempos cae a haversine.
    if osrm is None and params.usar_osrm:
        try:
            from geo.osrm_client import OSRMClient
            osrm = OSRMClient()
        except Exception:  # noqa: BLE001
            osrm = None

    sub_ctx = {**contexto, "pedidos": pedidos}
    osrm_disp = False
    try:
        osrm_disp = bool(osrm and params.usar_osrm and osrm.disponible())
    except Exception:  # noqa: BLE001
        osrm_disp = False
    feas = verificar(sub_ctx, osrm_disponible=osrm_disp, cache_disponible=False)
    if not feas["factible"]:
        return {"factible": False, "factibilidad": feas, "recomendacion": None,
                "candidatas": [], "escenario": None}

    base = matriz_base_tiempos(hub, pedidos, params, osrm)
    nodos = construir_nodos(hub, pedidos)
    ctx_mat = construir_matriz_contextual(
        base["tiempo_min"], nodos, contexto["zonas"], contexto["trafico"],
        eventos=contexto["eventos"], fecha=fecha, hora_ref=hora_ref)

    modelo = preparar_modelo(hub, pedidos, vehiculos, ctx_mat["matriz"], base["dist_km"],
                             tiempos_servicio=contexto.get("tiempos_servicio"),
                             jornada_inicio=hub.hora_apertura, jornada_fin=hub.hora_cierre,
                             frac_cuadrillas=float(getattr(params, "frac_cuadrillas", 0.5)))

    # Ventanas probabilisticas: buffer de nivel de servicio por nodo (chance-constrained).
    from core.uncertainty import buffer_sla_por_nodo
    buffer_sla = buffer_sla_por_nodo(ctx_mat["matriz"], cv=float(params.cv_tiempo),
                                     alpha=float(params.nivel_servicio))

    candidatas = generar_candidatas(modelo, contexto["perfiles"], params, buffer_sla=buffer_sla)

    if robusto:
        from core.robust_evaluation import evaluar_robusto, recomendar_robusto
        from core.uncertainty import conjunto_ambiguedad, perfil_td_franjas
        amb = conjunto_ambiguedad(radio_ambiguedad)
        # Perfil de trafico dependiente de la hora (TD-VRP) para la simulacion de riesgo.
        franjas_td = perfil_td_franjas(contexto["trafico"],
                                       jornada_inicio=hub.hora_apertura, hora_ref=hora_ref)
        evaluaciones = []
        for cand in candidatas:
            res = cand["resultado"]
            if res.get("status") != "ok" or not res.get("rutas"):
                continue
            evaluaciones.append(evaluar_robusto(
                res, modelo, pedidos, contexto["incidencias"], contexto["zonas"], params,
                ambiguedad=amb, alpha=alpha, beta=beta, franjas_td=franjas_td))
        reco = recomendar_robusto(evaluaciones)
        modo = f"robusto (DRO, radio={radio_ambiguedad})"
        ambiguedad_nombres = [c.nombre for c in amb]
    else:
        evaluaciones = evaluar_candidatas(candidatas, modelo, params)
        reco = recomendar(evaluaciones)
        modo = "promedio"
        ambiguedad_nombres = []

    elegida = reco.get("elegida") or next(
        (e for e in evaluaciones if e["perfil"] == reco["recomendada"]),
        evaluaciones[0] if evaluaciones else None)

    # Escenario del gemelo POR candidata (para que el usuario elija cual animar).
    escenarios = {}
    for e in evaluaciones:
        if e.get("resultado"):
            escenarios[e["perfil"]] = _escenario_desde_evaluacion(contexto, pedidos, modelo, e)
    escenario = escenarios.get(reco["recomendada"]) or (
        _escenario_desde_evaluacion(contexto, pedidos, modelo, elegida) if elegida else None)

    return {
        "factible": True, "factibilidad": feas, "modo": modo,
        "matriz_origen": base["origen"], "factores_contextuales": ctx_mat["factores"],
        "candidatas": [c["kpis"] for c in candidatas],
        "evaluaciones": evaluaciones, "recomendacion": reco,
        "perfil_recomendado": reco["recomendada"],
        "iri_recomendada": elegida["iri"] if elegida else None,
        "escenario": escenario, "escenarios": escenarios, "n_pedidos": len(pedidos),
        "ambiguedad": ambiguedad_nombres,
    }
