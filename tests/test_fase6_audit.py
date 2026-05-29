"""Auditoria FASE 6 - comparacion clara entre ruta inicial y final."""
import inspect
from pathlib import Path

import pandas as pd
import pytest

from simulation.replanning import (
    info_replanificacion_vehiculo, vehiculos_con_replanificacion,
    tabla_comparativa_secuencia,
)
from views import supervisor_results


ROOT = Path(__file__).resolve().parent.parent


def _src(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


# ============================================================
# Helpers de simulation/replanning
# ============================================================

def test_info_replanificacion_detecta_sin_cambios():
    rutas = {"V01": {"secuencia": ["P1", "P2", "P3"], "tiempo_min": 120.0}}
    info = info_replanificacion_vehiculo("V01", rutas, rutas, alertas=[], decisiones=[])
    assert info["tuvo_replanificacion"] is False
    assert info["secuencia_inicial"] == ["P1", "P2", "P3"]
    assert info["secuencia_final"] == ["P1", "P2", "P3"]


def test_info_replanificacion_detecta_cambio_y_calcula_deltas():
    rini = {"V01": {"secuencia": ["P1", "P2", "P3"], "tiempo_min": 120.0}}
    rfin = {"V01": {"secuencia": ["P2", "P1", "P3"], "tiempo_min": 100.0}}
    alertas = [
        {"vehiculo_id": "V01", "timestamp_min": 600,
         "otd_actual": 60.0, "otd_propuesto": 80.0,
         "tiempo_actual_min": 120, "tiempo_propuesto_min": 100},
    ]
    decisiones = [
        {"vehiculo_id": "V01", "decision": "aprobada",
         "pedidos_recuperados": 2, "delta_otd": 20.0, "timestamp_min": 600},
    ]
    info = info_replanificacion_vehiculo("V01", rini, rfin, alertas, decisiones)
    assert info["tuvo_replanificacion"] is True
    assert info["tiempo_antes_min"] == 120.0
    assert info["tiempo_despues_min"] == 100.0
    assert info["delta_tiempo_min"] == -20.0
    assert info["otd_antes"] == 60.0
    assert info["otd_despues"] == 80.0
    assert info["delta_otd"] == 20.0
    assert info["pedidos_recuperados"] == 2
    assert info["decisiones_aprobadas"] == 1


def test_info_replanificacion_sin_alertas_otd_es_none():
    rini = {"V01": {"secuencia": ["P1"], "tiempo_min": 30}}
    rfin = {"V01": {"secuencia": ["P2"], "tiempo_min": 35}}
    info = info_replanificacion_vehiculo("V01", rini, rfin, [], [])
    assert info["otd_antes"] is None
    assert info["otd_despues"] is None
    assert info["delta_otd"] is None


def test_vehiculos_con_replanificacion_lista_solo_los_que_cambiaron():
    rini = {
        "V01": {"secuencia": ["P1", "P2"]},
        "V02": {"secuencia": ["P3", "P4"]},
        "V03": {"secuencia": ["P5"]},
    }
    rfin = {
        "V01": {"secuencia": ["P2", "P1"]},     # cambio
        "V02": {"secuencia": ["P3", "P4"]},     # sin cambio
        "V03": {"secuencia": ["P5"]},           # sin cambio
    }
    assert vehiculos_con_replanificacion(rini, rfin) == ["V01"]


def test_tabla_comparativa_marca_cambios():
    sec_ini = ["P1", "P2", "P3"]
    sec_fin = ["P2", "P1", "P3"]
    tabla = tabla_comparativa_secuencia(sec_ini, sec_fin)
    cambios = tabla["cambio"].tolist()
    # Las dos primeras posiciones cambiaron, la tercera quedo igual
    assert cambios[0] == "Movido"
    assert cambios[1] == "Movido"
    assert cambios[2] == "Sin cambio"


def test_tabla_comparativa_maneja_longitudes_diferentes():
    """Si una secuencia es mas larga, se completa con '-'."""
    tabla = tabla_comparativa_secuencia(["P1", "P2"], ["P1", "P2", "P3"])
    assert len(tabla) == 3
    assert tabla.iloc[2]["pedido_inicial"] == "-"
    assert tabla.iloc[2]["pedido_final"] == "P3"


def test_tabla_comparativa_enriquece_con_pedidos():
    sec = ["P1"]
    pedidos = pd.DataFrame([
        {"pedido_id": "P1", "distrito": "Callao",
         "ventana_inicio": "09:00", "ventana_fin": "12:00"},
    ])
    tabla = tabla_comparativa_secuencia(sec, sec, pedidos)
    fila = tabla.iloc[0]
    assert fila["distrito"] == "Callao"
    assert "09:00" in fila["ventana"] and "12:00" in fila["ventana"]


# ============================================================
# Vista supervisor_results.py
# ============================================================

def test_supervisor_results_expone_render_tab_comparacion():
    assert hasattr(supervisor_results, "_render_tab_comparacion")
    sig = inspect.signature(supervisor_results._render_tab_comparacion)
    # Debe aceptar rutas_ini, rutas_fin, pedidos, alertas, decisiones, entregas
    params = list(sig.parameters)
    for esperado in ("rutas_ini", "rutas_fin", "pedidos", "alertas", "decisiones"):
        assert esperado in params, f"Falta parametro {esperado}"


def test_supervisor_results_usa_dos_mapas_lado_a_lado():
    src = _src("views/supervisor_results.py")
    # Dos llamadas a st_folium con keys distintas para ini y fin
    assert "sup_res_map_ini" in src
    assert "sup_res_map_fin" in src


def test_supervisor_results_muestra_card_si_no_hubo_replanificacion():
    src = _src("views/supervisor_results.py")
    assert "no tuvo replanificacion" in src.lower()
    assert "info_card(" in src


def test_supervisor_results_muestra_cards_de_mejora():
    """Debe haber cards para tiempo antes, despues, diferencia, OTD antes/despues, recuperados."""
    src = _src("views/supervisor_results.py")
    for etiqueta in ("Tiempo antes", "Tiempo despues", "Diferencia de tiempo",
                     "OTD antes", "OTD despues", "Pedidos recuperados"):
        assert etiqueta in src, f"Falta card '{etiqueta}'"


def test_supervisor_results_incluye_tabla_comparativa():
    src = _src("views/supervisor_results.py")
    assert "tabla_comparativa_secuencia" in src
    assert "Tabla comparativa de secuencia" in src


def test_supervisor_results_no_usa_mas_mapa_comparativo_superpuesto():
    """Reemplazamos mapa_comparativo (linea continua + punteada) por dos mapas."""
    src = _src("views/supervisor_results.py")
    assert "mapa_comparativo(" not in src, (
        "supervisor_results ya no debe usar mapa_comparativo superpuesto; "
        "ahora son dos mapas lado a lado con mapa_rutas."
    )


def test_supervisor_results_filtra_por_vehiculo():
    src = _src("views/supervisor_results.py")
    assert 'st.selectbox(' in src
    assert '"Todos"' in src and "rutas_ini" in src.lower() or "opciones" in src


# ============================================================
# Comportamiento integrado: vehiculo con vs sin replanificacion
# ============================================================

def test_info_replanificacion_acumula_pedidos_recuperados_por_multiples_decisiones():
    rini = {"V05": {"secuencia": ["A", "B", "C"], "tiempo_min": 200}}
    rfin = {"V05": {"secuencia": ["C", "A", "B"], "tiempo_min": 180}}
    alertas = [
        {"vehiculo_id": "V05", "timestamp_min": 600,
         "otd_actual": 50.0, "otd_propuesto": 65.0,
         "tiempo_actual_min": 200, "tiempo_propuesto_min": 185},
        {"vehiculo_id": "V05", "timestamp_min": 700,
         "otd_actual": 65.0, "otd_propuesto": 80.0,
         "tiempo_actual_min": 185, "tiempo_propuesto_min": 180},
    ]
    decisiones = [
        {"vehiculo_id": "V05", "decision": "aprobada",
         "pedidos_recuperados": 1, "timestamp_min": 600},
        {"vehiculo_id": "V05", "decision": "aprobada",
         "pedidos_recuperados": 2, "timestamp_min": 700},
    ]
    info = info_replanificacion_vehiculo("V05", rini, rfin, alertas, decisiones)
    assert info["pedidos_recuperados"] == 3
    assert info["decisiones_aprobadas"] == 2
    # OTD antes = primera alerta, OTD despues = ultima alerta
    assert info["otd_antes"] == 50.0
    assert info["otd_despues"] == 80.0


def test_info_replanificacion_ignora_decisiones_rechazadas():
    rini = {"V01": {"secuencia": ["P1", "P2"], "tiempo_min": 60}}
    rfin = {"V01": {"secuencia": ["P2", "P1"], "tiempo_min": 55}}
    decisiones = [
        {"vehiculo_id": "V01", "decision": "rechazada",
         "pedidos_recuperados": 5, "timestamp_min": 600},
    ]
    info = info_replanificacion_vehiculo("V01", rini, rfin, [], decisiones)
    # decisiones aprobadas = 0 -> no se suman pedidos_recuperados
    assert info["pedidos_recuperados"] == 0
    assert info["decisiones_aprobadas"] == 0
