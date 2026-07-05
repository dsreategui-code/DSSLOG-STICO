"""Deriva el FACTOR DE SEGURIDAD por distrito desde datos reales de CRIMINALIDAD.

NO es una API viva: la criminalidad se publica como DATASETS/CSV (INEI, Observatorio Nacional de
Seguridad Ciudadana - Mininter, datosabiertos.gob.pe). Se carga como una plantilla mas
(`data/plantillas/criminalidad.csv`). Si NO existe, el motor usa el `factor_seguridad` sintetico
de `zonas.csv` (respaldo). Asi, el realismo entra por el FACTOR sin rediseñar el motor.

El indice delictivo (mayor = mas peligroso; en cualquier unidad: denuncias/1000 hab, victimizacion,
etc.) se NORMALIZA entre distritos a un rango de factor razonable: el mas seguro -> f_min, el mas
peligroso -> f_max. Es relativo (robusto a la unidad del dato) y documentado.
"""
from __future__ import annotations

from typing import Dict

FACTOR_MIN = 1.0          # distrito mas seguro
FACTOR_MAX = 1.5          # distrito mas peligroso


def factores_desde_criminalidad(indices: Dict[str, float], f_min: float = FACTOR_MIN,
                                f_max: float = FACTOR_MAX) -> Dict[str, float]:
    """indice delictivo por distrito (mayor = peor) -> factor de seguridad normalizado en
    [f_min, f_max]. Si todos son iguales, devuelve el punto medio. Robusto a la unidad del dato."""
    vals = [float(v) for v in indices.values()]
    if not vals:
        return {}
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        medio = round((f_min + f_max) / 2, 3)
        return {d: medio for d in indices}
    out = {}
    for d, v in indices.items():
        norm = (float(v) - lo) / (hi - lo)               # 0 (mas seguro) .. 1 (mas peligroso)
        out[d] = round(f_min + (f_max - f_min) * norm, 3)
    return out
