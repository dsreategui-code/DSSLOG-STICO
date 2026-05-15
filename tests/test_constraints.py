"""Tests de las restricciones operativas."""
import pandas as pd

from optimization.constraints import (
    check_capacity, fits_time_window, within_jornada,
    respects_intravehicle, overlap_minutes,
)


def test_capacidad_dentro_de_limite(vehiculos_min, pedidos_min):
    """Sin sobrepasar capacidad ni en unidades ni en kg."""
    sub = pedidos_min[pedidos_min["pedido_id"].isin(["P001", "P002"])]
    vehiculo = vehiculos_min.iloc[0]
    chk = check_capacity(sub, vehiculo)
    assert chk.ok
    assert chk.carga_unidades == 2
    assert chk.carga_kg == 44


def test_capacidad_se_excede_en_unidades(vehiculos_min, pedidos_min):
    vehiculo = vehiculos_min.iloc[0].copy()
    vehiculo["capacidad_unidades"] = 1
    sub = pedidos_min.iloc[:3]
    chk = check_capacity(sub, vehiculo)
    assert not chk.ok


def test_capacidad_se_excede_en_kg(vehiculos_min, pedidos_min):
    vehiculo = vehiculos_min.iloc[0].copy()
    vehiculo["capacidad_kg"] = 30
    sub = pedidos_min.iloc[:2]
    chk = check_capacity(sub, vehiculo)
    assert not chk.ok


def test_ventana_horaria_se_cumple():
    # 10:30 dentro de la ventana 10:00-13:00
    assert fits_time_window(630, "10:00", "13:00")
    # 13:35 fuera (5 min mas que el limite con 30 min de tolerancia)
    assert not fits_time_window(815, "10:00", "13:00", tolerancia_min=30)
    # 13:10 fuera sin tolerancia, dentro con tolerancia de 15 min
    assert not fits_time_window(790, "10:00", "13:00")
    assert fits_time_window(790, "10:00", "13:00", tolerancia_min=15)


def test_jornada_operativa():
    assert within_jornada("09:00")
    assert within_jornada("18:59")
    assert not within_jornada("08:30")
    assert not within_jornada("19:30")


def test_intravehiculo_sin_duplicados():
    """Cada pedido debe aparecer en exactamente un vehiculo."""
    asign = pd.DataFrame([
        {"vehiculo_id": "V01", "pedido_id": "P001", "secuencia": 1},
        {"vehiculo_id": "V01", "pedido_id": "P002", "secuencia": 2},
        {"vehiculo_id": "V02", "pedido_id": "P003", "secuencia": 1},
    ])
    assert respects_intravehicle(asign)


def test_intravehiculo_rechaza_duplicado():
    """Un pedido en dos vehiculos rompe la regla intravehiculo."""
    asign = pd.DataFrame([
        {"vehiculo_id": "V01", "pedido_id": "P001", "secuencia": 1},
        {"vehiculo_id": "V02", "pedido_id": "P001", "secuencia": 1},
    ])
    assert not respects_intravehicle(asign)


def test_overlap_minutes():
    # 09:00-12:00 contra 10:00-11:00 = 60 min
    assert overlap_minutes(540, 720, 600, 660) == 60
    # Sin solapamiento
    assert overlap_minutes(540, 600, 660, 720) == 0
