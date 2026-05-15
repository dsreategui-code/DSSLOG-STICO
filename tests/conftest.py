"""Configuracion de pytest: agrega la raiz del proyecto al path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import random
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def pedidos_min() -> pd.DataFrame:
    """Dataset mini de 6 pedidos repartidos en 2 zonas para tests rapidos."""
    return pd.DataFrame([
        {"pedido_id": "P001", "cliente": "A", "distrito": "Callao",
         "zona": "Callao / Oeste", "latitud": -12.06, "longitud": -77.12,
         "modelo": "Comfort", "peso_kg": 22, "tipo_servicio": "Estandar",
         "tiempo_servicio_min": 10, "ventana_inicio": "09:00", "ventana_fin": "12:00"},
        {"pedido_id": "P002", "cliente": "B", "distrito": "Bellavista",
         "zona": "Callao / Oeste", "latitud": -12.05, "longitud": -77.11,
         "modelo": "Comfort", "peso_kg": 22, "tipo_servicio": "Estandar",
         "tiempo_servicio_min": 10, "ventana_inicio": "10:00", "ventana_fin": "13:00"},
        {"pedido_id": "P003", "cliente": "C", "distrito": "Bellavista",
         "zona": "Callao / Oeste", "latitud": -12.04, "longitud": -77.10,
         "modelo": "Queen", "peso_kg": 38, "tipo_servicio": "Instalacion",
         "tiempo_servicio_min": 25, "ventana_inicio": "12:00", "ventana_fin": "15:00"},
        {"pedido_id": "P004", "cliente": "D", "distrito": "San Borja",
         "zona": "Lima Moderna", "latitud": -12.10, "longitud": -77.00,
         "modelo": "Queen", "peso_kg": 38, "tipo_servicio": "Estandar",
         "tiempo_servicio_min": 8, "ventana_inicio": "10:00", "ventana_fin": "13:00"},
        {"pedido_id": "P005", "cliente": "E", "distrito": "Miraflores",
         "zona": "Lima Moderna", "latitud": -12.12, "longitud": -77.03,
         "modelo": "King", "peso_kg": 48, "tipo_servicio": "Subida a departamento",
         "tiempo_servicio_min": 18, "ventana_inicio": "14:00", "ventana_fin": "17:00"},
        {"pedido_id": "P006", "cliente": "F", "distrito": "Surco",
         "zona": "Lima Moderna", "latitud": -12.13, "longitud": -77.00,
         "modelo": "Comfort", "peso_kg": 30, "tipo_servicio": "Estandar",
         "tiempo_servicio_min": 8, "ventana_inicio": "16:00", "ventana_fin": "19:00"},
    ])


@pytest.fixture
def vehiculos_min() -> pd.DataFrame:
    """Flota minima de 2 vehiculos en zonas distintas."""
    return pd.DataFrame([
        {"vehiculo_id": "V01", "placa": "ABC-001", "capacidad_unidades": 10,
         "capacidad_kg": 500, "zona_preferente": "Callao / Oeste",
         "conductor": "Juan"},
        {"vehiculo_id": "V02", "placa": "ABC-002", "capacidad_unidades": 10,
         "capacidad_kg": 500, "zona_preferente": "Lima Moderna",
         "conductor": "Maria"},
    ])


@pytest.fixture
def perfiles_trafico() -> pd.DataFrame:
    return pd.DataFrame([
        {"franja_inicio": "09:00", "franja_fin": "13:00", "multiplicador": 1.1},
        {"franja_inicio": "13:00", "franja_fin": "17:00", "multiplicador": 1.3},
        {"franja_inicio": "17:00", "franja_fin": "19:00", "multiplicador": 1.5},
    ])


@pytest.fixture
def probabilidades_incidencias_baja() -> pd.DataFrame:
    """Probabilidades casi nulas para tests deterministas."""
    return pd.DataFrame([
        {"incidencia": "trafico_severo", "probabilidad": 0.0},
        {"incidencia": "estacionamiento_dificil", "probabilidad": 0.0},
        {"incidencia": "acceso_restringido", "probabilidad": 0.0},
        {"incidencia": "cliente_ausente", "probabilidad": 0.0},
        {"incidencia": "rechazo_entrega", "probabilidad": 0.0},
        {"incidencia": "demora_pago", "probabilidad": 0.0},
    ])


@pytest.fixture
def dataset_min(pedidos_min, vehiculos_min, perfiles_trafico,
                probabilidades_incidencias_baja) -> dict:
    """Dataset minimo simulando la estructura esperada por el motor."""
    return {
        "pedidos": pedidos_min,
        "vehiculos": vehiculos_min,
        "perfiles_trafico": perfiles_trafico,
        "probabilidades_incidencias": probabilidades_incidencias_baja,
        "tiempos_servicio": pd.DataFrame([
            {"tipo_servicio": "Estandar", "tiempo_base_min": 8},
            {"tipo_servicio": "Instalacion", "tiempo_base_min": 25},
            {"tipo_servicio": "Subida a departamento", "tiempo_base_min": 18},
        ]),
    }


@pytest.fixture(autouse=True)
def _set_seed():
    random.seed(123)
    np.random.seed(123)
