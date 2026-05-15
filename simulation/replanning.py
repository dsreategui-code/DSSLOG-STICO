"""Replanificacion intravehiculo: reordena solo pedidos pendientes del mismo vehiculo.

Regla critica del DSS: NO se reasignan pedidos entre vehiculos, ni se permiten
transbordos ni vehiculos de apoyo. Esta restriccion se aplica en todos los
puntos de entrada de este modulo.
"""
from dataclasses import dataclass, field
from typing import Dict, List
import pandas as pd

from optimization.route_optimizer import reordenar_intravehiculo, Ruta


@dataclass
class PropuestaReplanificacion:
    vehiculo_id: str
    motivo: str
    ruta_actual: List[str] = field(default_factory=list)
    ruta_propuesta: List[str] = field(default_factory=list)
    tiempo_actual_min: float = 0.0
    tiempo_propuesto_min: float = 0.0
    otd_actual: float = 0.0
    otd_propuesto: float = 0.0
    pedidos_recuperados: int = 0
    impacto_distancia_km: float = 0.0
    timestamp_min: int = 0

    def to_dict(self) -> dict:
        return {
            "vehiculo_id": self.vehiculo_id,
            "motivo": self.motivo,
            "ruta_actual": self.ruta_actual,
            "ruta_propuesta": self.ruta_propuesta,
            "tiempo_actual_min": self.tiempo_actual_min,
            "tiempo_propuesto_min": self.tiempo_propuesto_min,
            "otd_actual": self.otd_actual,
            "otd_propuesto": self.otd_propuesto,
            "pedidos_recuperados": self.pedidos_recuperados,
            "impacto_distancia_km": self.impacto_distancia_km,
            "timestamp_min": self.timestamp_min,
            "tipo": "replanificacion_intravehiculo",
        }


def _otd_proyectado(secuencia: List[str], pedidos: pd.DataFrame,
                    hora_actual_min: int, velocidad_kmh: float = 18.0,
                    pos_lat: float = None, pos_lon: float = None) -> tuple:
    """Estima cuantos pedidos llegarian a tiempo siguiendo una secuencia.

    Devuelve (otd_estimado_pct, pedidos_a_tiempo, tiempo_total_min).
    """
    from utils.formatters import hhmm_to_minutes
    from optimization.route_optimizer import _dist_km
    from config.settings import ALMACEN

    if not secuencia or pedidos is None:
        return 0.0, 0, 0.0

    base_lat = pos_lat if pos_lat is not None else ALMACEN["latitud"]
    base_lon = pos_lon if pos_lon is not None else ALMACEN["longitud"]

    ped_idx = pedidos.set_index("pedido_id")
    cur_lat, cur_lon = base_lat, base_lon
    t = hora_actual_min
    a_tiempo = 0
    for pid in secuencia:
        if pid not in ped_idx.index:
            continue
        p = ped_idx.loc[pid]
        dist = _dist_km(cur_lat, cur_lon, p["latitud"], p["longitud"])
        t += (dist / max(velocidad_kmh, 1.0)) * 60.0
        v_fin = hhmm_to_minutes(p["ventana_fin"])
        if t <= v_fin:
            a_tiempo += 1
        t += float(p["tiempo_servicio_min"])
        cur_lat, cur_lon = p["latitud"], p["longitud"]

    total = len(secuencia)
    otd = (a_tiempo / total * 100.0) if total else 0.0
    return otd, a_tiempo, t - hora_actual_min


def evaluar_replanificacion(ruta_actual: Ruta, pedidos: pd.DataFrame,
                            pedidos_pendientes: List[str], hora_actual_min: int,
                            motivo: str = "Riesgo de incumplimiento detectado",
                            velocidad_kmh: float = 18.0,
                            pos_lat: float = None,
                            pos_lon: float = None) -> PropuestaReplanificacion:
    """Genera una propuesta comparando ruta actual vs reordenada intravehiculo."""
    nueva = reordenar_intravehiculo(
        ruta_actual, pedidos, pedidos_pendientes,
        velocidad_kmh=velocidad_kmh,
        pos_actual_lat=pos_lat, pos_actual_lon=pos_lon,
    )

    otd_act, _, t_act = _otd_proyectado(
        ruta_actual.secuencia, pedidos, hora_actual_min,
        velocidad_kmh, pos_lat, pos_lon,
    )
    otd_new, a_tiempo_new, t_new = _otd_proyectado(
        nueva.secuencia, pedidos, hora_actual_min,
        velocidad_kmh, pos_lat, pos_lon,
    )

    # Estimar cuantos pedidos pendientes pasan de "fuera" a "a tiempo"
    _, a_tiempo_act, _ = _otd_proyectado(
        [p for p in ruta_actual.secuencia if p in pedidos_pendientes],
        pedidos, hora_actual_min, velocidad_kmh, pos_lat, pos_lon,
    )
    _, a_tiempo_pend, _ = _otd_proyectado(
        [p for p in nueva.secuencia if p in pedidos_pendientes],
        pedidos, hora_actual_min, velocidad_kmh, pos_lat, pos_lon,
    )
    recuperados = max(0, a_tiempo_pend - a_tiempo_act)

    return PropuestaReplanificacion(
        vehiculo_id=ruta_actual.vehiculo_id,
        motivo=motivo,
        ruta_actual=list(ruta_actual.secuencia),
        ruta_propuesta=list(nueva.secuencia),
        tiempo_actual_min=round(t_act, 1),
        tiempo_propuesto_min=round(t_new, 1),
        otd_actual=round(otd_act, 1),
        otd_propuesto=round(otd_new, 1),
        pedidos_recuperados=recuperados,
        impacto_distancia_km=round(nueva.distancia_km - ruta_actual.distancia_km, 2),
        timestamp_min=hora_actual_min,
    )


def aplicar_replanificacion(rutas: Dict[str, Ruta],
                            propuesta: PropuestaReplanificacion) -> Dict[str, Ruta]:
    """Aplica una propuesta aprobada al diccionario de rutas (solo el vehiculo objetivo)."""
    nuevas = dict(rutas)
    if propuesta.vehiculo_id not in nuevas:
        return nuevas
    ruta_actual = nuevas[propuesta.vehiculo_id]
    nuevas[propuesta.vehiculo_id] = Ruta(
        vehiculo_id=propuesta.vehiculo_id,
        secuencia=list(propuesta.ruta_propuesta),
        distancia_km=ruta_actual.distancia_km + propuesta.impacto_distancia_km,
        tiempo_min=propuesta.tiempo_propuesto_min,
        carga_unidades=ruta_actual.carga_unidades,
        carga_kg=ruta_actual.carga_kg,
    )
    return nuevas
