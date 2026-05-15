"""Motor de simulacion estocastica de la jornada de ultima milla.

Recorre cada ruta vehiculo a vehiculo, aplica:
  - tiempos de viaje basados en distancia y velocidad
  - multiplicador de trafico por franja horaria
  - tiempo de servicio con ruido normal
  - incidencias probabilisticas
  - alertas de riesgo cuando se proyecta incumplimiento de ventana
  - replanificacion intravehiculo (opcional, automatica o sugerida)

Devuelve un dict con entregas, alertas, eventos, rutas (inicial/final) y KPIs.
"""
from dataclasses import asdict
from typing import Dict, List
import math
import random
import numpy as np
import pandas as pd

from config.settings import ALMACEN
from optimization.route_optimizer import (
    Ruta, construir_rutas_iniciales, _dist_km,
)
from simulation import events
from simulation.metrics import compute_kpis, compute_otd_evolution
from simulation.replanning import evaluar_replanificacion, aplicar_replanificacion
from utils.formatters import hhmm_to_minutes
from utils.constants import (
    ESTADO_A_TIEMPO, ESTADO_FUERA_VENTANA, ESTADO_FALLIDA,
    ESTADO_REPLANIFICADA, ESTADO_PENDIENTE,
)


def _multiplicador_trafico(min_t: int, perfiles_df: pd.DataFrame) -> float:
    """Devuelve el multiplicador de trafico vigente."""
    if perfiles_df is None or perfiles_df.empty:
        return 1.0
    for _, row in perfiles_df.iterrows():
        ini = hhmm_to_minutes(row["franja_inicio"])
        fin = hhmm_to_minutes(row["franja_fin"])
        if ini <= min_t < fin:
            return float(row["multiplicador"])
    return 1.0


def _muestrear_incidencia(prob_df: pd.DataFrame, rng: random.Random) -> tuple:
    """Devuelve (tipo_incidencia, demora_min) o (None, 0) si no ocurre."""
    if prob_df is None or prob_df.empty:
        return None, 0
    for _, row in prob_df.iterrows():
        if rng.random() < float(row["probabilidad"]):
            tipo = row["incidencia"]
            demora = {
                "trafico_severo": rng.uniform(8, 20),
                "estacionamiento_dificil": rng.uniform(3, 10),
                "acceso_restringido": rng.uniform(4, 12),
                "cliente_ausente": rng.uniform(5, 15),
                "rechazo_entrega": rng.uniform(2, 8),
                "demora_pago": rng.uniform(2, 7),
            }.get(tipo, rng.uniform(2, 8))
            # rechazo_entrega marca fallida; aqui se modela como demora
            return tipo, demora
    return None, 0


def _estado_entrega(hora_llegada_min: int, ventana_inicio: str,
                    ventana_fin: str, fallida: bool = False) -> str:
    if fallida:
        return ESTADO_FALLIDA
    ini = hhmm_to_minutes(ventana_inicio)
    fin = hhmm_to_minutes(ventana_fin)
    if ini <= hora_llegada_min <= fin:
        return ESTADO_A_TIEMPO
    return ESTADO_FUERA_VENTANA


def _retraso_min(hora_llegada_min: int, ventana_fin: str) -> float:
    fin = hhmm_to_minutes(ventana_fin)
    return max(0.0, hora_llegada_min - fin)


def simular_jornada(dataset: dict, rutas: Dict[str, Ruta] = None,
                    configuracion: dict = None,
                    replanifica: bool = True,
                    aprobacion_automatica: bool = True,
                    seed: int = None) -> dict:
    """Ejecuta la simulacion de un dia completo.

    Args:
        dataset: dict con dataframes (pedidos, vehiculos, perfiles_trafico, ...)
        rutas: dict de Ruta por vehiculo. Si None, se construyen iniciales.
        configuracion: dict con parametros de la simulacion.
        replanifica: si True habilita replanificacion intravehiculo.
        aprobacion_automatica: si True (validacion) aplica replan sin esperar al supervisor.
        seed: semilla para reproducibilidad.
    """
    cfg = configuracion or {}
    rng = random.Random(seed if seed is not None else cfg.get("semilla", 42))
    np_rng = np.random.default_rng(seed if seed is not None else cfg.get("semilla", 42))

    pedidos = dataset["pedidos"].copy()
    vehiculos = dataset["vehiculos"]
    perfiles = dataset.get("perfiles_trafico")
    prob_inc = dataset.get("probabilidades_incidencias")

    velocidad = float(cfg.get("velocidad_kmh", 18.0))
    umbral_riesgo = int(cfg.get("umbral_riesgo_min", 15))
    hora_inicio = hhmm_to_minutes(cfg.get("jornada_inicio", "09:00"))
    hora_fin = hhmm_to_minutes(cfg.get("jornada_fin", "19:00"))

    if rutas is None:
        rutas = construir_rutas_iniciales(pedidos, vehiculos, velocidad_kmh=velocidad)
    rutas_iniciales = {v: Ruta(**asdict(r)) for v, r in rutas.items()}
    rutas_actuales = {v: Ruta(**asdict(r)) for v, r in rutas.items()}

    ped_idx = pedidos.set_index("pedido_id")
    entregas_rows = []
    eventos: List[events.Evento] = []
    alertas: List[dict] = []
    decisiones: List[dict] = []
    pedidos_atendidos = set()

    for veh_id, ruta in rutas_actuales.items():
        t = hora_inicio
        cur_lat, cur_lon = ALMACEN["latitud"], ALMACEN["longitud"]
        eventos.append(events.evento_salida(t, veh_id))

        i = 0
        while i < len(ruta.secuencia):
            pid = ruta.secuencia[i]
            if pid in pedidos_atendidos or pid not in ped_idx.index:
                i += 1
                continue
            p = ped_idx.loc[pid]

            dist = _dist_km(cur_lat, cur_lon, p["latitud"], p["longitud"])
            mult = _multiplicador_trafico(t, perfiles)
            viaje = (dist / max(velocidad, 1.0)) * 60.0 * mult
            viaje *= float(np_rng.normal(1.0, 0.06))  # ruido viaje
            viaje = max(2.0, viaje)
            t += viaje
            eventos.append(events.evento_llegada(int(t), veh_id, pid))

            tipo_inc, demora_inc = _muestrear_incidencia(prob_inc, rng)
            fallida = (tipo_inc == "rechazo_entrega") and rng.random() < 0.4
            if tipo_inc:
                eventos.append(events.evento_incidencia(int(t), veh_id, pid, tipo_inc, demora_inc))
                t += demora_inc

            # Detectar riesgo proyectado en pedidos pendientes del mismo vehiculo
            if replanifica and i + 1 < len(ruta.secuencia):
                pendientes = [pp for pp in ruta.secuencia[i+1:]
                              if pp not in pedidos_atendidos]
                if pendientes:
                    riesgo = _calcular_riesgo(pendientes, ped_idx, t, cur_lat, cur_lon, velocidad)
                    if riesgo["riesgo_min"] > umbral_riesgo:
                        propuesta = evaluar_replanificacion(
                            ruta, pedidos, pendientes, int(t),
                            motivo=(
                                f"Proyeccion de retraso > {umbral_riesgo} min "
                                f"({riesgo['riesgo_min']:.0f} min en {riesgo['pedidos_riesgo']} pedidos)"
                            ),
                            velocidad_kmh=velocidad,
                            pos_lat=cur_lat, pos_lon=cur_lon,
                        )
                        propuesta_dict = propuesta.to_dict()
                        alertas.append(propuesta_dict)
                        eventos.append(events.evento_alerta_riesgo(
                            int(t), veh_id,
                            f"Riesgo de incumplimiento en {riesgo['pedidos_riesgo']} pedidos pendientes.",
                        ))
                        if aprobacion_automatica and propuesta.otd_propuesto > propuesta.otd_actual:
                            rutas_actuales = aplicar_replanificacion(rutas_actuales, propuesta)
                            ruta = rutas_actuales[veh_id]
                            decisiones.append({
                                "vehiculo_id": veh_id,
                                "decision": "aprobada",
                                "pedidos_recuperados": propuesta.pedidos_recuperados,
                                "delta_otd": propuesta.otd_propuesto - propuesta.otd_actual,
                                "timestamp_min": int(t),
                            })
                            eventos.append(events.evento_replanificacion(
                                int(t), veh_id,
                                "Replanificacion intravehiculo aplicada automaticamente.",
                                pendientes,
                            ))

            # Servicio
            servicio_real = float(np_rng.normal(p["tiempo_servicio_min"],
                                                p["tiempo_servicio_min"] * 0.12))
            servicio_real = max(2.0, servicio_real)
            eventos.append(events.evento_inicio_servicio(int(t), veh_id, pid))
            inicio_serv = t
            t += servicio_real

            estado = _estado_entrega(int(inicio_serv), p["ventana_inicio"],
                                     p["ventana_fin"], fallida=fallida)
            retraso = _retraso_min(int(inicio_serv), p["ventana_fin"]) if not fallida else 0.0
            eventos.append(events.evento_fin_servicio(int(t), veh_id, pid, estado))

            entregas_rows.append({
                "pedido_id": pid,
                "vehiculo_id": veh_id,
                "cliente": p.get("cliente", ""),
                "distrito": p.get("distrito", ""),
                "zona": p.get("zona", ""),
                "tipo_servicio": p.get("tipo_servicio", ""),
                "peso_kg": float(p.get("peso_kg", 0)),
                "ventana_inicio": p["ventana_inicio"],
                "ventana_fin": p["ventana_fin"],
                "hora_llegada_min": int(inicio_serv - servicio_real if False else t - servicio_real),
                "inicio_servicio_min": int(inicio_serv),
                "fin_servicio_min": int(t),
                "tiempo_viaje_min": round(viaje, 1),
                "tiempo_servicio_real_min": round(servicio_real, 1),
                "tiempo_total_min": round(viaje + servicio_real + demora_inc, 1),
                "estado": estado,
                "retraso_min": round(retraso, 1),
                "incidencia": tipo_inc or "",
                "tiempo_op_min": int(t - hora_inicio),
            })
            pedidos_atendidos.add(pid)
            cur_lat, cur_lon = p["latitud"], p["longitud"]
            i += 1

            if t > hora_fin:
                # Pedidos restantes pendientes
                for rest in ruta.secuencia[i:]:
                    if rest in pedidos_atendidos:
                        continue
                    p_rest = ped_idx.loc[rest] if rest in ped_idx.index else None
                    if p_rest is None:
                        continue
                    entregas_rows.append({
                        "pedido_id": rest,
                        "vehiculo_id": veh_id,
                        "cliente": p_rest.get("cliente", ""),
                        "distrito": p_rest.get("distrito", ""),
                        "zona": p_rest.get("zona", ""),
                        "tipo_servicio": p_rest.get("tipo_servicio", ""),
                        "peso_kg": float(p_rest.get("peso_kg", 0)),
                        "ventana_inicio": p_rest["ventana_inicio"],
                        "ventana_fin": p_rest["ventana_fin"],
                        "hora_llegada_min": None,
                        "inicio_servicio_min": None,
                        "fin_servicio_min": int(hora_fin),
                        "tiempo_viaje_min": 0,
                        "tiempo_servicio_real_min": 0,
                        "tiempo_total_min": 0,
                        "estado": ESTADO_PENDIENTE,
                        "retraso_min": 0,
                        "incidencia": "jornada_terminada",
                        "tiempo_op_min": int(hora_fin - hora_inicio),
                    })
                    pedidos_atendidos.add(rest)
                break

    entregas_df = pd.DataFrame(entregas_rows)
    eventos_df = pd.DataFrame([e.to_dict() for e in eventos])
    kpis = compute_kpis(entregas_df, alertas)
    evolucion = compute_otd_evolution(entregas_df, step_min=15)

    return {
        "entregas": entregas_df,
        "eventos": eventos_df,
        "alertas": alertas,
        "decisiones": decisiones,
        "kpis": kpis,
        "evolucion_otd": evolucion,
        "rutas_iniciales": {v: asdict(r) for v, r in rutas_iniciales.items()},
        "rutas_finales": {v: asdict(r) for v, r in rutas_actuales.items()},
    }


def _calcular_riesgo(pendientes: list, ped_idx: pd.DataFrame, t_actual: float,
                     cur_lat: float, cur_lon: float, velocidad: float) -> dict:
    """Estima riesgo acumulado de retraso para los pedidos pendientes."""
    total_riesgo = 0.0
    n_riesgo = 0
    lat, lon = cur_lat, cur_lon
    t = t_actual
    for pid in pendientes:
        if pid not in ped_idx.index:
            continue
        p = ped_idx.loc[pid]
        d = _dist_km(lat, lon, p["latitud"], p["longitud"])
        t += (d / max(velocidad, 1.0)) * 60.0
        v_fin = hhmm_to_minutes(p["ventana_fin"])
        if t > v_fin:
            total_riesgo += (t - v_fin)
            n_riesgo += 1
        t += float(p["tiempo_servicio_min"])
        lat, lon = p["latitud"], p["longitud"]
    return {"riesgo_min": total_riesgo, "pedidos_riesgo": n_riesgo}


def simular_escenarios(dataset: dict, configuracion: dict,
                       iteraciones: int = 30) -> dict:
    """Corre Monte Carlo sobre los escenarios definidos en configuracion."""
    escenarios = configuracion.get("escenarios_activos") or [
        "sin_dss", "solo_ruta", "dss_completo"
    ]
    velocidad = float(configuracion.get("velocidad_kmh", 18.0))
    semilla_base = int(configuracion.get("semilla", 42))

    pedidos = dataset["pedidos"]
    vehiculos = dataset["vehiculos"]

    rutas_optimizadas = construir_rutas_iniciales(pedidos, vehiculos, velocidad_kmh=velocidad)

    iteraciones_rows = []
    resultados_finales = {}
    for esc in escenarios:
        replanifica = (esc == "dss_completo")
        usa_optimizacion = (esc != "sin_dss")
        rutas_base = rutas_optimizadas if usa_optimizacion else \
            _rutas_baseline_sin_dss(pedidos, vehiculos)

        agregados_otd = []
        ultimo = None
        for it in range(iteraciones):
            res = simular_jornada(
                dataset, rutas=rutas_base, configuracion=configuracion,
                replanifica=replanifica, aprobacion_automatica=True,
                seed=semilla_base + it * 7,
            )
            kpis = res["kpis"]
            iteraciones_rows.append({
                "escenario": esc,
                "iteracion": it + 1,
                **kpis,
            })
            agregados_otd.append(kpis.get("otd", 0))
            ultimo = res
        resultados_finales[esc] = ultimo
        resultados_finales[esc]["otd_promedio_iter"] = float(np.mean(agregados_otd)) if agregados_otd else 0.0
        resultados_finales[esc]["otd_std_iter"] = float(np.std(agregados_otd)) if agregados_otd else 0.0

    return {
        "escenarios": resultados_finales,
        "iteraciones": pd.DataFrame(iteraciones_rows),
        "escenarios_lista": escenarios,
    }


def _rutas_baseline_sin_dss(pedidos: pd.DataFrame, vehiculos: pd.DataFrame) -> Dict[str, Ruta]:
    """Asignacion baseline 'sin DSS': por orden de llegada del pedido (ID) sin reorden."""
    rutas: Dict[str, Ruta] = {}
    vlist = vehiculos["vehiculo_id"].tolist()
    for v in vlist:
        rutas[v] = Ruta(vehiculo_id=v, secuencia=[])
    for i, p in pedidos.reset_index(drop=True).iterrows():
        v = vlist[i % len(vlist)]
        rutas[v].secuencia.append(p["pedido_id"])
    # Tiempos/distancias placeholder (no se necesitan exactos para baseline)
    return rutas
