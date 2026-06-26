"""Adaptador ALM RRC -> formato interno del DSS.

Convierte una ruta del benchmark (depot Station + paradas Dropoff + matriz real de
tiempos) en un `CasoBenchmark` que el motor de optimizacion puede consumir, y tambien
en un DataFrame `pedidos` con las columnas que usa el DSS, por si se desea reusar
funciones existentes.

Decisiones documentadas para datos faltantes (instruccion: solo permitir la ejecucion
comparativa, sin mezclar con la validacion de Lima):
    - Ventana horaria ausente o invalida  -> ventana abierta (sin restriccion).
    - Tiempo de servicio ausente          -> 0 minutos.
    - El benchmark evalua ruteo/secuencia/tiempos; NO modela trafico de Lima,
      instalacion de colchones ni condiciones urbanas que ALM RRC no contiene.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import pandas as pd


# Horizonte maximo plausible para considerar una ventana "confiable" (minutos).
_HORIZONTE_MAX_MIN = 24 * 60


@dataclass
class CasoBenchmark:
    route_id: str
    depot_stop_id: str
    depot_lat: float
    depot_lng: float
    nodos: List[str]                      # nodos[0] = depot; resto = paradas
    matriz_min: Dict[Tuple[str, str], float]
    servicio_min: Dict[str, float]
    ventanas: Dict[str, Optional[Tuple[float, float]]]  # stop -> (ini,fin) min rel o None
    secuencia_real: List[str]             # orden real del conductor (sin depot)
    coords: Dict[str, Tuple[float, float]]
    zonas: Dict[str, str] = field(default_factory=dict)  # stop -> zone_id (depot -> "DEPOT")
    meta: dict = field(default_factory=dict)

    @property
    def n_paradas(self) -> int:
        return len(self.nodos) - 1

    @property
    def stops_entrega(self) -> List[str]:
        return self.nodos[1:]

    def tiempo(self, origen: str, destino: str) -> float:
        """Tiempo de viaje (min) entre dos paradas; 0 si no esta en la matriz."""
        if origen == destino:
            return 0.0
        return float(self.matriz_min.get((origen, destino), 0.0))

    def ventana_confiable(self, stop: str) -> bool:
        return self.ventanas.get(stop) is not None


def _parse_departure_min(meta: dict) -> Optional[pd.Timestamp]:
    """Instante de salida del depot como Timestamp UTC, o None."""
    date = str(meta.get("date", "")).strip()
    hora = str(meta.get("departure_time_utc", "")).strip()
    if not date or not hora or hora.lower() == "nan":
        return None
    try:
        return pd.to_datetime(f"{date} {hora}", utc=True)
    except Exception:
        return None


def _ventana_rel(ini_utc, fin_utc, t0: Optional[pd.Timestamp]) -> Optional[Tuple[float, float]]:
    """Convierte una ventana UTC a minutos relativos a la salida. None si no es confiable."""
    if t0 is None or pd.isna(ini_utc) or pd.isna(fin_utc):
        return None
    try:
        ini = pd.to_datetime(ini_utc, utc=True)
        fin = pd.to_datetime(fin_utc, utc=True)
    except Exception:
        return None
    ini_m = (ini - t0).total_seconds() / 60.0
    fin_m = (fin - t0).total_seconds() / 60.0
    if fin_m <= ini_m:
        return None
    # Recorta a horizonte plausible; descarta ventanas absurdas.
    if fin_m <= 0 or ini_m > _HORIZONTE_MAX_MIN:
        return None
    return (max(0.0, ini_m), min(_HORIZONTE_MAX_MIN, fin_m))


def construir_caso(ruta_data: dict) -> CasoBenchmark:
    """Construye un CasoBenchmark a partir de la salida de alm_loader.cargar_ruta."""
    meta = ruta_data["meta"]
    pedidos = ruta_data["pedidos"].copy()
    matriz = ruta_data["matriz"]

    route_id = meta["route_id"]
    depot = str(meta["station_stop_id"])
    depot_lat = float(meta["station_lat"])
    depot_lng = float(meta["station_lng"])

    # Orden real del conductor: paradas ordenadas por actual_sequence.
    pedidos = pedidos.dropna(subset=["pedido_id"]).copy()
    pedidos["actual_sequence"] = pd.to_numeric(pedidos["actual_sequence"], errors="coerce")
    pedidos_ord = pedidos.sort_values("actual_sequence", na_position="last")
    secuencia_real = [str(s) for s in pedidos_ord["pedido_id"].tolist()]

    nodos = [depot] + secuencia_real

    # Matriz real -> dict (origen,destino)->min.
    matriz_min: Dict[Tuple[str, str], float] = {}
    for o, d, t in zip(matriz["origen_stop_id"].astype(str),
                       matriz["destino_stop_id"].astype(str),
                       matriz["tiempo_viaje_min"]):
        matriz_min[(o, d)] = float(t)

    # Servicio por parada (min); ausente -> 0. Zona por parada (para SDzone).
    servicio_min: Dict[str, float] = {}
    coords: Dict[str, Tuple[float, float]] = {depot: (depot_lat, depot_lng)}
    zonas: Dict[str, str] = {depot: "DEPOT"}
    t0 = _parse_departure_min(meta)
    ventanas: Dict[str, Optional[Tuple[float, float]]] = {depot: None}

    tiene_ventana_cols = {"ventana_inicio_utc", "ventana_fin_utc"}.issubset(pedidos.columns)
    tiene_zona = "zona" in pedidos.columns
    for _, p in pedidos_ord.iterrows():
        sid = str(p["pedido_id"])
        servicio_min[sid] = float(p.get("tiempo_servicio_total_min", 0) or 0.0)
        coords[sid] = (float(p["latitud"]), float(p["longitud"]))
        if tiene_zona and pd.notna(p.get("zona")):
            zonas[sid] = str(p["zona"])
        else:
            zonas[sid] = "SIN_ZONA"
        if tiene_ventana_cols:
            ventanas[sid] = _ventana_rel(
                p.get("ventana_inicio_utc"), p.get("ventana_fin_utc"), t0
            )
        else:
            ventanas[sid] = None

    return CasoBenchmark(
        route_id=route_id,
        depot_stop_id=depot,
        depot_lat=depot_lat,
        depot_lng=depot_lng,
        nodos=nodos,
        matriz_min=matriz_min,
        servicio_min=servicio_min,
        ventanas=ventanas,
        secuencia_real=secuencia_real,
        coords=coords,
        zonas=zonas,
        meta=meta,
    )


def caso_a_pedidos_dss(caso: CasoBenchmark) -> pd.DataFrame:
    """DataFrame con columnas estilo DSS (por si se desea reusar funciones existentes).

    No se usa en el flujo principal del benchmark (que opera con la matriz real),
    pero deja el puente disponible y documentado.
    """
    filas = []
    for sid in caso.stops_entrega:
        lat, lng = caso.coords[sid]
        v = caso.ventanas.get(sid)
        filas.append({
            "pedido_id": sid,
            "zona": "ALM",
            "latitud": lat,
            "longitud": lng,
            "peso_kg": 1.0,
            "tipo_servicio": "Estandar",
            "tiempo_servicio_min": caso.servicio_min.get(sid, 0.0),
            "ventana_inicio": "09:00" if v is None else _min_to_hhmm(v[0]),
            "ventana_fin": "19:00" if v is None else _min_to_hhmm(v[1]),
        })
    return pd.DataFrame(filas)


def _min_to_hhmm(m: float) -> str:
    m = int(max(0, min(23 * 60 + 59, m)))
    return f"{m // 60:02d}:{m % 60:02d}"
