"""Auditoria FASE 1 - verifica que los 5 puntos del requerimiento se cumplan."""
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from components import navigation
from simulation.sim_engine import simular_jornada


ROOT = Path(__file__).resolve().parent.parent


def _src(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


# ============================================================
# Punto 1 - Boton global Inicio
# ============================================================

def test_navigation_expone_render_global_actions():
    assert hasattr(navigation, "render_global_actions"), \
        "Falta render_global_actions en components.navigation"


def test_app_invoca_render_global_actions():
    src = _src("app.py")
    assert "render_global_actions" in src, "app.py no llama render_global_actions"
    assert "from components.navigation import render_global_actions" in src


def test_render_global_actions_no_se_dibuja_en_home():
    """Inspecciona el codigo: la funcion debe salir temprano cuando vista=HOME."""
    src = inspect.getsource(navigation.render_global_actions)
    assert "VISTA_HOME" in src
    assert "VISTA_DEMO_ROLE_SELECTION" in src


# ============================================================
# Punto 2 - Boton cambiar de rol conserva contexto
# ============================================================

def test_back_to_role_selection_conserva_dataset_y_resultados():
    src = inspect.getsource(navigation.back_to_role_selection)
    # No debe haber asignaciones que vacien rutas/resultados
    for clave in ("rutas_iniciales", "rutas_finales", "resultados",
                  "dataset", "configuracion", "alertas"):
        assert f'st.session_state.{clave} =' not in src and f'"{clave}"' not in src, \
            f"back_to_role_selection no debe modificar {clave}"
    # Si debe limpiar el rol
    assert "rol = None" in src


def test_render_global_actions_muestra_cambiar_rol_solo_en_demostracion():
    src = inspect.getsource(navigation.render_global_actions)
    assert "MODO_DEMOSTRACION" in src
    assert "Cambiar de rol" in src


# ============================================================
# Punto 3 - Validacion sin motor visible
# ============================================================

def test_validation_config_no_expone_motor_ni_velocidad():
    src = _src("views/validation_config.py")
    # Motor no debe estar en widgets
    assert "st.radio" not in src or "motor" not in src.lower().split("st.radio")[1][:200], \
        "Validacion no debe exponer selector de motor"
    # Velocidad no debe estar como slider
    assert "st.slider(\n            \"Velocidad" not in src, \
        "Validacion no debe exponer slider de velocidad"
    # aprob_auto no debe ser toggle visible
    assert 'st.toggle(\n            "Aprobar replanificaciones' not in src
    # Motor forzado a auto
    assert '_MOTOR_OPTIMIZACION = "auto"' in src or '"motor_optimizacion": "auto"' in src


def test_validation_config_mantiene_los_4_controles_requeridos():
    src = _src("views/validation_config.py")
    assert "Iteraciones Monte Carlo" in src
    assert "Umbral de riesgo" in src
    assert "Semilla" in src
    assert "Escenarios a comparar" in src


# ============================================================
# Punto 4 - Velocidad sigue conectada en motor
# ============================================================

def test_velocidad_kmh_sigue_afectando_los_calculos(dataset_min):
    """Si la velocidad cambia, los tiempos de VIAJE deben cambiar.

    Nota: medimos tiempo_viaje_min y no tiempo_op_min porque tras la espera
    por ventana horaria, el reloj operativo puede saturarse cuando se llega
    antes de la ventana. La velocidad afecta directa y solo el tiempo de viaje.
    """
    cfg_lento = {"velocidad_kmh": 10.0, "semilla": 7}
    cfg_rapido = {"velocidad_kmh": 30.0, "semilla": 7}
    res_lento = simular_jornada(dataset_min, configuracion=cfg_lento,
                                replanifica=False, aprobacion_automatica=False, seed=7)
    res_rapido = simular_jornada(dataset_min, configuracion=cfg_rapido,
                                 replanifica=False, aprobacion_automatica=False, seed=7)
    t_lento = res_lento["entregas"]["tiempo_viaje_min"].sum()
    t_rapido = res_rapido["entregas"]["tiempo_viaje_min"].sum()
    assert t_lento > t_rapido, \
        f"Velocidad no afecta tiempo de viaje: lento={t_lento}, rapido={t_rapido}"


# ============================================================
# Punto 5 - Supervisor: replan siempre activa + aprobacion manual
# ============================================================

def test_supervisor_config_no_expone_toggles_replan_ni_motor():
    src = _src("views/supervisor_config.py")
    # Verifica que no hay widgets (st.toggle / st.radio / st.slider) con esos labels
    assert 'st.toggle(\n            "Activar replanificacion' not in src, \
        "Supervisor no debe tener toggle para desactivar la replanificacion"
    assert 'st.toggle(\n            "Aprobar replanificaciones automaticamente' not in src, \
        "Supervisor no debe tener toggle para aprobacion automatica"
    assert 'st.radio(\n            "Motor de optimizacion' not in src, \
        "Supervisor no debe tener radio para elegir motor"
    assert 'st.slider(\n            "Velocidad urbana' not in src, \
        "Supervisor no debe tener slider de velocidad"


def test_supervisor_config_expone_los_6_controles_requeridos():
    src = _src("views/supervisor_config.py")
    assert "Escenario operativo" in src
    assert "Intensidad de trafico" in src
    assert "Variabilidad de tiempos de servicio" in src
    assert "Probabilidad de incidencias" in src
    assert "Umbral de riesgo" in src
    assert "Semilla" in src


def test_supervisor_simulation_fuerza_replan_y_aprobacion_manual():
    src = _src("views/supervisor_simulation.py")
    # Busca la llamada a simular_jornada con replanifica=True y aprobacion_automatica=False
    pat = re.search(
        r"simular_jornada\([^)]*?replanifica=True[^)]*?aprobacion_automatica=False",
        src, re.DOTALL,
    )
    assert pat is not None, \
        "supervisor_simulation.py debe pasar replanifica=True y aprobacion_automatica=False"


def test_supervisor_routes_fuerza_motor_auto():
    src = _src("views/supervisor_routes.py")
    assert 'motor="auto"' in src or "motor='auto'" in src, \
        "supervisor_routes.py debe forzar motor='auto' (OR-Tools con respaldo)"


# ============================================================
# Punto 5 (bis) - Factores realmente afectan la simulacion
# ============================================================

def test_factor_trafico_aumenta_tiempos(dataset_min):
    """factor_trafico=2.0 debe dar tiempos de VIAJE mayores que 1.0.

    Como la velocidad, el factor de trafico afecta el tiempo de viaje
    (multiplicador) y no necesariamente el tiempo total de operacion cuando
    hay esperas por ventana horaria que absorben el incremento.
    """
    base = {"semilla": 5, "factor_trafico": 1.0}
    alto = {"semilla": 5, "factor_trafico": 2.0}
    r_base = simular_jornada(dataset_min, configuracion=base,
                             replanifica=False, aprobacion_automatica=False, seed=5)
    r_alto = simular_jornada(dataset_min, configuracion=alto,
                             replanifica=False, aprobacion_automatica=False, seed=5)
    assert r_alto["entregas"]["tiempo_viaje_min"].sum() > \
           r_base["entregas"]["tiempo_viaje_min"].sum()


def test_factor_incidencias_cero_evita_incidencias():
    """factor_incidencias=0 debe anular todas las incidencias."""
    import random
    # Probabilidades altas para forzar incidencias en el escenario base
    pedidos = pd.DataFrame([
        {"pedido_id": f"P{i:03d}", "cliente": "X", "distrito": "Callao",
         "zona": "Callao / Oeste", "latitud": -12.06, "longitud": -77.12,
         "modelo": "C", "peso_kg": 22, "tipo_servicio": "Estandar",
         "tiempo_servicio_min": 8, "ventana_inicio": "09:00", "ventana_fin": "12:00"}
        for i in range(5)
    ])
    vehiculos = pd.DataFrame([
        {"vehiculo_id": "V01", "placa": "X", "capacidad_unidades": 10,
         "capacidad_kg": 500, "zona_preferente": "Callao / Oeste", "conductor": "X"}
    ])
    probs_altas = pd.DataFrame([
        {"incidencia": "trafico_severo", "probabilidad": 0.9},
        {"incidencia": "cliente_ausente", "probabilidad": 0.9},
    ])
    ds = {
        "pedidos": pedidos, "vehiculos": vehiculos,
        "perfiles_trafico": pd.DataFrame(
            [{"franja_inicio": "09:00", "franja_fin": "19:00", "multiplicador": 1.0}]
        ),
        "probabilidades_incidencias": probs_altas,
    }
    cfg_cero = {"factor_incidencias": 0.0, "semilla": 3}
    res = simular_jornada(ds, configuracion=cfg_cero,
                          replanifica=False, aprobacion_automatica=False, seed=3)
    incidencias = res["entregas"]["incidencia"]
    # Pueden quedar valores vacios "" o "jornada_terminada" pero nunca incidencias reales
    incidencias_reales = incidencias[~incidencias.isin(["", "jornada_terminada"])]
    assert len(incidencias_reales) == 0, \
        f"factor_incidencias=0 debe anular incidencias, vi: {list(incidencias_reales)}"


def test_factor_variabilidad_servicio_amplifica_desviacion():
    """Con muchas iteraciones, factor_variabilidad alto debe aumentar la std del tiempo de servicio."""
    pedidos = pd.DataFrame([
        {"pedido_id": f"P{i:03d}", "cliente": "X", "distrito": "Callao",
         "zona": "Callao / Oeste", "latitud": -12.06, "longitud": -77.12,
         "modelo": "C", "peso_kg": 22, "tipo_servicio": "Estandar",
         "tiempo_servicio_min": 20, "ventana_inicio": "09:00", "ventana_fin": "18:00"}
        for i in range(20)
    ])
    vehiculos = pd.DataFrame([
        {"vehiculo_id": "V01", "placa": "X", "capacidad_unidades": 30,
         "capacidad_kg": 1000, "zona_preferente": "Callao / Oeste", "conductor": "X"}
    ])
    ds = {
        "pedidos": pedidos, "vehiculos": vehiculos,
        "perfiles_trafico": pd.DataFrame(
            [{"franja_inicio": "09:00", "franja_fin": "19:00", "multiplicador": 1.0}]
        ),
        "probabilidades_incidencias": pd.DataFrame(
            [{"incidencia": "x", "probabilidad": 0.0}]
        ),
    }
    r1 = simular_jornada(ds, configuracion={"factor_variabilidad_servicio": 0.2, "semilla": 11},
                         replanifica=False, aprobacion_automatica=False, seed=11)
    r3 = simular_jornada(ds, configuracion={"factor_variabilidad_servicio": 3.0, "semilla": 11},
                         replanifica=False, aprobacion_automatica=False, seed=11)
    std_low = r1["entregas"]["tiempo_servicio_real_min"].std()
    std_high = r3["entregas"]["tiempo_servicio_real_min"].std()
    assert std_high > std_low, f"factor_variabilidad no amplifica std: low={std_low}, high={std_high}"
