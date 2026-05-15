"""Generador de enlaces de navegacion Waze."""
from urllib.parse import quote


WAZE_BASE = "https://www.waze.com/ul"


def waze_link(lat: float, lon: float, etiqueta: str = "") -> str:
    """Devuelve la URL de Waze para una coordenada."""
    qs = f"?ll={lat:.6f}%2C{lon:.6f}&navigate=yes"
    if etiqueta:
        qs += f"&q={quote(etiqueta)}"
    return WAZE_BASE + qs


def waze_links_for_route(secuencia: list, pedidos_df) -> list:
    """Devuelve una lista de dicts con info de navegacion para cada parada."""
    if not secuencia or pedidos_df is None:
        return []
    idx = pedidos_df.set_index("pedido_id")
    out = []
    for i, pid in enumerate(secuencia, start=1):
        if pid not in idx.index:
            continue
        p = idx.loc[pid]
        etiqueta = f"{pid} - {p.get('cliente', '')}"
        out.append({
            "orden": i,
            "pedido_id": pid,
            "cliente": p.get("cliente", ""),
            "distrito": p.get("distrito", ""),
            "direccion": p.get("direccion", ""),
            "ventana": f"{p.get('ventana_inicio', '-')} - {p.get('ventana_fin', '-')}",
            "tipo_servicio": p.get("tipo_servicio", ""),
            "latitud": float(p.get("latitud", 0)),
            "longitud": float(p.get("longitud", 0)),
            "url_waze": waze_link(p["latitud"], p["longitud"], etiqueta),
        })
    return out
