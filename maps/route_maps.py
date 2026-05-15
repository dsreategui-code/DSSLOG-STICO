"""Mapas interactivos Folium con rutas, almacen y pedidos."""
import folium
from folium.features import DivIcon
import pandas as pd

from config.settings import ALMACEN
from utils.constants import COLOR_ESTADO


COLORES_VEHICULO = [
    "#0C111D", "#1570EF", "#027A48", "#B54708", "#B42318",
    "#7F56D9", "#0E96CC", "#475467", "#DC6803", "#101828",
]


def _color_para_vehiculo(veh_id: str) -> str:
    try:
        n = int("".join(c for c in veh_id if c.isdigit()) or "1")
    except Exception:
        n = 1
    return COLORES_VEHICULO[(n - 1) % len(COLORES_VEHICULO)]


def _crear_mapa_base() -> folium.Map:
    m = folium.Map(
        location=[ALMACEN["latitud"], ALMACEN["longitud"]],
        zoom_start=11, tiles="CartoDB positron",
        control_scale=True,
    )
    # Marcador del almacen
    folium.Marker(
        [ALMACEN["latitud"], ALMACEN["longitud"]],
        popup=f"<b>{ALMACEN['nombre']}</b><br>{ALMACEN['distrito']}",
        tooltip="Almacen",
        icon=folium.Icon(color="black", icon="warehouse", prefix="fa"),
    ).add_to(m)
    return m


def mapa_rutas(rutas: dict, pedidos: pd.DataFrame,
               vehiculo_id: str = None, modo: str = "iniciales",
               entregas: pd.DataFrame = None) -> folium.Map:
    """Mapa con rutas por vehiculo. Si modo == 'comparar', dibuja inicial vs final con dash."""
    m = _crear_mapa_base()
    if not rutas or pedidos is None or pedidos.empty:
        return m
    idx = pedidos.set_index("pedido_id")
    estado_por_pid = {}
    if entregas is not None and not entregas.empty:
        estado_por_pid = dict(zip(entregas["pedido_id"], entregas["estado"]))

    target = {vehiculo_id: rutas[vehiculo_id]} if vehiculo_id and vehiculo_id in rutas else rutas

    for veh_id, ruta in target.items():
        secuencia = ruta.get("secuencia") if isinstance(ruta, dict) else getattr(ruta, "secuencia", [])
        if not secuencia:
            continue
        color = _color_para_vehiculo(veh_id)
        coords = [[ALMACEN["latitud"], ALMACEN["longitud"]]]
        for i, pid in enumerate(secuencia, start=1):
            if pid not in idx.index:
                continue
            p = idx.loc[pid]
            estado = estado_por_pid.get(pid, "Pendiente")
            estado_color = COLOR_ESTADO.get(estado, "#64748B")
            coords.append([p["latitud"], p["longitud"]])
            # Marcador con numero de orden
            folium.CircleMarker(
                location=[p["latitud"], p["longitud"]],
                radius=8,
                color=color, weight=2,
                fill=True, fill_color=estado_color, fill_opacity=0.85,
                popup=folium.Popup(
                    f"<b>{pid}</b><br>{p.get('cliente','')}<br>"
                    f"{p.get('distrito','')} - {p.get('zona','')}<br>"
                    f"Ventana: {p['ventana_inicio']} - {p['ventana_fin']}<br>"
                    f"Tipo: {p.get('tipo_servicio','')}<br>"
                    f"<b>Estado:</b> {estado}",
                    max_width=260,
                ),
                tooltip=f"{veh_id} - parada {i}",
            ).add_to(m)
            folium.map.Marker(
                [p["latitud"], p["longitud"]],
                icon=DivIcon(
                    icon_size=(20, 20),
                    icon_anchor=(10, 10),
                    html=f'<div style="font-size:10px; color:white; '
                         f'text-align:center; line-height:18px; font-weight:600;">{i}</div>',
                ),
            ).add_to(m)

        folium.PolyLine(
            coords, color=color, weight=3.2, opacity=0.85,
            tooltip=f"{veh_id} - ruta {modo}",
        ).add_to(m)

    folium.LayerControl().add_to(m)
    return m


def mapa_comparativo(rutas_iniciales: dict, rutas_finales: dict,
                     pedidos: pd.DataFrame, vehiculo_id: str = None) -> folium.Map:
    """Dibuja ruta inicial (linea continua) y final (linea punteada) del mismo vehiculo."""
    m = _crear_mapa_base()
    if pedidos is None or pedidos.empty:
        return m
    idx = pedidos.set_index("pedido_id")

    target_ids = [vehiculo_id] if vehiculo_id else list(rutas_iniciales.keys())
    for veh_id in target_ids:
        ini = rutas_iniciales.get(veh_id, {})
        fin = rutas_finales.get(veh_id, {})
        sec_ini = ini.get("secuencia") if isinstance(ini, dict) else getattr(ini, "secuencia", [])
        sec_fin = fin.get("secuencia") if isinstance(fin, dict) else getattr(fin, "secuencia", [])
        color = _color_para_vehiculo(veh_id)

        def _poly(sec, dash):
            coords = [[ALMACEN["latitud"], ALMACEN["longitud"]]]
            for pid in sec:
                if pid in idx.index:
                    p = idx.loc[pid]
                    coords.append([p["latitud"], p["longitud"]])
            folium.PolyLine(
                coords, color=color, weight=3 if not dash else 2.4,
                opacity=0.8 if not dash else 0.65,
                dash_array=None if not dash else "8,8",
                tooltip=f"{veh_id} - {'inicial' if not dash else 'final'}",
            ).add_to(m)

        if sec_ini:
            _poly(sec_ini, dash=False)
        if sec_fin:
            _poly(sec_fin, dash=True)

    return m
