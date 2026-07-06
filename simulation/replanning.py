"""Replanificacion intravehiculo: reordena solo pedidos pendientes del mismo vehiculo.

Regla critica del DSS: NO se reasignan pedidos entre vehiculos, ni se permiten
transbordos ni vehiculos de apoyo. Esta restriccion se aplica en todos los
puntos de entrada de este modulo.

Una propuesta solo es "aprobable" si representa una mejora real. Ver
`propuesta_es_mejora()` para la logica de decision exacta.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import pandas as pd

from optimization.route_optimizer import reordenar_intravehiculo, Ruta


# Tolerancias para neutralizar ruido de coma flotante en la comparacion
EPS_OTD = 0.05         # 0.05 % se considera "OTD igual"
EPS_TIEMPO_MIN = 0.1   # 0.1 min se considera "tiempo igual"


def propuesta_es_mejora(propuesta) -> bool:
    """Decide si una propuesta de replanificacion debe mostrarse al supervisor
    o aprobarse automaticamente en validacion.

    Criterios:
        1. Mejora OTD                            -> ACEPTAR
        2. OTD igual y mejora tiempo             -> ACEPTAR
        3. Mejora distancia pero empeora OTD     -> RECHAZAR
        4. Reduce tiempo pero empeora OTD        -> RECHAZAR
        5. Aumenta tiempo y reduce OTD           -> RECHAZAR

    Si OTD empeora, la propuesta siempre se descarta sin importar tiempo o distancia.
    """
    delta_otd = float(propuesta.otd_propuesto) - float(propuesta.otd_actual)
    delta_tiempo = float(propuesta.tiempo_propuesto_min) - float(propuesta.tiempo_actual_min)

    # Criterio 1: OTD mejora claramente
    if delta_otd > EPS_OTD:
        return True
    # Criterio 2: OTD se mantiene y el tiempo total baja
    if abs(delta_otd) <= EPS_OTD and delta_tiempo < -EPS_TIEMPO_MIN:
        return True
    # Criterios 3, 4, 5: cualquier otra combinacion no es una mejora real
    return False


def motivo_descarte(propuesta) -> str:
    """Etiqueta legible del motivo por el que una propuesta se descarta.

    Devuelve cadena vacia si la propuesta SI es una mejora (no se descarta).
    """
    if propuesta_es_mejora(propuesta):
        return ""
    delta_otd = float(propuesta.otd_propuesto) - float(propuesta.otd_actual)
    delta_tiempo = float(propuesta.tiempo_propuesto_min) - float(propuesta.tiempo_actual_min)
    if delta_otd < -EPS_OTD and delta_tiempo < -EPS_TIEMPO_MIN:
        return "Reduce tiempo pero empeora OTD"
    if delta_otd < -EPS_OTD and delta_tiempo > EPS_TIEMPO_MIN:
        return "Aumenta tiempo y reduce OTD"
    if delta_otd < -EPS_OTD:
        return "Empeora OTD"
    if abs(delta_otd) <= EPS_OTD and delta_tiempo > EPS_TIEMPO_MIN:
        return "Aumenta tiempo sin mejora de OTD"
    return "Sin mejora medible"


def evaluar_y_decidir(ruta_actual: Ruta, pedidos: pd.DataFrame,
                      pedidos_pendientes: List[str], hora_actual_min: int,
                      motivo: str = "Riesgo de incumplimiento detectado",
                      velocidad_kmh: float = 18.0,
                      pos_lat: float = None,
                      pos_lon: float = None,
                      perfiles=None, factor_trafico: float = 1.0) -> Tuple["PropuestaReplanificacion", bool, str]:
    """Combina `evaluar_replanificacion` con la regla de aceptacion.

    Devuelve (propuesta, es_mejora, motivo_descarte_o_vacio).
    """
    p = evaluar_replanificacion(
        ruta_actual, pedidos, pedidos_pendientes, hora_actual_min,
        motivo=motivo, velocidad_kmh=velocidad_kmh,
        pos_lat=pos_lat, pos_lon=pos_lon,
        perfiles=perfiles, factor_trafico=factor_trafico,
    )
    if propuesta_es_mejora(p):
        return p, True, ""
    return p, False, motivo_descarte(p)


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


def _mult_trafico(min_t: int, perfiles) -> float:
    """Multiplicador de trafico vigente segun perfil por franja horaria.

    Replica la logica del motor de simulacion para que la proyeccion de la
    replanificacion sea coherente con la jornada real (mismo modelo de tiempo).
    """
    if perfiles is None or getattr(perfiles, "empty", True):
        return 1.0
    from utils.formatters import hhmm_to_minutes
    for _, row in perfiles.iterrows():
        ini = hhmm_to_minutes(row["franja_inicio"])
        fin = hhmm_to_minutes(row["franja_fin"])
        if ini <= min_t < fin:
            return float(row["multiplicador"])
    return 1.0


def _otd_proyectado(secuencia: List[str], pedidos: pd.DataFrame,
                    hora_actual_min: int, velocidad_kmh: float = 18.0,
                    pos_lat: float = None, pos_lon: float = None,
                    perfiles=None, factor_trafico: float = 1.0) -> tuple:
    """Estima cuantos pedidos llegarian a tiempo siguiendo una secuencia.

    Usa el MISMO modelo de tiempo que el motor de simulacion:
      - multiplicador de trafico por franja x factor_trafico,
      - espera por ventana (si llega antes de ventana_inicio, espera),
      - tiempo de servicio por parada.

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
    n_validos = 0
    for pid in secuencia:
        if pid not in ped_idx.index:
            continue
        p = ped_idx.loc[pid]
        dist = _dist_km(cur_lat, cur_lon, p["latitud"], p["longitud"])
        mult = _mult_trafico(int(t), perfiles) * factor_trafico
        t += (dist / max(velocidad_kmh, 1.0)) * 60.0 * mult
        # Espera por ventana: no se sirve antes del inicio de la ventana.
        v_ini = hhmm_to_minutes(p["ventana_inicio"])
        if t < v_ini:
            t = float(v_ini)
        v_fin = hhmm_to_minutes(p["ventana_fin"])
        if t <= v_fin:
            a_tiempo += 1
        t += float(p["tiempo_servicio_min"])
        cur_lat, cur_lon = p["latitud"], p["longitud"]
        n_validos += 1

    otd = (a_tiempo / n_validos * 100.0) if n_validos else 0.0
    return otd, a_tiempo, t - hora_actual_min


def evaluar_replanificacion(ruta_actual: Ruta, pedidos: pd.DataFrame,
                            pedidos_pendientes: List[str], hora_actual_min: int,
                            motivo: str = "Riesgo de incumplimiento detectado",
                            velocidad_kmh: float = 18.0,
                            pos_lat: float = None,
                            pos_lon: float = None,
                            perfiles=None, factor_trafico: float = 1.0) -> PropuestaReplanificacion:
    """Genera una propuesta comparando ruta actual vs reordenada intravehiculo.

    perfiles y factor_trafico hacen que la proyeccion de OTD/tiempo use el mismo
    modelo de tiempo que la simulacion (trafico + espera por ventana).
    """
    nueva = reordenar_intravehiculo(
        ruta_actual, pedidos, pedidos_pendientes,
        velocidad_kmh=velocidad_kmh,
        pos_actual_lat=pos_lat, pos_actual_lon=pos_lon,
        t_actual_min=hora_actual_min,      # activa el nucleo compartido (Moore-Hodgson del gemelo)
    )

    otd_act, _, t_act = _otd_proyectado(
        ruta_actual.secuencia, pedidos, hora_actual_min,
        velocidad_kmh, pos_lat, pos_lon, perfiles, factor_trafico,
    )
    otd_new, a_tiempo_new, t_new = _otd_proyectado(
        nueva.secuencia, pedidos, hora_actual_min,
        velocidad_kmh, pos_lat, pos_lon, perfiles, factor_trafico,
    )

    # Estimar cuantos pedidos pendientes pasan de "fuera" a "a tiempo"
    _, a_tiempo_act, _ = _otd_proyectado(
        [p for p in ruta_actual.secuencia if p in pedidos_pendientes],
        pedidos, hora_actual_min, velocidad_kmh, pos_lat, pos_lon,
        perfiles, factor_trafico,
    )
    _, a_tiempo_pend, _ = _otd_proyectado(
        [p for p in nueva.secuencia if p in pedidos_pendientes],
        pedidos, hora_actual_min, velocidad_kmh, pos_lat, pos_lon,
        perfiles, factor_trafico,
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


def _seq_de_ruta(ruta) -> list:
    if ruta is None:
        return []
    if isinstance(ruta, dict):
        return list(ruta.get("secuencia", []))
    return list(getattr(ruta, "secuencia", []))


def _campo_ruta(ruta, campo: str, default=0):
    if ruta is None:
        return default
    if isinstance(ruta, dict):
        return ruta.get(campo, default)
    return getattr(ruta, campo, default)


def info_replanificacion_vehiculo(veh_id: str,
                                  rutas_iniciales: dict,
                                  rutas_finales: dict,
                                  alertas: list = None,
                                  decisiones: list = None) -> dict:
    """Extrae la informacion comparativa de un vehiculo para la vista
    "Ruta inicial vs final".

    Devuelve un dict con:
        tuvo_replanificacion: bool
        secuencia_inicial:    list[str]
        secuencia_final:      list[str]
        tiempo_antes_min:     float
        tiempo_despues_min:   float
        delta_tiempo_min:     float (despues - antes; negativo = mejora)
        otd_antes:            float | None  (proyectado por la propuesta)
        otd_despues:          float | None
        delta_otd:            float | None
        pedidos_recuperados:  int (suma de decisiones aprobadas del vehiculo)
        decisiones_aprobadas: int
    """
    sec_ini = _seq_de_ruta((rutas_iniciales or {}).get(veh_id))
    sec_fin = _seq_de_ruta((rutas_finales or {}).get(veh_id))
    tuvo_replan = sec_ini != sec_fin and bool(sec_fin)

    t_antes = float(_campo_ruta((rutas_iniciales or {}).get(veh_id), "tiempo_min", 0.0))
    t_despues = float(_campo_ruta((rutas_finales or {}).get(veh_id), "tiempo_min", 0.0))

    decs_apr = [
        d for d in (decisiones or [])
        if d.get("vehiculo_id") == veh_id and d.get("decision") == "aprobada"
    ]
    pedidos_recuperados = sum(int(d.get("pedidos_recuperados", 0)) for d in decs_apr)

    # Buscar OTD proyectado: primera alerta del vehiculo para "antes",
    # ultima decision aprobada para "despues".
    otd_antes = None
    otd_despues = None
    alts_veh = sorted(
        [a for a in (alertas or []) if a.get("vehiculo_id") == veh_id],
        key=lambda a: a.get("timestamp_min", 0),
    )
    if alts_veh:
        otd_antes = float(alts_veh[0].get("otd_actual", 0))
        otd_despues = float(alts_veh[-1].get("otd_propuesto", 0))

    delta_otd = (otd_despues - otd_antes) if (otd_antes is not None and otd_despues is not None) else None
    delta_tiempo = round(t_despues - t_antes, 1)

    return {
        "tuvo_replanificacion": tuvo_replan,
        "secuencia_inicial": sec_ini,
        "secuencia_final": sec_fin,
        "tiempo_antes_min": round(t_antes, 1),
        "tiempo_despues_min": round(t_despues, 1),
        "delta_tiempo_min": delta_tiempo,
        "otd_antes": otd_antes,
        "otd_despues": otd_despues,
        "delta_otd": delta_otd,
        "pedidos_recuperados": pedidos_recuperados,
        "decisiones_aprobadas": len(decs_apr),
    }


def vehiculos_con_replanificacion(rutas_iniciales: dict,
                                  rutas_finales: dict) -> list:
    """Lista de vehiculos cuya secuencia inicial difiere de la final."""
    ids = list((rutas_iniciales or {}).keys())
    out = []
    for v in ids:
        ini = _seq_de_ruta((rutas_iniciales or {}).get(v))
        fin = _seq_de_ruta((rutas_finales or {}).get(v))
        if ini != fin and fin:
            out.append(v)
    return out


def tabla_comparativa_secuencia(secuencia_inicial: list,
                                secuencia_final: list,
                                pedidos: pd.DataFrame = None) -> pd.DataFrame:
    """Construye una tabla lado a lado de la secuencia inicial vs la final,
    enriquecida con datos del pedido cuando se provee `pedidos`.

    Columnas: orden, pedido_inicial, pedido_final, distrito, ventana, cambio.
    """
    n = max(len(secuencia_inicial), len(secuencia_final))
    rows = []
    ped_idx = (pedidos.set_index("pedido_id") if pedidos is not None and not pedidos.empty
               else None)
    for i in range(n):
        pid_ini = secuencia_inicial[i] if i < len(secuencia_inicial) else None
        pid_fin = secuencia_final[i] if i < len(secuencia_final) else None
        distrito = ventana = ""
        ref = pid_fin or pid_ini
        if ped_idx is not None and ref in ped_idx.index:
            p = ped_idx.loc[ref]
            distrito = str(p.get("distrito", ""))
            ventana = f"{p.get('ventana_inicio', '-')} - {p.get('ventana_fin', '-')}"
        cambio = "Sin cambio" if pid_ini == pid_fin else "Movido"
        rows.append({
            "orden": i + 1,
            "pedido_inicial": pid_ini or "-",
            "pedido_final": pid_fin or "-",
            "distrito": distrito,
            "ventana": ventana,
            "cambio": cambio,
        })
    return pd.DataFrame(rows)
