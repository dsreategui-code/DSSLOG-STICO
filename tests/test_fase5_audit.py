"""Auditoria FASE 5 - filtros, formulas y metricas de servicio."""
import inspect
from pathlib import Path

import pandas as pd
import pytest

from components import filters as filters_mod
from components.filters import apply_filters, _APPLY_ORDER
from simulation.metrics import (
    compute_kpis, compute_otd_evolution, compute_vehicle_performance,
    compute_service_time_metrics, CV_MEAN_MIN_MIN, _safe_cv, _safe_div,
)
from utils.constants import (
    ESTADO_A_TIEMPO, ESTADO_FUERA_VENTANA, ESTADO_FALLIDA, ESTADO_PENDIENTE,
)


ROOT = Path(__file__).resolve().parent.parent


def _src(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


# ============================================================
# Punto 1 y 2 - Filtros
# ============================================================

def test_filtros_prioridad_escenario_y_vehiculo():
    """Escenario primero, vehiculo segundo, luego el resto."""
    assert _APPLY_ORDER[0][0] == "escenario"
    assert _APPLY_ORDER[1][0] == "vehiculo"
    keys_restantes = [k for k, _ in _APPLY_ORDER[2:]]
    assert "zona" in keys_restantes
    assert "tipo_servicio" in keys_restantes
    assert "estado" in keys_restantes


def test_filtros_demostracion_no_muestran_escenario():
    """supervisor_results invoca render_filters con show_escenario=False."""
    src = _src("views/supervisor_results.py")
    assert "show_escenario=False" in src


def test_filtros_validacion_muestran_escenario():
    src = _src("views/validation_results.py")
    assert "show_escenario=True" in src


def test_render_filters_acepta_labels():
    sig = inspect.signature(filters_mod.render_filters)
    assert "escenarios_labels" in sig.parameters
    assert "show_escenario" in sig.parameters


def _entregas_sintetico():
    return pd.DataFrame([
        {"pedido_id": "P1", "vehiculo_id": "V01", "zona": "Z1",
         "tipo_servicio": "Estandar", "estado": ESTADO_A_TIEMPO,
         "retraso_min": 0, "fin_servicio_min": 540, "tiempo_op_min": 540,
         "tiempo_total_min": 30, "tiempo_servicio_real_min": 10, "peso_kg": 22},
        {"pedido_id": "P2", "vehiculo_id": "V01", "zona": "Z2",
         "tipo_servicio": "Instalacion", "estado": ESTADO_FUERA_VENTANA,
         "retraso_min": 10, "fin_servicio_min": 720, "tiempo_op_min": 720,
         "tiempo_total_min": 40, "tiempo_servicio_real_min": 25, "peso_kg": 30},
        {"pedido_id": "P3", "vehiculo_id": "V02", "zona": "Z1",
         "tipo_servicio": "Estandar", "estado": ESTADO_FALLIDA,
         "retraso_min": 0, "fin_servicio_min": 780, "tiempo_op_min": 780,
         "tiempo_total_min": 35, "tiempo_servicio_real_min": 0, "peso_kg": 22},
        {"pedido_id": "P4", "vehiculo_id": "V02", "zona": "Z2",
         "tipo_servicio": "Estandar", "estado": ESTADO_A_TIEMPO,
         "retraso_min": 0, "fin_servicio_min": 600, "tiempo_op_min": 600,
         "tiempo_total_min": 28, "tiempo_servicio_real_min": 9, "peso_kg": 22},
    ])


def test_apply_filters_filtra_por_vehiculo():
    df = _entregas_sintetico()
    out = apply_filters(df, {"vehiculo": "V01"})
    assert set(out["vehiculo_id"].unique()) == {"V01"}


def test_apply_filters_combina_vehiculo_y_zona():
    df = _entregas_sintetico()
    out = apply_filters(df, {"vehiculo": "V01", "zona": "Z2"})
    assert len(out) == 1
    assert out.iloc[0]["pedido_id"] == "P2"


def test_apply_filters_combina_tipo_y_estado():
    df = _entregas_sintetico()
    out = apply_filters(df, {"tipo_servicio": "Estandar", "estado": ESTADO_A_TIEMPO})
    assert set(out["pedido_id"]) == {"P1", "P4"}


def test_apply_filters_kpis_se_recalculan_consistentemente():
    """Recalcular KPIs con un subset filtrado debe reflejar solo ese subset."""
    df = _entregas_sintetico()
    k_total = compute_kpis(df)
    sub = apply_filters(df, {"vehiculo": "V01"})
    k_sub = compute_kpis(sub)
    assert k_sub["total_pedidos"] == 2
    assert k_total["total_pedidos"] == 4
    assert k_sub["entregas_a_tiempo"] <= k_total["entregas_a_tiempo"]


def test_validation_results_recalcula_kpis_desde_filtradas():
    src = _src("views/validation_results.py")
    assert "kpis_filtrados = compute_kpis(entregas_filtradas" in src
    assert "evolucion_filtrada = compute_otd_evolution(entregas_filtradas" in src


def test_supervisor_results_recalcula_kpis_desde_filtradas():
    src = _src("views/supervisor_results.py")
    assert "kpis_filtrados = compute_kpis(entregas_filtradas" in src
    assert "evolucion_filtrada = compute_otd_evolution(entregas_filtradas" in src


# ============================================================
# Punto 3 - Formulas
# ============================================================

def test_safe_div_no_divide_por_cero():
    assert _safe_div(5, 0) == 0
    assert _safe_div(0, 0) == 0
    assert _safe_div(5, 10) == 50.0


def test_otd_y_otif_se_calculan_sobre_bases_correctas():
    df = _entregas_sintetico()  # 4 pedidos, 2 a tiempo, 1 fuera, 1 fallida, 0 pendientes
    k = compute_kpis(df)
    # OTD = a_tiempo / completadas (no pendientes)
    assert k["otd"] == pytest.approx(50.0)   # 2/4
    # OTIF = a_tiempo / total
    assert k["otif"] == pytest.approx(50.0)  # 2/4


def test_otd_excluye_pedidos_pendientes():
    """Si hay pedidos pendientes, OTD se calcula solo sobre completadas."""
    df = _entregas_sintetico()
    df = pd.concat([df, pd.DataFrame([{
        "pedido_id": "P5", "vehiculo_id": "V01", "zona": "Z1",
        "tipo_servicio": "Estandar", "estado": ESTADO_PENDIENTE,
        "retraso_min": 0, "fin_servicio_min": 1140, "tiempo_op_min": 1140,
        "tiempo_total_min": 0, "tiempo_servicio_real_min": 0, "peso_kg": 22,
    }])], ignore_index=True)
    k = compute_kpis(df)
    assert k["entregas_completadas"] == 4
    assert k["pedidos_pendientes"] == 1
    assert k["otd"] == pytest.approx(50.0)   # sigue 2/4
    assert k["otif"] == pytest.approx(40.0)  # 2/5


def test_safe_cv_devuelve_none_si_media_baja():
    """El CV no debe explotar con media < 1 min."""
    assert _safe_cv(desv=5.0, promedio=0.0) is None
    assert _safe_cv(desv=5.0, promedio=0.5) is None
    assert _safe_cv(desv=5.0, promedio=CV_MEAN_MIN_MIN - 0.01) is None


def test_safe_cv_es_aplicable_con_media_alta():
    assert _safe_cv(desv=4.0, promedio=20.0) == pytest.approx(20.0)


def test_compute_kpis_cv_no_explota_con_media_baja():
    """Regresion del bug 'CV de 400%'."""
    df = pd.DataFrame([
        {"pedido_id": f"P{i}", "vehiculo_id": "V01", "zona": "Z1",
         "tipo_servicio": "Estandar", "estado": ESTADO_A_TIEMPO,
         "retraso_min": 0.2 if i % 2 else 0.4,
         "fin_servicio_min": 540 + i * 5, "tiempo_op_min": 540,
         "tiempo_total_min": 20, "tiempo_servicio_real_min": 8, "peso_kg": 22}
        for i in range(8)
    ])
    k = compute_kpis(df)
    # Retraso promedio ~0.3 min: CV debe ser None ("No aplicable")
    assert k["coef_variacion_pct"] is None


def test_compute_kpis_cv_si_aplica_con_retrasos_relevantes():
    df = pd.DataFrame([
        {"pedido_id": f"P{i}", "vehiculo_id": "V01", "zona": "Z1",
         "tipo_servicio": "Estandar", "estado": ESTADO_FUERA_VENTANA,
         "retraso_min": 10 + i, "fin_servicio_min": 540 + i * 5,
         "tiempo_op_min": 540, "tiempo_total_min": 20,
         "tiempo_servicio_real_min": 8, "peso_kg": 22}
        for i in range(8)
    ])
    k = compute_kpis(df)
    assert k["coef_variacion_pct"] is not None
    assert 0 < k["coef_variacion_pct"] < 100, \
        f"CV fuera de rango razonable: {k['coef_variacion_pct']}"


def test_compute_kpis_no_mezcla_minutos_y_horas():
    """Todos los tiempos expuestos deben estar en minutos."""
    df = _entregas_sintetico()
    k = compute_kpis(df)
    for clave in ("tiempo_total_operacion_min", "tiempo_promedio_entrega_min",
                  "tiempo_promedio_parada_min", "retraso_promedio_min",
                  "retraso_maximo_min", "desviacion_estandar_min"):
        assert clave.endswith("_min"), f"{clave} no esta nombrado en minutos"


def test_compute_otd_evolution_no_explota_si_vacio():
    out = compute_otd_evolution(pd.DataFrame())
    assert out.empty
    assert list(out.columns) == ["tiempo_min", "hora", "otd", "completadas", "a_tiempo"]


# ============================================================
# Punto 4 - Indicadores de tiempo de servicio
# ============================================================

def test_compute_service_time_metrics_totales():
    df = _entregas_sintetico()
    m = compute_service_time_metrics(df)
    # Solo se cuentan paradas con servicio > 0 (P1, P2, P4)
    assert m["servicio_total_min"] == pytest.approx(44.0, abs=0.5)
    assert m["servicio_promedio_min"] > 0


def test_compute_service_time_metrics_por_vehiculo():
    df = _entregas_sintetico()
    m = compute_service_time_metrics(df)
    pv = m["por_vehiculo"]
    assert {"vehiculo_id", "servicio_total", "servicio_prom", "n"}.issubset(pv.columns)
    assert set(pv["vehiculo_id"]) == {"V01", "V02"}


def test_compute_service_time_metrics_por_tipo_incluye_otd():
    df = _entregas_sintetico()
    m = compute_service_time_metrics(df)
    pt = m["por_tipo"]
    assert "otd_pct" in pt.columns, "Por tipo debe incluir la relacion con OTD"
    assert {"tipo_servicio", "servicio_total", "servicio_prom",
            "n", "otd_pct"}.issubset(pt.columns)


def test_compute_service_time_metrics_pct_jornada():
    df = _entregas_sintetico()
    m = compute_service_time_metrics(df)
    assert 0 <= m["servicio_pct_jornada"] <= 100


def test_compute_service_time_metrics_vacio_no_explota():
    m = compute_service_time_metrics(pd.DataFrame())
    assert m["servicio_total_min"] == 0
    assert m["por_vehiculo"].empty
    assert m["por_tipo"].empty


def test_vehicle_performance_incluye_tiempo_servicio():
    df = _entregas_sintetico()
    veh = pd.DataFrame([
        {"vehiculo_id": "V01", "capacidad_unidades": 10, "capacidad_kg": 500},
        {"vehiculo_id": "V02", "capacidad_unidades": 10, "capacidad_kg": 500},
    ])
    perf = compute_vehicle_performance(df, veh)
    assert "tiempo_servicio_total" in perf.columns
    assert "tiempo_servicio_prom" in perf.columns


# ============================================================
# UI: CV "No aplicable"
# ============================================================

def test_kpi_dashboard_muestra_no_aplicable_cuando_cv_none():
    from dashboards.kpi_dashboard import _fmt_cv
    assert _fmt_cv(None) == "No aplicable"
    assert _fmt_cv(25.3) != "No aplicable"


def test_variability_analysis_maneja_cv_none():
    src = _src("dashboards/variability_analysis.py")
    assert "No aplicable" in src
