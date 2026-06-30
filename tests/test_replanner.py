"""Pruebas de la replanificacion intra-vehiculo (horizonte limitado)."""
import numpy as np

from core.data_models import Parametros
from core.optimizer_ortools import ModeloNumerico
from core.replanner import (EstadoVehiculo, debe_replanificar, replanificar_vehiculo,
                            _cambios_secuencia)


def _modelo():
    # HUB(0), P1(1) cerca con ventana amplia, P2(2) lejos con ventana MUY estricta,
    # P3(3) intermedio. La matriz hace que el orden importe.
    t = np.array([
        [0, 10, 12, 8],
        [10, 0, 20, 6],
        [12, 20, 0, 14],
        [8, 6, 14, 0],
    ], dtype=float)
    d = t * 0.4
    return ModeloNumerico(
        tiempo_min=t, dist_km=d, demanda_m3=[0, 1, 1, 1], demanda_kg=[0, 10, 10, 10],
        ventanas_min=[(0, 600), (0, 600), (0, 30), (0, 600)],
        servicio_min=[0, 5, 5, 5], pedido_ids=["HUB", "P1", "P2", "P3"],
        num_vehiculos=1, cap_m3=[100], cap_kg=[1000], vehiculo_ids=["V1"],
        horizonte_min=600)


def test_pendientes_excluye_completadas_y_hub():
    est = EstadoVehiculo("V1", ruta_planificada=[0, 1, 2, 3], completadas=[1], pos_nodo=1,
                         t_actual_min=15)
    assert est.pendientes() == [2, 3]


def test_debe_replanificar_por_retraso_y_forzado():
    est = EstadoVehiculo("V1", [0, 1, 2, 3], completadas=[1], pos_nodo=1,
                         t_actual_min=15, retraso_acumulado_min=25)
    ok, motivos = debe_replanificar(est, Parametros(umbral_retraso_replanificar=20))
    assert ok and any("retraso" in m for m in motivos)
    ok2, _ = debe_replanificar(est, Parametros(umbral_retraso_replanificar=100), forzado=True)
    assert ok2


def test_no_replanifica_si_no_hay_motivo():
    est = EstadoVehiculo("V1", [0, 1, 2, 3], completadas=[], pos_nodo=0, t_actual_min=0,
                         retraso_acumulado_min=0)
    ok, motivos = debe_replanificar(est, Parametros(umbral_retraso_replanificar=20))
    assert not ok and motivos == []


def test_replanifica_mejora_tardanza_con_ventana_critica():
    # Ruta actual visita P2 al final -> llega tarde a su ventana estricta (cierra 30).
    # Reordenar para visitar P2 primero deberia reducir la tardanza.
    modelo = _modelo()
    est = EstadoVehiculo("V1", ruta_planificada=[0, 1, 3, 2], completadas=[], pos_nodo=0,
                         t_actual_min=0)
    r = replanificar_vehiculo(est, modelo, Parametros(tiempo_solver_seg=3))
    # La propuesta no debe tener peor tardanza que la actual.
    assert r["comparacion"]["propuesta"]["tardanza_total_min"] <= \
           r["comparacion"]["actual"]["tardanza_total_min"] + 1e-6
    assert r["recomendacion"] in ("Aceptar replanificacion", "Mantener ruta actual")
    assert isinstance(r["explicacion"], str) and len(r["explicacion"]) > 10


def test_custodia_no_introduce_nodos_ajenos():
    modelo = _modelo()
    est = EstadoVehiculo("V1", ruta_planificada=[0, 1, 3, 2], completadas=[1], pos_nodo=1,
                         t_actual_min=15)
    r = replanificar_vehiculo(est, modelo, Parametros(tiempo_solver_seg=3))
    assert set(r["secuencia_propuesta"]) == {3, 2}      # solo pendientes del propio vehiculo


def test_cambios_secuencia():
    assert _cambios_secuencia([2, 3], [2, 3]) == 0
    assert _cambios_secuencia([2, 3], [3, 2]) == 2
