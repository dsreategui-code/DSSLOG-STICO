"""Verificacion de factibilidad previa a la planificacion (CORTEX-LM).

Comprueba que la jornada sea resoluble antes de invocar al optimizador: capacidad de flota
vs demanda (peso y volumen), ventanas validas, coordenadas presentes, numero de vehiculos y
disponibilidad de una fuente de matriz de tiempos (OSRM o cache). Distingue ERRORES (bloquean)
de AVISOS (degradan pero permiten continuar). No inventa datos: si falta algo critico, lo
reporta con claridad.
"""
from __future__ import annotations

from typing import List

from utils.formatters import hhmm_to_minutes


def _chk(nombre, ok, nivel, detalle):
    return {"nombre": nombre, "ok": bool(ok), "nivel": nivel, "detalle": detalle}


def verificar(contexto: dict, osrm_disponible: bool = False,
              cache_disponible: bool = False) -> dict:
    pedidos = contexto["pedidos"]
    vehiculos = contexto["vehiculos"]
    checks: List[dict] = []

    checks.append(_chk("pedidos", len(pedidos) > 0, "error",
                       f"{len(pedidos)} pedidos cargados"))
    checks.append(_chk("vehiculos", len(vehiculos) > 0, "error",
                       f"{len(vehiculos)} vehiculos"))

    sin_coord = [p.pedido_id for p in pedidos if not p.tiene_coordenadas()]
    checks.append(_chk("coordenadas", len(sin_coord) == 0, "error",
                       "todas con lat/lon" if not sin_coord
                       else f"{len(sin_coord)} pedidos sin coordenadas (ej. {sin_coord[:3]})"))

    ventana_mala = []
    for p in pedidos:
        try:
            if hhmm_to_minutes(p.ventana_inicio) >= hhmm_to_minutes(p.ventana_fin):
                ventana_mala.append(p.pedido_id)
        except Exception:  # noqa: BLE001
            ventana_mala.append(p.pedido_id)
    checks.append(_chk("ventanas_horarias", len(ventana_mala) == 0, "error",
                       "ventanas validas" if not ventana_mala
                       else f"{len(ventana_mala)} ventanas invalidas (inicio>=fin)"))

    dem_kg = sum(p.peso_kg for p in pedidos)
    cap_kg = sum(v.capacidad_kg for v in vehiculos)
    checks.append(_chk("capacidad_peso", cap_kg + 1e-6 >= dem_kg, "error",
                       f"flota {cap_kg:.0f} kg vs demanda {dem_kg:.0f} kg"))

    dem_m3 = sum(p.volumen_m3 for p in pedidos)
    cap_m3 = sum(v.capacidad_m3 for v in vehiculos)
    if dem_m3 > 0 and cap_m3 > 0:
        checks.append(_chk("capacidad_volumen", cap_m3 + 1e-6 >= dem_m3, "error",
                           f"flota {cap_m3:.1f} m3 vs demanda {dem_m3:.1f} m3"))

    fuente_ok = osrm_disponible or cache_disponible
    checks.append(_chk("fuente_matriz", fuente_ok, "aviso",
                       "OSRM disponible" if osrm_disponible else
                       ("cache OSRM disponible" if cache_disponible else
                        "sin OSRM ni cache: se usara matriz de respaldo (haversine)")))

    errores = [c for c in checks if c["nivel"] == "error" and not c["ok"]]
    avisos = [c for c in checks if c["nivel"] == "aviso" and not c["ok"]]
    return {"factible": len(errores) == 0, "checks": checks,
            "errores": errores, "avisos": avisos}
