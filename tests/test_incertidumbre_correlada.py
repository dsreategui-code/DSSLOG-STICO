"""Punto 2: incertidumbre correlacionada (factor sistemico del dia) y tiempos dependientes
de la hora (TD-VRP) en la simulacion de riesgo."""
import numpy as np

from core.risk_engine import otd_por_escenario
from core.simulator_simpy import ContextoSim, _td_mult, montecarlo
from core.uncertainty import ConfigIncertidumbre, conjunto_ambiguedad, perfil_td_franjas


def _ctx(sigma_sistemico):
    n = 6
    t = np.full((n, n), 15.0)
    np.fill_diagonal(t, 0)
    return ContextoSim(
        tiempo_min=t, rutas={"V1": [0, 1, 2, 3], "V2": [0, 4, 5]},
        ventana_ini=[0.0] * n, ventana_fin=[0, 20, 40, 60, 25, 45],
        serv_min=[8.0] * n, serv_moda=[8.0] * n, serv_max=[8.0] * n,
        pedido_ids=["HUB", "P1", "P2", "P3", "P4", "P5"],
        sigma_viaje=0.25, sigma_sistemico=sigma_sistemico)


def test_correlacion_aumenta_variabilidad_del_otd():
    # Con el factor sistemico del dia (correlacionado) la variabilidad NO se promedia:
    # la desviacion estandar del OTD entre corridas debe ser MAYOR que con ruido independiente.
    m_indep = montecarlo(_ctx(0.0), iteraciones=300, semilla_base=1)
    m_corr = montecarlo(_ctx(0.20), iteraciones=300, semilla_base=1)
    std_indep = float(otd_por_escenario(m_indep).std())
    std_corr = float(otd_por_escenario(m_corr).std())
    assert std_corr > std_indep


def test_configs_dro_tienen_sigma_sistemico_creciente():
    amb = conjunto_ambiguedad("medio")
    nombres = {c.nombre: c.sigma_sistemico for c in amb}
    assert nombres["nominal"] > 0
    assert nombres["dia_critico"] > nombres["nominal"]     # dia peor = mas variabilidad sistemica


def test_perfil_td_relativo_a_hora_ref():
    from core.data_models import FranjaTrafico

    def _fr(hi, hf, fac):
        return FranjaTrafico(macrozona="todas", franja="", hora_inicio=hi, hora_fin=hf,
                             factor_trafico=fac)
    trafico = [_fr("09:00", "12:00", 1.2), _fr("12:00", "15:00", 1.0),
               _fr("17:00", "19:00", 1.8)]
    franjas = perfil_td_franjas(trafico, jornada_inicio="09:00", hora_ref="09:00")
    # La franja que contiene hora_ref (09:00, factor 1.2) tiene multiplicador 1.0 (referencia).
    assert any(abs(m - 1.0) < 1e-6 and ini <= 0 <= fin for ini, fin, m in franjas)
    # La tarde (17-19, factor 1.8) es mas lenta que la referencia: mult = 1.8/1.2 = 1.5.
    tarde = [m for ini, fin, m in franjas if ini >= 480]
    assert tarde and abs(tarde[0] - 1.5) < 1e-6
    # Lookup por minuto: 17:30 (t=510) usa el multiplicador de la tarde.
    assert abs(_td_mult(franjas, 510) - 1.5) < 1e-6
