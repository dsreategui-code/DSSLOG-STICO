"""Capas PyDeck del gemelo digital operativo.

Construye las capas del mapa (HUB, pedidos, vehiculos, rutas, etiquetas) y el Deck. Usa un
basemap de Carto sin token (positron). Colores por estado de pedido y de vehiculo. PyDeck
es el visualizador principal del gemelo (no Folium).

Convencion: PyDeck usa [lon, lat]. El dominio usa (lat, lon).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import pydeck as pdk

MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

COLOR_PEDIDO = {
    "pendiente": [152, 162, 179, 200], "en_ruta": [21, 112, 239, 220],
    "en_servicio": [13, 148, 136, 230], "entregado": [2, 122, 72, 200],
    "en_riesgo": [181, 71, 8, 235], "fallido": [180, 35, 24, 235],
    "reprogramado": [127, 86, 217, 225],
}
COLOR_VEHICULO = {
    "disponible": [152, 162, 179, 235], "en_ruta": [21, 112, 239, 255],
    "en_servicio": [13, 148, 136, 255], "retrasado": [181, 71, 8, 255],
    "finalizado": [2, 122, 72, 235],
}
COLOR_RUTA = {
    "planificada": [21, 112, 239, 140], "replanificada": [181, 71, 8, 200],
    "original": [152, 162, 179, 120],
}


def _color(mapa: dict, estado: str) -> List[int]:
    return mapa.get(str(estado), [120, 120, 120, 200])


def capa_hub(hub: dict) -> pdk.Layer:
    df = pd.DataFrame([{"coordenada": [hub["lon"], hub["lat"]],
                        "nombre": hub.get("nombre", "HUB")}])
    return pdk.Layer("ScatterplotLayer", df, get_position="coordenada",
                     get_fill_color=[12, 17, 29, 255], get_radius=180,
                     radius_min_pixels=7, radius_max_pixels=18, pickable=True)


def capa_pedidos(df_estado: pd.DataFrame) -> pdk.Layer:
    df = df_estado.copy()
    df["coordenada"] = df.apply(lambda r: [r["lon"], r["lat"]], axis=1)
    df["color"] = df["estado"].map(lambda e: _color(COLOR_PEDIDO, e))
    return pdk.Layer("ScatterplotLayer", df, get_position="coordenada",
                     get_fill_color="color", get_radius=90, radius_min_pixels=4,
                     radius_max_pixels=12, pickable=True)


def capa_rutas(escenario: dict, ruta_tipo_por_veh: Optional[Dict[str, str]] = None) -> pdk.Layer:
    ruta_tipo_por_veh = ruta_tipo_por_veh or {}
    geoms = escenario.get("geometrias", {})
    hub_ll = [escenario["hub"]["lon"], escenario["hub"]["lat"]]
    filas = []
    for veh, paradas in escenario["rutas"].items():
        path = geoms.get(veh)
        if not path:
            path = [hub_ll] + [[p["coord"][1], p["coord"][0]] for p in paradas]
        tipo = ruta_tipo_por_veh.get(veh, "planificada")
        filas.append({"vehiculo_id": veh, "path": path, "color": _color(COLOR_RUTA, tipo)})
    df = pd.DataFrame(filas)
    return pdk.Layer("PathLayer", df, get_path="path", get_color="color",
                     width_scale=1, width_min_pixels=2, get_width=4, pickable=True)


def capa_vehiculos(df_tick: pd.DataFrame) -> pdk.Layer:
    df = df_tick.copy()
    df["coordenada"] = df.apply(lambda r: [r["lon"], r["lat"]], axis=1)
    df["color"] = df["estado_vehiculo"].map(lambda e: _color(COLOR_VEHICULO, e))
    return pdk.Layer("ScatterplotLayer", df, get_position="coordenada",
                     get_fill_color="color", get_radius=140, radius_min_pixels=6,
                     radius_max_pixels=16, stroked=True, get_line_color=[255, 255, 255, 230],
                     line_width_min_pixels=1, pickable=True)


def capa_etiquetas_vehiculos(df_tick: pd.DataFrame) -> pdk.Layer:
    df = df_tick.copy()
    df["coordenada"] = df.apply(lambda r: [r["lon"], r["lat"]], axis=1)
    return pdk.Layer("TextLayer", df, get_position="coordenada",
                     get_text="vehiculo_id", get_size=12, get_color=[12, 17, 29, 255],
                     get_alignment_baseline="'bottom'")


def capa_path_comparacion(path_lonlat: List[List[float]], tipo: str) -> pdk.Layer:
    df = pd.DataFrame([{"path": path_lonlat, "color": _color(COLOR_RUTA, tipo)}])
    return pdk.Layer("PathLayer", df, get_path="path", get_color="color",
                     width_min_pixels=3, get_width=5)


def vista_inicial(hub: dict, zoom: float = 10.5) -> pdk.ViewState:
    return pdk.ViewState(latitude=hub["lat"], longitude=hub["lon"], zoom=zoom, pitch=35)


def construir_deck(layers: List[pdk.Layer], hub: dict,
                   tooltip: Optional[dict] = None) -> pdk.Deck:
    tooltip = tooltip or {"html": "<b>{vehiculo_id}{pedido_id}{nombre}</b><br/>"
                                  "{estado}{estado_vehiculo}",
                          "style": {"backgroundColor": "#0C111D", "color": "white"}}
    return pdk.Deck(layers=layers, initial_view_state=vista_inicial(hub),
                    map_style=MAP_STYLE, tooltip=tooltip)
