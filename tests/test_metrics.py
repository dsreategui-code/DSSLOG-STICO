"""Tests de calculo de indicadores."""
import pandas as pd
import pytest

from simulation.metrics import (
    compute_kpis, compute_otd_evolution, compute_vehicle_performance,
    compute_replanning_stats, aggregate_iterations,
)
from utils.constants import (
    ESTADO_A_TIEMPO, ESTADO_FUERA_VENTANA, ESTADO_FALLIDA, ESTADO_PENDIENTE,
)


def _entregas_sample() -> pd.DataFrame:
    return pd.DataFrame([
        {"pedido_id": "P1", "vehiculo_id": "V01", "zona": "Z1",
         "tipo_servicio": "Estandar", "peso_kg": 22,
         "fin_servicio_min": 540, "estado": ESTADO_A_TIEMPO,
         "retraso_min": 0, "tiempo_op_min": 540,
         "tiempo_total_min": 30, "tiempo_servicio_real_min": 10},
        {"pedido_id": "P2", "vehiculo_id": "V01", "zona": "Z1",
         "tipo_servicio": "Estandar", "peso_kg": 22,
         "fin_servicio_min": 600, "estado": ESTADO_A_TIEMPO,
         "retraso_min": 0, "tiempo_op_min": 600,
         "tiempo_total_min": 28, "tiempo_servicio_real_min": 9},
        {"pedido_id": "P3", "vehiculo_id": "V02", "zona": "Z2",
         "tipo_servicio": "Instalacion", "peso_kg": 38,
         "fin_servicio_min": 720, "estado": ESTADO_FUERA_VENTANA,
         "retraso_min": 12, "tiempo_op_min": 720,
         "tiempo_total_min": 40, "tiempo_servicio_real_min": 20},
        {"pedido_id": "P4", "vehiculo_id": "V02", "zona": "Z2",
         "tipo_servicio": "Estandar", "peso_kg": 22,
         "fin_servicio_min": 780, "estado": ESTADO_FALLIDA,
         "retraso_min": 0, "tiempo_op_min": 780,
         "tiempo_total_min": 35, "tiempo_servicio_real_min": 8},
        {"pedido_id": "P5", "vehiculo_id": "V02", "zona": "Z2",
         "tipo_servicio": "Estandar", "peso_kg": 22,
         "fin_servicio_min": 840, "estado": ESTADO_PENDIENTE,
         "retraso_min": 0, "tiempo_op_min": 840,
         "tiempo_total_min": 0, "tiempo_servicio_real_min": 0},
    ])


def test_compute_kpis_basicos():
    df = _entregas_sample()
    kpis = compute_kpis(df, alertas=[])

    assert kpis["total_pedidos"] == 5
    assert kpis["entregas_a_tiempo"] == 2
    assert kpis["entregas_fuera_ventana"] == 1
    assert kpis["entregas_fallidas"] == 1
    assert kpis["pedidos_pendientes"] == 1
    assert kpis["entregas_completadas"] == 4
    # OTD = 2/4 * 100 = 50
    assert kpis["otd"] == pytest.approx(50.0)
    # OTIF = 2/5 * 100 = 40
    assert kpis["otif"] == pytest.approx(40.0)


def test_compute_kpis_vacio():
    df = pd.DataFrame()
    assert compute_kpis(df) == {}


def test_otd_evolution_es_monotona_no_decreciente_en_aciertos():
    """En el caso sin nada que falle, OTD se mantiene en 100 todo el dia."""
    df = pd.DataFrame([
        {"pedido_id": f"P{i}", "fin_servicio_min": 540 + i * 15,
         "estado": ESTADO_A_TIEMPO, "retraso_min": 0}
        for i in range(4)
    ])
    evol = compute_otd_evolution(df, step_min=15)
    assert not evol.empty
    assert (evol["otd"] == 100.0).all()


def test_otd_evolution_se_actualiza_con_completadas():
    df = _entregas_sample()
    evol = compute_otd_evolution(df, step_min=60)
    assert not evol.empty
    # En el ultimo instante debe coincidir con OTD global
    kpis = compute_kpis(df)
    assert evol["otd"].iloc[-1] == pytest.approx(kpis["otd"], abs=0.1)


def test_vehicle_performance(vehiculos_min):
    df = _entregas_sample()
    veh = vehiculos_min.copy()
    veh.loc[len(veh)] = {"vehiculo_id": "V01", "placa": "X", "capacidad_unidades": 10,
                          "capacidad_kg": 500, "zona_preferente": "Z1", "conductor": "X"}
    # Forzar que V01 y V02 esten
    veh = pd.DataFrame([
        {"vehiculo_id": "V01", "capacidad_unidades": 10, "capacidad_kg": 500},
        {"vehiculo_id": "V02", "capacidad_unidades": 10, "capacidad_kg": 500},
    ])
    perf = compute_vehicle_performance(df, veh)
    assert set(perf["vehiculo_id"]) == {"V01", "V02"}
    fila_v01 = perf[perf["vehiculo_id"] == "V01"].iloc[0]
    assert fila_v01["otd"] == pytest.approx(100.0)
    fila_v02 = perf[perf["vehiculo_id"] == "V02"].iloc[0]
    # V02 tiene 1 a tiempo / 0 -> 0 completadas a tiempo entre 2 completadas = 0%
    assert fila_v02["otd"] == pytest.approx(0.0)


def test_replanning_stats_cuenta_correctamente():
    decisiones = [
        {"decision": "aprobada", "pedidos_recuperados": 3},
        {"decision": "aprobada", "pedidos_recuperados": 1},
        {"decision": "rechazada", "pedidos_recuperados": 0},
    ]
    stats = compute_replanning_stats(decisiones)
    assert stats["sugeridas"] == 3
    assert stats["aprobadas"] == 2
    assert stats["rechazadas"] == 1
    assert stats["pedidos_recuperados"] == 4


def test_aggregate_iterations_promedia_y_calcula_cv():
    df = pd.DataFrame([
        {"escenario": "sin_dss", "iteracion": 1, "otd": 60.0,
         "otif": 55, "retraso_promedio_min": 12, "coef_variacion_pct": 30},
        {"escenario": "sin_dss", "iteracion": 2, "otd": 70.0,
         "otif": 60, "retraso_promedio_min": 10, "coef_variacion_pct": 28},
        {"escenario": "dss_completo", "iteracion": 1, "otd": 85.0,
         "otif": 80, "retraso_promedio_min": 5, "coef_variacion_pct": 15},
        {"escenario": "dss_completo", "iteracion": 2, "otd": 88.0,
         "otif": 82, "retraso_promedio_min": 4, "coef_variacion_pct": 14},
    ])
    out = aggregate_iterations(df)
    sin_dss = out[out["escenario"] == "sin_dss"].iloc[0]
    dss = out[out["escenario"] == "dss_completo"].iloc[0]
    assert sin_dss["otd_prom"] == pytest.approx(65.0)
    assert dss["otd_prom"] == pytest.approx(86.5)
    assert dss["otd_prom"] > sin_dss["otd_prom"]
