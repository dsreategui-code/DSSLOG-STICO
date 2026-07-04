"""Generador de rutas candidatas del motor CORTEX-LM.

Ejecuta el optimizador CVRPTW (core.optimizer_ortools) bajo distintos PERFILES DE DECISION
(eficiente, puntual, robusta, balanceada, estable) sobre la MISMA matriz contextual, y
devuelve una ruta candidata por perfil con sus KPIs basicos. La seleccion final entre
candidatas la hace core.recommender (utilidad DSS), no este modulo.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from core.data_models import (Hub, Parametros, Pedido, PerfilDecision, TiempoServicio,
                              Vehiculo)
from core.optimizer_ortools import ModeloNumerico, resolver_cvrptw
from utils.formatters import hhmm_to_minutes


# Tipos de pedido que requieren una CUADRILLA especializada (instalacion / 2+ personas).
TIPOS_CUADRILLA = {"Instalacion", "Atencion especial"}


def _servicio_de(pedido: Pedido, tiempos: Dict[str, TiempoServicio], defecto: float) -> float:
    ts = tiempos.get(pedido.tipo_pedido) or tiempos.get(pedido.tipo_producto)
    return float(ts.moda) if ts else float(defecto)


def _requiere_cuadrilla(p: Pedido) -> bool:
    return bool(getattr(p, "requiere_instalacion", False) or p.tipo_pedido in TIPOS_CUADRILLA)


def _cumple_operativo(resultado: dict, modelo: ModeloNumerico, jornada_max: int) -> bool:
    """True si el resultado respeta las restricciones operativas duras (jornada del conductor y
    cuadrillas). Se usa para descartar candidatas ALNS no conformes antes del recomendador."""
    req = modelo.requiere_cuadrilla or []
    vc = modelo.vehiculo_cuadrilla or []
    hay_restr_crew = bool(vc) and not all(vc)
    crew_ids = {modelo.vehiculo_ids[i] for i in range(len(vc))
                if vc[i] and i < len(modelo.vehiculo_ids)}
    for veh, rc in resultado.get("rutas", {}).items():
        if jornada_max and (rc.tiempo_min - rc.inicio_min) > jornada_max + 1:
            return False
        if hay_restr_crew and veh not in crew_ids:
            if any(s.idx_nodo < len(req) and req[s.idx_nodo] for s in rc.secuencia):
                return False
    return True


def preparar_modelo(hub: Hub, pedidos: Sequence[Pedido], vehiculos: Sequence[Vehiculo],
                    tiempo_min: np.ndarray, dist_km: np.ndarray,
                    tiempos_servicio: Optional[Sequence[TiempoServicio]] = None,
                    jornada_inicio: str = "09:00", jornada_fin: str = "19:00",
                    servicio_defecto: float = 5.0,
                    frac_cuadrillas: float = 0.5) -> ModeloNumerico:
    """Construye la instancia numerica (nodo 0 = HUB) lista para el resolvedor."""
    t0 = hhmm_to_minutes(jornada_inicio)
    H = hhmm_to_minutes(jornada_fin) - t0
    tmap = {ts.tipo_pedido: ts for ts in (tiempos_servicio or [])}

    ventanas = [(0, H)]
    servicio = [0.0]
    dem_m3 = [0.0]
    dem_kg = [0.0]
    pedido_ids = ["HUB"]
    for p in pedidos:
        ini = max(0, hhmm_to_minutes(p.ventana_inicio) - t0)
        fin = min(H, hhmm_to_minutes(p.ventana_fin) - t0)
        ventanas.append((ini, max(ini, fin)))
        servicio.append(_servicio_de(p, tmap, servicio_defecto))
        dem_m3.append(p.volumen_m3)
        dem_kg.append(p.peso_kg)
        pedido_ids.append(p.pedido_id)

    # Restricciones operativas: pedidos que requieren cuadrilla y vehiculos que la tienen.
    nv = len(vehiculos)
    req_cuadrilla = [False] + [_requiere_cuadrilla(p) for p in pedidos]
    n_cuad = max(1, min(nv, round(float(frac_cuadrillas) * nv))) if nv else 0
    veh_cuadrilla = [i < n_cuad for i in range(nv)]

    return ModeloNumerico(
        tiempo_min=np.asarray(tiempo_min, dtype=float),
        dist_km=np.asarray(dist_km, dtype=float),
        demanda_m3=dem_m3, demanda_kg=dem_kg, ventanas_min=ventanas,
        servicio_min=servicio, pedido_ids=pedido_ids,
        num_vehiculos=nv,
        cap_m3=[v.capacidad_m3 for v in vehiculos],
        cap_kg=[v.capacidad_kg for v in vehiculos],
        vehiculo_ids=[v.vehiculo_id for v in vehiculos],
        horizonte_min=H,
        requiere_cuadrilla=req_cuadrilla,
        vehiculo_cuadrilla=veh_cuadrilla,
    )


def kpis_candidata(resultado: dict, modelo: ModeloNumerico) -> dict:
    """KPIs operativos basicos de una candidata (sin simulacion estocastica)."""
    rutas = resultado.get("rutas", {})
    n_clientes = len(modelo.pedido_ids) - 1
    dist = sum(r.distancia_km for r in rutas.values())
    tmax = max((r.tiempo_min for r in rutas.values()), default=0.0)
    tardanza = sum(r.tardanza_total_min for r in rutas.values())
    servidos = sum(r.n_paradas for r in rutas.values())
    a_tiempo = sum(1 for r in rutas.values() for s in r.secuencia if s.tardanza_min <= 1e-6)
    return {
        "perfil": resultado.get("perfil"),
        "status": resultado.get("status"),
        "n_rutas": len(rutas),
        "n_servidos": servidos,
        "n_no_servidos": len(modelo.pedido_ids) - 1 - servidos,
        "distancia_km": round(dist, 2),
        "tiempo_max_min": round(tmax, 1),
        "tardanza_total_min": round(tardanza, 1),
        "otd_plan": round(a_tiempo / servidos, 4) if servidos else 0.0,
        "cobertura": round(servidos / n_clientes, 4) if n_clientes else 0.0,
    }


def generar_candidatas(modelo: ModeloNumerico, perfiles: Sequence[PerfilDecision],
                       params: Parametros, buffer_sla=None) -> List[dict]:
    """Genera candidatas: una por perfil con OR-Tools (ventanas probabilisticas via
    `buffer_sla`) y, si `params.usar_alns`, refina la mejor con ALNS y agrega sus elites
    diversas. Devuelve [{perfil, resultado, kpis}]."""
    candidatas = []
    mejor_ot, mejor_clave = None, (float("inf"), float("inf"))
    for perfil in perfiles:
        resultado = resolver_cvrptw(modelo, perfil, params, buffer_sla)
        candidatas.append({"perfil": perfil.perfil, "resultado": resultado,
                           "kpis": kpis_candidata(resultado, modelo)})
        if resultado.get("status") == "ok" and resultado.get("rutas"):
            tard = sum(r.tardanza_total_min for r in resultado["rutas"].values())
            dist = sum(r.distancia_km for r in resultado["rutas"].values())
            if (tard, dist) < mejor_clave:
                mejor_clave, mejor_ot = (tard, dist), resultado

    if getattr(params, "usar_alns", False) and mejor_ot is not None:
        from core.alns import optimizar
        perfil_alns = PerfilDecision("robusta", w_tiempo=0.6, w_tardanza=1.0, w_riesgo=1.0)
        out = optimizar(modelo, params, perfil=perfil_alns, buffer_sla=buffer_sla,
                        warm=mejor_ot, n_elites=2)
        jornada_max = int(getattr(params, "jornada_max_min", 0) or 0)
        for i, res_e in enumerate([out["best"]] + out["elites"]):
            if (res_e and res_e.get("status") == "ok" and res_e.get("rutas")
                    and _cumple_operativo(res_e, modelo, jornada_max)):
                res_e["perfil"] = f"alns-{i}"          # etiqueta unica por candidata ALNS
                candidatas.append({"perfil": f"alns-{i}", "resultado": res_e,
                                   "kpis": kpis_candidata(res_e, modelo)})
    return candidatas
