# -*- coding: utf-8 -*-
"""Puente de ruteo con el motor CORTEX-LM para la VALIDACION Monte Carlo.

Unifica el motor: la validacion deja de construir rutas con el optimizador v1
(`optimization/route_optimizer`) y usa el MISMO motor que el demo
(`core/planner.planificar`: matriz contextual + APIs + OR-Tools + ALNS + robustez SAA/DRO).
Adapta el plan recomendado a los objetos `Ruta` que consume el simulador (`simulation/sim_engine`).
"""
from __future__ import annotations

from typing import Dict, Optional

from optimization.route_optimizer import Ruta


def construir_contexto(dataset: dict, *, solver_seg: Optional[int] = 6) -> dict:
    """Contexto CORTEX-LM ALINEADO con el dataset de la validacion (mismos pedidos/vehiculos que se
    simulan). Reutiliza `cargar_contexto` (plantillas + criminalidad/POIs + factores contextuales) y
    sustituye pedidos/vehiculos por los del dataset usando las conversiones de dominio existentes.

    Nota: `cargar_contexto` ya lee de `load_dataset()` (la misma fuente que la validacion), pero se
    re-alinean explicitamente por si el llamador filtro o modifico el dataset.

    `solver_seg`: presupuesto de OR-Tools por perfil. La validacion corre planificar 2 veces (x N
    escenarios), asi que se acota (def 6s) para mantener la corrida responsiva; None = usar el de la
    plantilla."""
    from services.cortex_loader import cargar_contexto
    from core.data_models import Pedido, Vehiculo
    ctx = dict(cargar_contexto())
    ctx["pedidos"] = [Pedido.desde_fila(r) for _, r in dataset["pedidos"].iterrows()]
    ctx["vehiculos"] = [Vehiculo.desde_fila(r) for _, r in dataset["vehiculos"].iterrows()]
    if solver_seg is not None:
        ctx["parametros"].tiempo_solver_seg = int(solver_seg)
    return ctx


def rutas_cortex(contexto: dict, *, robusto: bool = False, nivel_servicio: Optional[float] = None,
                 cv_tiempo: Optional[float] = None, fecha: Optional[str] = None) -> Dict[str, Ruta]:
    """Corre `planificar` sobre el contexto y adapta el plan recomendado a `Dict[str, Ruta]`.

    ROBUSTEZ POR BUFFER (el planteo correcto): la robustez se controla con el BUFFER de seguridad
    (`nivel_servicio` α + `cv_tiempo`), que optimiza contra `ventana_fin − buffer` y adelanta las
    entregas donde la incertidumbre lo justifica. MISMO motor, una perilla: α alto = mas holgura =
    robusto; α normal = determinista. `robusto` (DRO/SAA en la seleccion) queda como opcion heredada."""
    from core.planner import planificar
    par = contexto["parametros"]
    prev = (getattr(par, "usar_saa", True), par.nivel_servicio, par.cv_tiempo)
    par.usar_saa = bool(robusto)
    if nivel_servicio is not None:
        par.nivel_servicio = float(nivel_servicio)
    if cv_tiempo is not None:
        par.cv_tiempo = float(cv_tiempo)
    try:
        plan = planificar(contexto, robusto=bool(robusto), fecha=fecha)
    finally:
        par.usar_saa, par.nivel_servicio, par.cv_tiempo = prev
    return _plan_a_rutas(plan)


def _plan_a_rutas(plan: dict) -> Dict[str, Ruta]:
    """Extrae la candidata RECOMENDADA del plan y la convierte en objetos Ruta (secuencia de
    pedido_id). Devuelve {} si el plan no es factible o no tiene rutas."""
    if not plan or not plan.get("factible"):
        return {}
    reco = plan.get("recomendacion") or {}
    elegida = reco.get("elegida")
    if elegida is None:
        perfil = plan.get("perfil_recomendado")
        elegida = next((e for e in plan.get("evaluaciones", [])
                        if e.get("perfil") == perfil), None)
    if not elegida or not elegida.get("resultado"):
        return {}
    rutas: Dict[str, Ruta] = {}
    for veh, rc in elegida["resultado"].get("rutas", {}).items():
        seq = [s.pedido_id for s in rc.secuencia if s.pedido_id != "HUB"]
        if seq:
            rutas[veh] = Ruta(
                vehiculo_id=veh, secuencia=seq,
                distancia_km=float(getattr(rc, "distancia_km", 0.0) or 0.0),
                tiempo_min=float(getattr(rc, "tiempo_min", 0.0) or 0.0),
            )
    return rutas
