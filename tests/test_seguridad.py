"""Peligrosidad por HORA y DISTRITO: curva horaria de seguridad (modula el factor por distrito
en la matriz contextual) y agendamiento de distritos peligrosos DE DIA en el optimizador."""
import numpy as np

from core.contextual_matrix import curva_seguridad, factores_por_nodo
from core.data_models import FranjaSeguridad, Parametros, PerfilDecision, Zona
from core.optimizer_ortools import ModeloNumerico, resolver_cvrptw


def _curva():
    return [
        FranjaSeguridad("todas", "manana", "06:00", "12:00", 1.00),
        FranjaSeguridad("todas", "tarde", "15:00", "18:00", 1.10),
        FranjaSeguridad("todas", "noche", "18:00", "23:59", 1.30),
        FranjaSeguridad("Norte", "noche", "18:00", "23:59", 1.55),
    ]


def test_curva_seguridad_global_y_override_por_macrozona():
    seg = _curva()
    assert curva_seguridad("10:00", seg) == 1.00           # global manana
    assert curva_seguridad("19:00", seg) == 1.30           # global noche
    assert curva_seguridad("19:00", seg, "Norte") == 1.55  # override del norte de noche
    assert curva_seguridad("19:00", seg, "Sur") == 1.30    # sin override -> global
    assert curva_seguridad("10:00", None) == 1.0           # sin curva -> neutro


def test_factor_seguridad_por_nodo_sube_de_noche():
    zonas = [Zona(distrito="Comas", macrozona="Norte", factor_seguridad=1.25)]
    nodos = construir_nodos_stub("Comas")
    dia = factores_por_nodo(nodos, zonas, [], seguridad_horaria=_curva(), hora_ref="10:00")
    noche = factores_por_nodo(nodos, zonas, [], seguridad_horaria=_curva(), hora_ref="19:00")
    f_dia = float(dia[dia["idx"] == 1]["f_seguridad"].iloc[0])
    f_noche = float(noche[noche["idx"] == 1]["f_seguridad"].iloc[0])
    assert abs(f_dia - 1.25) < 1e-6                         # 1.25 (distrito) x 1.00 (dia)
    assert f_noche > f_dia                                  # de noche pesa mas (x1.55 Norte)


def construir_nodos_stub(distrito):
    return [
        {"idx": 0, "distrito": "Callao", "tipo_pedido": "hub",
         "requiere_instalacion": False, "es_hub": True},
        {"idx": 1, "distrito": distrito, "tipo_pedido": "Estandar",
         "requiere_instalacion": False, "es_hub": False},
    ]


def _modelo_seg(peligro3=1.5):
    t = np.array([[0, 10, 20, 30], [10, 0, 10, 20], [20, 10, 0, 10], [30, 20, 10, 0]], float)
    return ModeloNumerico(
        tiempo_min=t, dist_km=t * 0.4, demanda_m3=[0, 1, 1, 1], demanda_kg=[0, 10, 10, 10],
        ventanas_min=[(0, 600)] * 4, servicio_min=[0, 10, 10, 10],
        pedido_ids=["HUB", "P1", "P2", "P3"], num_vehiculos=1, cap_m3=[100], cap_kg=[100],
        vehiculo_ids=["V1"], horizonte_min=600, peligrosidad=[1.0, 1.0, 1.0, peligro3],
        hora_riesgo_min=40.0)


def _eta_p3(res):
    rc = list(res["rutas"].values())[0]
    return next(s.eta_min for s in rc.secuencia if s.pedido_id == "P3")


def test_optimizador_agenda_zona_peligrosa_de_dia():
    perfil = PerfilDecision("eficiente", w_tiempo=1.0, w_tardanza=0.4, w_riesgo=0.3)

    def _corre(seg_on):
        par = Parametros(tiempo_solver_seg=3, usar_alns=False, usar_seguridad_horaria=seg_on,
                         hora_riesgo_seguridad="17:00", umbral_peligrosidad=1.15, penal_seguridad=1.5)
        return resolver_cvrptw(_modelo_seg(), perfil, par)

    r_off, r_on = _corre(False), _corre(True)
    # P3 (peligroso y el mas lejano) sin seguridad se sirve tarde; con seguridad, antes de la
    # hora de riesgo (40 min).
    assert _eta_p3(r_off) > 40.0
    assert _eta_p3(r_on) <= 40.0
    # sigue sirviendo a todos.
    assert {s.pedido_id for s in list(r_on["rutas"].values())[0].secuencia} == {"P1", "P2", "P3"}


def test_sin_peligrosidad_no_cambia_el_plan():
    # Modelo sin peligrosidad (lista vacia) => la seguridad no aplica aunque este activada.
    m = _modelo_seg()
    m.peligrosidad = []
    perfil = PerfilDecision("eficiente", w_tiempo=1.0, w_tardanza=0.4, w_riesgo=0.3)
    par = Parametros(tiempo_solver_seg=3, usar_alns=False, usar_seguridad_horaria=True)
    r = resolver_cvrptw(m, perfil, par)
    assert _eta_p3(r) > 40.0                                # sin dato de peligrosidad, P3 va tarde
