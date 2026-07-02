"""Pruebas del gemelo operativo: incidencias aleatorias, alertas dinamicas y re-ruteo."""
from core.demo_scenario import construir_escenario_demo
from core.twin_sim import (mitigar_con_reruteo, resumen_operacion, simular_incidencias,
                           tabla_alertas, tabla_operacion)


def _esc():
    return construir_escenario_demo(num_vehiculos=6)


def test_incidencias_reproducibles_con_semilla():
    a, ia = simular_incidencias(_esc(), tasa=0.15, seed=7)
    b, ib = simular_incidencias(_esc(), tasa=0.15, seed=7)
    assert len(ia) == len(ib)
    assert [x["pedido_id"] for x in ia] == [x["pedido_id"] for x in ib]


def test_intensidad_cero_sin_incidencias():
    _, inc = simular_incidencias(_esc(), tasa=0.0, seed=3)
    assert inc == []


def test_alertas_saltan_con_cascada():
    esc, inc = simular_incidencias(_esc(), tasa=0.2, seed=5)
    r = resumen_operacion(esc, inc)
    # con incidencias que empujan ventanas debe haber alertas y coincidir con la tabla
    assert r["incidencias"] > 0
    assert r["alertas"] > 0
    df = tabla_operacion(esc)
    assert int(df["alerta"].sum()) == r["alertas"]
    assert len(tabla_alertas(esc)) == r["alertas"]


def test_reruteo_nunca_empeora_y_puede_recuperar():
    esc_sin, inc = simular_incidencias(_esc(), tasa=0.2, seed=5)
    esc_con, acc = mitigar_con_reruteo(esc_sin)
    r_sin = resumen_operacion(esc_sin, inc)
    r_con = resumen_operacion(esc_con, inc)
    assert r_con["otd"] >= r_sin["otd"] - 1e-9         # accept-if-better: nunca empeora
    for a in acc:                                       # cada accion mejora (o iguala)
        assert a["tard_despues_min"] <= a["tard_antes_min"]
        assert a["recuperadas"] >= 0


def test_reruteo_conserva_todos_los_pedidos():
    esc_sin, _ = simular_incidencias(_esc(), tasa=0.25, seed=11)
    esc_con, _ = mitigar_con_reruteo(esc_sin)
    ids_sin = sorted(p["pedido_id"] for r in esc_sin["rutas"].values() for p in r)
    ids_con = sorted(p["pedido_id"] for r in esc_con["rutas"].values() for p in r)
    assert ids_sin == ids_con                          # custodia: no se pierde ni transfiere
