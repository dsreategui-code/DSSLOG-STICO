"""Auditoria FASE 3 - simulacion, incidencias y bitacora."""
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from services.validation_service import run_validation, label_escenario, ESCENARIOS_DEFAULT
from simulation.sim_engine import simular_escenarios, simular_jornada, _DEMORA_POR_INCIDENCIA
from views import validation_simulation, supervisor_simulation


ROOT = Path(__file__).resolve().parent.parent


def _src(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


# ============================================================
# Punto 1 - Simulacion en Validacion con barra de progreso por escenario
# ============================================================

def test_etiquetas_escenarios_son_las_pedidas():
    nombres = {e["id"]: e["nombre"] for e in ESCENARIOS_DEFAULT}
    assert nombres["sin_dss"] == "Operacion sin DSS"
    assert nombres["solo_ruta"] == "DSS parcial"
    assert nombres["dss_completo"] == "DSS completo"
    assert label_escenario("sin_dss") == "Operacion sin DSS"
    assert label_escenario("solo_ruta") == "DSS parcial"
    assert label_escenario("dss_completo") == "DSS completo"


def test_run_validation_acepta_progress_callback(dataset_min):
    sig = inspect.signature(run_validation)
    assert "progress_callback" in sig.parameters


def test_simular_escenarios_invoca_callback_con_start_progress_done(dataset_min):
    """El callback debe recibir start, varios progress y un done por escenario."""
    eventos = []

    def cb(esc, it, total, status):
        eventos.append((esc, it, total, status))

    cfg = {
        "escenarios_activos": ["sin_dss", "dss_completo"],
        "semilla": 1, "factor_incidencias": 0.0,
        "usar_motor_cortex": False,   # ruta rapida (v1): este test valida el CALLBACK, no el motor
    }
    simular_escenarios(dataset_min, cfg, iteraciones=2, progress_callback=cb)

    # Para cada escenario debe haber al menos 1 start y 1 done
    for esc in ("sin_dss", "dss_completo"):
        statuses = [s for (e, _, _, s) in eventos if e == esc]
        assert "start" in statuses, f"Falta start en {esc}"
        assert "done" in statuses, f"Falta done en {esc}"
        assert sum(1 for s in statuses if s == "progress") >= 1


def test_validation_simulation_no_renderiza_kpi_row():
    """La vista de simulacion no debe importar ni invocar kpi_row."""
    src = _src("views/validation_simulation.py")
    assert "kpi_row" not in src, "validation_simulation no debe mostrar KPI cards"


def test_validation_simulation_renderiza_progreso_por_escenario():
    src = _src("views/validation_simulation.py")
    assert "Progreso por escenario" in src
    # Debe definir slots por escenario y un callback _on_progress
    assert "progress_slots" in src
    assert "_on_progress" in src
    # Tres estados visibles
    assert "Pendiente" in src
    assert "En ejecucion" in src
    assert "Completado" in src
    # Llama a run_validation con progress_callback
    assert "progress_callback=" in src


# ============================================================
# Punto 2 - Incidencias generan tiempo perdido, sin aprobacion, registradas
# ============================================================

def test_catalogo_incidencias_cubre_los_7_tipos_pedidos():
    """El motor debe conocer demoras para los 7 nombres operativos."""
    requeridos = [
        "zona_dificil_acceso",
        "cliente_no_encontrado",
        "demora_estacionamiento",
        "congestion_inesperada",
        "restriccion_acceso",
        "demora_instalacion",
        "direccion_incompleta",
    ]
    for tipo in requeridos:
        assert tipo in _DEMORA_POR_INCIDENCIA, f"Falta demora para {tipo}"
        lo, hi = _DEMORA_POR_INCIDENCIA[tipo]
        assert 0 < lo < hi, f"Rango invalido para {tipo}: ({lo}, {hi})"


def test_dataset_sintetico_usa_catalogo_v2():
    """El dataset regenerado debe usar los 7 nombres operativos pedidos."""
    df = pd.read_csv(ROOT / "data" / "datasets" /
                     "dataset_demo_callao_80pedidos" /
                     "probabilidades_incidencias.csv")
    tipos = set(df["incidencia"])
    esperados = {
        "zona_dificil_acceso", "cliente_no_encontrado", "demora_estacionamiento",
        "congestion_inesperada", "restriccion_acceso", "demora_instalacion",
        "direccion_incompleta",
    }
    assert esperados.issubset(tipos), \
        f"Faltan tipos en el dataset: {esperados - tipos}"


def test_incidencias_aplican_tiempo_perdido_sin_aprobacion():
    """Con probabilidad alta debe haber incidencias y el tiempo de operacion debe crecer."""
    pedidos = pd.DataFrame([
        {"pedido_id": f"P{i:03d}", "cliente": "X", "distrito": "Callao",
         "zona": "Callao / Oeste", "latitud": -12.06, "longitud": -77.12,
         "modelo": "C", "peso_kg": 22, "tipo_servicio": "Estandar",
         "tiempo_servicio_min": 8, "ventana_inicio": "09:00", "ventana_fin": "18:00"}
        for i in range(10)
    ])
    vehiculos = pd.DataFrame([
        {"vehiculo_id": "V01", "placa": "X", "capacidad_unidades": 15,
         "capacidad_kg": 600, "zona_preferente": "Callao / Oeste", "conductor": "X"}
    ])
    probs_altas = pd.DataFrame([
        {"incidencia": "congestion_inesperada", "probabilidad": 0.9},
        {"incidencia": "demora_estacionamiento", "probabilidad": 0.9},
        {"incidencia": "direccion_incompleta", "probabilidad": 0.9},
    ])
    probs_nulas = pd.DataFrame([
        {"incidencia": "congestion_inesperada", "probabilidad": 0.0},
    ])
    perfiles = pd.DataFrame(
        [{"franja_inicio": "09:00", "franja_fin": "19:00", "multiplicador": 1.0}]
    )

    ds_sin = {"pedidos": pedidos, "vehiculos": vehiculos,
              "perfiles_trafico": perfiles, "probabilidades_incidencias": probs_nulas}
    ds_con = {"pedidos": pedidos, "vehiculos": vehiculos,
              "perfiles_trafico": perfiles, "probabilidades_incidencias": probs_altas}

    r_sin = simular_jornada(ds_sin, configuracion={"semilla": 5},
                            replanifica=False, aprobacion_automatica=False, seed=5)
    r_con = simular_jornada(ds_con, configuracion={"semilla": 5},
                            replanifica=False, aprobacion_automatica=False, seed=5)

    # Con incidencias debe haber al menos una entrega con campo 'incidencia' poblado
    inc = r_con["entregas"]["incidencia"]
    reales = inc[~inc.isin(["", "jornada_terminada"])]
    assert len(reales) > 0, "Se esperaban incidencias con probabilidades altas"
    # Y los eventos deben incluir filas tipo 'incidencia'
    eventos = r_con["eventos"]
    assert (eventos["tipo"] == "incidencia").sum() > 0
    # El tiempo total debe ser mayor con incidencias
    assert r_con["entregas"]["tiempo_op_min"].max() >= r_sin["entregas"]["tiempo_op_min"].max()


# ============================================================
# Punto 3 - Bitacora en Supervisor
# ============================================================

def test_supervisor_simulation_expone_helper_build_bitacora():
    assert hasattr(supervisor_simulation, "_build_bitacora")


def test_supervisor_simulation_no_renderiza_kpi_row():
    src = _src("views/supervisor_simulation.py")
    assert "kpi_row" not in src, \
        "supervisor_simulation no debe mostrar KPI cards de resumen"


def test_build_bitacora_tiene_todas_las_columnas_requeridas(dataset_min):
    res = simular_jornada(dataset_min, configuracion={"semilla": 9},
                          replanifica=True, aprobacion_automatica=False, seed=9)
    bit = supervisor_simulation._build_bitacora(res)
    assert not bit.empty, "La bitacora no debe estar vacia tras simular"
    columnas_requeridas = {
        "hora", "vehiculo", "pedido", "tipo_evento", "descripcion",
        "impacto_min", "estado", "genero_alerta", "genero_replanificacion",
    }
    assert columnas_requeridas.issubset(set(bit.columns)), \
        f"Faltan columnas: {columnas_requeridas - set(bit.columns)}"


def test_build_bitacora_marca_impacto_solo_en_incidencias():
    """impacto_min debe ser > 0 unicamente en filas de tipo Incidencia."""
    pedidos = pd.DataFrame([
        {"pedido_id": "P001", "cliente": "X", "distrito": "Callao",
         "zona": "Callao / Oeste", "latitud": -12.06, "longitud": -77.12,
         "modelo": "C", "peso_kg": 22, "tipo_servicio": "Estandar",
         "tiempo_servicio_min": 8, "ventana_inicio": "09:00", "ventana_fin": "18:00"},
    ])
    vehiculos = pd.DataFrame([
        {"vehiculo_id": "V01", "placa": "X", "capacidad_unidades": 5,
         "capacidad_kg": 500, "zona_preferente": "Callao / Oeste", "conductor": "X"},
    ])
    probs = pd.DataFrame([
        {"incidencia": "congestion_inesperada", "probabilidad": 1.0},
    ])
    perfiles = pd.DataFrame(
        [{"franja_inicio": "09:00", "franja_fin": "19:00", "multiplicador": 1.0}]
    )
    ds = {"pedidos": pedidos, "vehiculos": vehiculos,
          "perfiles_trafico": perfiles, "probabilidades_incidencias": probs}

    res = simular_jornada(ds, configuracion={"semilla": 11},
                          replanifica=False, aprobacion_automatica=False, seed=11)
    bit = supervisor_simulation._build_bitacora(res)
    incidencias = bit[bit["tipo_evento"] == "Incidencia"]
    otros = bit[bit["tipo_evento"] != "Incidencia"]
    assert (incidencias["impacto_min"] > 0).all(), \
        "Las incidencias deben registrar impacto > 0"
    assert (otros["impacto_min"] == 0).all(), \
        "Filas que no son incidencia deben tener impacto 0"


def test_build_bitacora_marca_flags_alerta_y_replan(dataset_min):
    """Si hay alertas y replanificaciones, los flags deben encenderse en sus filas."""
    res = simular_jornada(dataset_min, configuracion={"semilla": 42},
                          replanifica=True, aprobacion_automatica=True, seed=42)
    bit = supervisor_simulation._build_bitacora(res)
    # Los flags solo deben ser True en sus respectivas filas
    flag_a = bit["genero_alerta"]
    tipos_a = set(bit.loc[flag_a, "tipo_evento"].unique())
    if len(tipos_a) > 0:
        assert tipos_a == {"Alerta de riesgo"}
    flag_r = bit["genero_replanificacion"]
    tipos_r = set(bit.loc[flag_r, "tipo_evento"].unique())
    if len(tipos_r) > 0:
        assert tipos_r == {"Replanificacion"}


def test_supervisor_simulation_registra_incidencias_en_bitacora_de_sesion():
    """El log_bitacora del view debe incluir conteo de incidencias."""
    src = _src("views/supervisor_simulation.py")
    assert "n_incidencias" in src
    assert 'log_bitacora(' in src
    assert "incidencias" in src
