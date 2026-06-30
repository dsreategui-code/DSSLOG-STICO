"""Pruebas de la matriz contextual: aplicacion multiplicativa, trazabilidad y contexto."""
import numpy as np

from core.contextual_matrix import (construir_matriz_contextual, construir_nodos,
                                     factores_por_nodo, resolver_franja)
from core.data_models import (EventoCalendario, FranjaTrafico, Hub, Incidencia, Pedido,
                              Zona)


def _setup():
    hub = Hub("HUB", "Almacen", "Callao", -12.05, -77.12)
    pedidos = [
        Pedido("P1", "C1", "Miraflores", -12.12, -77.03, "09:00", "12:00"),
        Pedido("P2", "C2", "SJL", -11.98, -76.99, "09:00", "12:00", requiere_instalacion=True),
    ]
    zonas = [
        Zona("Callao", "Oeste", 1.0, 1.0, 1.0),
        Zona("Miraflores", "CentroSur", factor_acceso=1.2, factor_estacionamiento=1.1, factor_seguridad=1.0),
        Zona("SJL", "Este", factor_acceso=1.3, factor_estacionamiento=1.0, factor_seguridad=1.4),
    ]
    trafico = [FranjaTrafico("", "manana", "08:00", "11:00", 1.5)]
    nodos = construir_nodos(hub, pedidos)
    return hub, pedidos, zonas, trafico, nodos


def test_hub_factor_unitario():
    _, _, zonas, trafico, nodos = _setup()
    f = factores_por_nodo(nodos, zonas, trafico, hora_ref="09:00").set_index("idx")
    assert f.loc[0, "f_total"] == 1.0


def test_factores_multiplicativos_trazables():
    _, _, zonas, trafico, nodos = _setup()
    f = factores_por_nodo(nodos, zonas, trafico, hora_ref="09:30").set_index("idx")
    # Miraflores: f_zona = 1.2*1.1=1.32 ; f_trafico=1.5 ; resto 1.0
    assert abs(f.loc[1, "f_zona"] - 1.32) < 1e-6
    assert abs(f.loc[1, "f_trafico"] - 1.5) < 1e-6
    assert abs(f.loc[1, "f_total"] - 1.32 * 1.5) < 1e-6
    # SJL requiere_instalacion -> f_servicio 1.15 ; f_seguridad 1.4
    assert abs(f.loc[2, "f_servicio"] - 1.15) < 1e-6
    assert abs(f.loc[2, "f_seguridad"] - 1.4) < 1e-6


def test_fuera_de_franja_sin_factor_trafico():
    _, _, zonas, trafico, nodos = _setup()
    f = factores_por_nodo(nodos, zonas, trafico, hora_ref="15:00").set_index("idx")
    assert f.loc[1, "f_trafico"] == 1.0   # 15:00 fuera de 08:00-11:00


def test_evento_global_infla_todos_los_clientes():
    _, _, zonas, trafico, nodos = _setup()
    ev = [EventoCalendario("2026-12-24", "navidad", "campana", factor_trafico=1.4,
                           zonas_afectadas="todas")]
    f = factores_por_nodo(nodos, zonas, trafico, eventos=ev, fecha="2026-12-24",
                          hora_ref="15:00").set_index("idx")
    assert abs(f.loc[1, "f_evento"] - 1.4) < 1e-6
    assert abs(f.loc[2, "f_evento"] - 1.4) < 1e-6
    assert f.loc[0, "f_evento"] == 1.0    # el hub no


def test_incidencia_activa_solo_afecta_su_zona():
    _, _, zonas, trafico, nodos = _setup()
    inc = [Incidencia("I1", "bloqueo", distrito="SJL", impacto_tiempo=1.5)]
    f = factores_por_nodo(nodos, zonas, trafico, incidencias_activas=inc,
                          hora_ref="15:00").set_index("idx")
    assert abs(f.loc[2, "f_incidencia"] - 1.5) < 1e-6   # SJL
    assert f.loc[1, "f_incidencia"] == 1.0              # Miraflores no


def test_matriz_aplica_factor_destino_y_diagonal_cero():
    _, _, zonas, trafico, nodos = _setup()
    base = np.array([[0., 10., 20.], [10., 0., 15.], [20., 15., 0.]])
    res = construir_matriz_contextual(base, nodos, zonas, trafico, hora_ref="09:30")
    f = res["factores"].set_index("idx")["f_total"]
    # columna 1 (Miraflores) escalada por su f_total
    assert abs(res["matriz"][0, 1] - 10. * f.loc[1]) < 1e-3
    assert abs(res["matriz"][2, 1] - 15. * f.loc[1]) < 1e-3
    assert np.allclose(np.diag(res["matriz"]), 0.0)


def test_resolver_franja():
    trafico = [FranjaTrafico("", "manana", "08:00", "11:00", 1.5),
               FranjaTrafico("", "tarde", "16:00", "20:00", 1.8)]
    assert resolver_franja("09:00", trafico).franja == "manana"
    assert resolver_franja("17:00", trafico).franja == "tarde"
    assert resolver_franja("13:00", trafico) is None
