"""Restricciones operativas para asignacion y replanificacion."""
from dataclasses import dataclass
import pandas as pd

from utils.formatters import hhmm_to_minutes


@dataclass
class CapacityCheck:
    ok: bool
    carga_unidades: int
    carga_kg: float
    capacidad_unidades: int
    capacidad_kg: float


def check_capacity(pedidos_asignados: pd.DataFrame, vehiculo: pd.Series) -> CapacityCheck:
    """Verifica que la suma de pedidos no exceda capacidades del vehiculo."""
    n = int(len(pedidos_asignados))
    kg = float(pedidos_asignados["peso_kg"].sum()) if not pedidos_asignados.empty else 0.0
    cap_u = int(vehiculo.get("capacidad_unidades", 0))
    cap_kg = float(vehiculo.get("capacidad_kg", 0))
    return CapacityCheck(
        ok=(n <= cap_u and kg <= cap_kg),
        carga_unidades=n,
        carga_kg=kg,
        capacidad_unidades=cap_u,
        capacidad_kg=cap_kg,
    )


def within_jornada(hhmm: str, inicio: str = "09:00", fin: str = "19:00") -> bool:
    """Devuelve True si la hora cae en la jornada operativa."""
    m = hhmm_to_minutes(hhmm)
    return hhmm_to_minutes(inicio) <= m <= hhmm_to_minutes(fin)


def overlap_minutes(start1: int, end1: int, start2: int, end2: int) -> int:
    """Solapamiento (min) entre dos intervalos en minutos."""
    return max(0, min(end1, end2) - max(start1, start2))


def fits_time_window(hora_llegada_min: int, ventana_inicio: str,
                     ventana_fin: str, tolerancia_min: int = 0) -> bool:
    ini = hhmm_to_minutes(ventana_inicio) - tolerancia_min
    fin = hhmm_to_minutes(ventana_fin) + tolerancia_min
    return ini <= hora_llegada_min <= fin


def respects_intravehicle(asignacion: pd.DataFrame) -> bool:
    """Cada pedido debe pertenecer a un solo vehiculo (regla critica del DSS)."""
    if asignacion is None or asignacion.empty:
        return True
    return asignacion["pedido_id"].duplicated().sum() == 0
