"""Asignacion y secuenciacion de rutas iniciales.

Estrategia v1 (estable, sin OR-Tools):
  - Cada pedido se asigna al vehiculo con zona preferente coincidente.
  - Si la capacidad se excede, se rota al siguiente vehiculo de la misma zona;
    si no quedan, se distribuye en vehiculos con menor carga.
  - Dentro de cada vehiculo, los pedidos se ordenan por inicio de ventana
    horaria y luego por proximidad al almacen (greedy nearest neighbor).

El modulo expone una API estable que en el futuro puede sustituirse por
OR-Tools (CVRPTW) sin tocar el resto del proyecto.
"""
from dataclasses import dataclass, field
from typing import Dict, List
import math
import pandas as pd

from config.settings import ALMACEN
from optimization.constraints import check_capacity
from utils.formatters import hhmm_to_minutes


@dataclass
class Ruta:
    vehiculo_id: str
    secuencia: List[str] = field(default_factory=list)
    distancia_km: float = 0.0
    tiempo_min: float = 0.0
    carga_unidades: int = 0
    carga_kg: float = 0.0


def _dist_km(lat1, lon1, lat2, lon2) -> float:
    dx = (lat2 - lat1) * 111.0
    dy = (lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dx * dx + dy * dy)


def _ordenar_pedidos(pedidos: pd.DataFrame, base_lat: float, base_lon: float) -> List[str]:
    """Greedy nearest neighbor con prioridad a ventana horaria temprana."""
    pendientes = pedidos.copy()
    pendientes["v_min"] = pendientes["ventana_inicio"].apply(hhmm_to_minutes)
    pendientes["v_fin_min"] = pendientes["ventana_fin"].apply(hhmm_to_minutes)
    pendientes = pendientes.sort_values(["v_min", "v_fin_min"]).reset_index(drop=True)

    secuencia = []
    cur_lat, cur_lon = base_lat, base_lon
    while not pendientes.empty:
        # Candidatos: pedidos con la ventana mas temprana abierta
        v_min_actual = pendientes["v_min"].min()
        ventana = pendientes[pendientes["v_min"] <= v_min_actual + 60]
        if ventana.empty:
            ventana = pendientes
        ventana = ventana.copy()
        ventana["dist"] = ventana.apply(
            lambda r: _dist_km(cur_lat, cur_lon, r["latitud"], r["longitud"]),
            axis=1,
        )
        siguiente = ventana.sort_values("dist").iloc[0]
        pid = siguiente["pedido_id"]
        secuencia.append(pid)
        cur_lat, cur_lon = siguiente["latitud"], siguiente["longitud"]
        pendientes = pendientes[pendientes["pedido_id"] != pid].reset_index(drop=True)
    return secuencia


def _calcular_metricas_ruta(ruta_pedidos: pd.DataFrame, base_lat: float,
                            base_lon: float, velocidad_kmh: float = 18.0) -> tuple:
    """Devuelve (distancia_km, tiempo_min) recorriendo en orden + retorno opcional."""
    if ruta_pedidos.empty:
        return 0.0, 0.0
    cur_lat, cur_lon = base_lat, base_lon
    dist_total = 0.0
    for _, p in ruta_pedidos.iterrows():
        dist_total += _dist_km(cur_lat, cur_lon, p["latitud"], p["longitud"])
        cur_lat, cur_lon = p["latitud"], p["longitud"]
    tiempo_min = (dist_total / max(velocidad_kmh, 1.0)) * 60.0
    return dist_total, tiempo_min


def asignar_pedidos(pedidos: pd.DataFrame, vehiculos: pd.DataFrame,
                    factor_balance: float = 1.0) -> Dict[str, List[str]]:
    """Asigna cada pedido a un vehiculo respetando capacidad, zona y balance.

    El cupo efectivo de cada vehiculo se acota a ceil(N/V * factor_balance) para
    distribuir los pedidos entre toda la flota antes de saturar a unos pocos.
    Si la zona preferente esta saturada se busca el vehiculo con menos carga.

    Devuelve un dict {vehiculo_id: [pedido_id, ...]} (sin orden todavia).
    """
    n_pedidos = len(pedidos)
    num_v = len(vehiculos)
    cupo_balance = max(1, math.ceil(n_pedidos / max(num_v, 1) * factor_balance))

    asignacion: Dict[str, List[str]] = {v: [] for v in vehiculos["vehiculo_id"]}
    cargas_u = {v: 0 for v in vehiculos["vehiculo_id"]}
    cargas_kg = {v: 0.0 for v in vehiculos["vehiculo_id"]}
    cap_u_real = dict(zip(vehiculos["vehiculo_id"], vehiculos["capacidad_unidades"]))
    cap_kg = dict(zip(vehiculos["vehiculo_id"], vehiculos["capacidad_kg"]))
    # Cupo efectivo: minimo entre capacidad fisica y cupo de balance
    cap_u = {v: min(int(cap_u_real[v]), cupo_balance) for v in cap_u_real}
    veh_por_zona = vehiculos.groupby("zona_preferente")["vehiculo_id"].apply(list).to_dict()

    pedidos_ord = pedidos.sort_values(
        ["zona", "ventana_inicio", "pedido_id"]
    ).reset_index(drop=True)

    for _, p in pedidos_ord.iterrows():
        zona = p["zona"]
        candidatos = veh_por_zona.get(zona, list(vehiculos["vehiculo_id"]))

        # 1) Vehiculos de la zona con cupo de balance disponible
        viables = [
            v for v in candidatos
            if cargas_u[v] + 1 <= cap_u[v] and cargas_kg[v] + p["peso_kg"] <= cap_kg[v]
        ]
        # 2) Cualquier vehiculo con cupo de balance disponible
        if not viables:
            viables = [
                v for v in vehiculos["vehiculo_id"]
                if cargas_u[v] + 1 <= cap_u[v] and cargas_kg[v] + p["peso_kg"] <= cap_kg[v]
            ]
        # 3) Relajar cupo de balance: cualquier vehiculo con capacidad fisica disponible
        if not viables:
            viables = [
                v for v in vehiculos["vehiculo_id"]
                if cargas_u[v] + 1 <= cap_u_real[v]
                and cargas_kg[v] + p["peso_kg"] <= cap_kg[v]
            ]
        # 4) Ultimo recurso: el de menor carga
        if not viables:
            viables = sorted(vehiculos["vehiculo_id"].tolist(),
                             key=lambda v: cargas_u[v])

        # Elegir el de menor carga relativa
        elegido = min(viables, key=lambda v: cargas_u[v] / max(cap_u_real[v], 1))
        asignacion[elegido].append(p["pedido_id"])
        cargas_u[elegido] += 1
        cargas_kg[elegido] += float(p["peso_kg"])

    return asignacion


def _construir_rutas_greedy(pedidos: pd.DataFrame, vehiculos: pd.DataFrame,
                            velocidad_kmh: float = 18.0) -> Dict[str, Ruta]:
    """Asignacion greedy por zona + nearest neighbor por ventana (fallback estable)."""
    base_lat, base_lon = ALMACEN["latitud"], ALMACEN["longitud"]
    asignacion = asignar_pedidos(pedidos, vehiculos)
    rutas: Dict[str, Ruta] = {}

    for veh_id in vehiculos["vehiculo_id"]:
        pids = asignacion[veh_id]
        sub = pedidos[pedidos["pedido_id"].isin(pids)].copy()
        secuencia = _ordenar_pedidos(sub, base_lat, base_lon) if not sub.empty else []
        sub_ord = sub.set_index("pedido_id").loc[secuencia].reset_index() if secuencia else sub
        dist, tiempo = _calcular_metricas_ruta(sub_ord, base_lat, base_lon, velocidad_kmh)
        rutas[veh_id] = Ruta(
            vehiculo_id=veh_id,
            secuencia=secuencia,
            distancia_km=round(dist, 2),
            tiempo_min=round(tiempo, 1),
            carga_unidades=len(secuencia),
            carga_kg=float(sub["peso_kg"].sum()),
        )
    return rutas


def construir_rutas_iniciales(pedidos: pd.DataFrame, vehiculos: pd.DataFrame,
                              velocidad_kmh: float = 18.0,
                              motor: str = "auto",
                              jornada_inicio: str = "09:00",
                              jornada_fin: str = "19:00",
                              time_limit_seconds: int = 8) -> Dict[str, Ruta]:
    """Construye rutas iniciales con el motor solicitado.

    Args:
        motor: "ortools" para forzar CVRPTW, "greedy" para forzar el fallback,
               "auto" (default) para intentar OR-Tools y degradar al greedy
               si OR-Tools no esta instalado o no encuentra solucion.
    """
    if motor in ("ortools", "auto"):
        try:
            from optimization.route_optimizer_ortools import (
                construir_rutas_or_tools, is_available,
            )
            if is_available():
                rutas = construir_rutas_or_tools(
                    pedidos, vehiculos,
                    velocidad_kmh=velocidad_kmh,
                    jornada_inicio=jornada_inicio,
                    jornada_fin=jornada_fin,
                    time_limit_seconds=time_limit_seconds,
                )
                if rutas is not None:
                    return rutas
            if motor == "ortools":
                # Si fue solicitado explicitamente y fallo, propagar
                raise RuntimeError("OR-Tools no disponible o sin solucion.")
        except RuntimeError:
            raise
        except Exception:
            if motor == "ortools":
                raise
    return _construir_rutas_greedy(pedidos, vehiculos, velocidad_kmh)


def reordenar_intravehiculo(ruta: Ruta, pedidos: pd.DataFrame,
                            pedidos_pendientes: List[str],
                            velocidad_kmh: float = 18.0,
                            pos_actual_lat: float = None,
                            pos_actual_lon: float = None,
                            t_actual_min: float = None) -> Ruta:
    """Reordena solo los pedidos pendientes del mismo vehiculo (regla intravehiculo).

    Los pedidos ya entregados o en curso se mantienen al inicio en su orden original.

    Si se entrega `t_actual_min` (hora actual), usa el MISMO nucleo de re-secuenciacion que el
    gemelo digital (`twin_sim.reordenar_pendientes`: EDD + Moore-Hodgson + vecino-mas-cercano, que
    minimiza el nº de entregas tardias) en vez del greedy nearest-neighbor. Asi validacion y gemelo
    comparten el replanificador. Sin la hora, cae al greedy previo (compat)."""
    if not pedidos_pendientes:
        return ruta
    entregados = [p for p in ruta.secuencia if p not in pedidos_pendientes]

    base_lat = pos_actual_lat if pos_actual_lat is not None else ALMACEN["latitud"]
    base_lon = pos_actual_lon if pos_actual_lon is not None else ALMACEN["longitud"]

    sub = pedidos[pedidos["pedido_id"].isin(pedidos_pendientes)].copy()
    if sub.empty:
        return ruta
    if t_actual_min is not None:
        # Nucleo COMPARTIDO con el gemelo (Moore-Hodgson): respeta el orden actual de los pendientes.
        from core.twin_sim import reordenar_pendientes
        orden_actual = [p for p in ruta.secuencia if p in pedidos_pendientes]
        idx = sub.set_index("pedido_id")
        pend = [{"pedido_id": pid,
                 "coord": (float(idx.loc[pid, "latitud"]), float(idx.loc[pid, "longitud"])),
                 "ventana_fin_min": hhmm_to_minutes(str(idx.loc[pid, "ventana_fin"])),
                 "servicio_min": float(idx.loc[pid].get("tiempo_servicio_min", 8.0))}
                for pid in orden_actual]
        orden, _ = reordenar_pendientes(pend, float(t_actual_min), (base_lat, base_lon))
        nueva_secuencia_pendientes = [p["pedido_id"] for p in orden]
    else:
        nueva_secuencia_pendientes = _ordenar_pedidos(sub, base_lat, base_lon)
    nueva_secuencia = entregados + nueva_secuencia_pendientes

    sub_full = pedidos[pedidos["pedido_id"].isin(nueva_secuencia)].set_index("pedido_id").loc[nueva_secuencia].reset_index()
    dist, tiempo = _calcular_metricas_ruta(
        sub_full, ALMACEN["latitud"], ALMACEN["longitud"], velocidad_kmh
    )
    return Ruta(
        vehiculo_id=ruta.vehiculo_id,
        secuencia=nueva_secuencia,
        distancia_km=round(dist, 2),
        tiempo_min=round(tiempo, 1),
        carga_unidades=len(nueva_secuencia),
        carga_kg=ruta.carga_kg,
    )


def rutas_to_dataframe(rutas: Dict[str, Ruta]) -> pd.DataFrame:
    """Convierte el dict de rutas a un dataframe largo."""
    rows = []
    for veh_id, ruta in rutas.items():
        for i, pid in enumerate(ruta.secuencia, start=1):
            rows.append({
                "vehiculo_id": veh_id,
                "secuencia": i,
                "pedido_id": pid,
            })
    return pd.DataFrame(rows)
