"""Carga del indice y de cada ruta del benchmark DESDE EL CACHE.

Nunca toca los archivos pesados originales. Si el cache no existe, expone
errores claros para que la UI/CLI indiquen como prepararlo.
"""
from typing import Dict, List
import pandas as pd

from benchmark import paths


class BenchmarkNoPreparado(Exception):
    """El cache de muestra no existe todavia."""


def cache_listo() -> bool:
    return paths.is_prepared()


def cargar_indice(solo_high: bool = True) -> pd.DataFrame:
    """Devuelve el indice de la muestra de rutas (una fila por ruta).

    solo_high=True (default) restringe el indice a rutas High Quality, que es la
    base del benchmark principal.
    """
    if not paths.is_prepared():
        raise BenchmarkNoPreparado(
            "El cache de benchmark no existe. Ejecuta: "
            "python -m benchmark.prepare_cache --n-rutas 30"
        )
    df = pd.read_csv(paths.cache_index_file())
    # Benchmark PRINCIPAL: solo rutas High Quality. Filtro de defensa en profundidad
    # por si el cache contuviera rutas de otra calidad (cache legado mixto).
    if solo_high and "route_score" in df.columns:
        high = df[df["route_score"].astype(str).str.lower() == "high"]
        if not high.empty:
            return high.reset_index(drop=True)
    return df


def listar_route_ids(solo_high: bool = True) -> List[str]:
    try:
        return cargar_indice(solo_high=solo_high)["route_id"].tolist()
    except BenchmarkNoPreparado:
        return []


def cargar_ruta(route_id: str) -> Dict:
    """Carga los datos crudos de una ruta desde el cache.

    Devuelve {meta, pedidos, matriz}. Lanza FileNotFoundError si falta algo.
    """
    rdir = paths.cache_ruta_dir(route_id)
    f_ped = rdir / "pedidos.csv"
    f_mat = rdir / "matriz.csv"
    if not f_ped.exists() or not f_mat.exists():
        raise FileNotFoundError(
            f"Ruta {route_id} no esta en el cache. Reconstruye con prepare_cache."
        )

    idx = cargar_indice()
    fila = idx[idx["route_id"] == route_id]
    if fila.empty:
        raise FileNotFoundError(f"Ruta {route_id} no figura en el indice del cache.")
    meta = fila.iloc[0].to_dict()

    pedidos = pd.read_csv(f_ped)
    matriz = pd.read_csv(f_mat)

    # Validaciones minimas de integridad.
    cols_ped = {"pedido_id", "latitud", "longitud", "actual_sequence",
                "tiempo_servicio_total_min"}
    faltan = cols_ped - set(pedidos.columns)
    if faltan:
        raise ValueError(f"Pedidos de {route_id} sin columnas: {faltan}")
    cols_mat = {"origen_stop_id", "destino_stop_id", "tiempo_viaje_min"}
    if not cols_mat.issubset(matriz.columns):
        raise ValueError(f"Matriz de {route_id} sin columnas: {cols_mat - set(matriz.columns)}")

    return {"meta": meta, "pedidos": pedidos, "matriz": matriz}
