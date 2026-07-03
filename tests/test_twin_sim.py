"""Pruebas del gemelo operativo: incidencias aleatorias, alertas dinamicas y re-ruteo."""
from core.demo_scenario import construir_escenario_demo
from core.twin_sim import (agregados_incidencias, aplicar_propuestas, comparar_rutas,
                           mitigar_con_reruteo, proponer_reruteo, resumen_operacion,
                           simular_incidencias, tabla_alertas, tabla_incidencias,
                           tabla_operacion, tabla_por_camion, variabilidad_operacion)


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


def test_proponer_no_muta_y_aplicar_solo_lo_aprobado():
    esc_sin, _ = simular_incidencias(_esc(), tasa=0.22, seed=9)
    antes = [(v, [p["pedido_id"] for p in r]) for v, r in esc_sin["rutas"].items()]
    props = proponer_reruteo(esc_sin)
    # proponer no debe mutar el escenario base
    despues = [(v, [p["pedido_id"] for p in r]) for v, r in esc_sin["rutas"].items()]
    assert antes == despues
    # aplicar sin aprobaciones = escenario base (mismas ETAs)
    esc0 = aplicar_propuestas(esc_sin, props, [])
    r0 = resumen_operacion(esc0)
    rb = resumen_operacion(esc_sin)
    assert abs(r0["otd"] - rb["otd"]) < 1e-9
    # aprobar todas = mismo OTD que el atajo mitigar_con_reruteo
    if props:
        esc_all = aplicar_propuestas(esc_sin, props, [p["vehiculo_id"] for p in props])
        esc_mit, _ = mitigar_con_reruteo(esc_sin)
        assert abs(resumen_operacion(esc_all)["otd"]
                   - resumen_operacion(esc_mit)["otd"]) < 1e-9


def test_propuesta_siempre_mejora():
    esc_sin, _ = simular_incidencias(_esc(), tasa=0.25, seed=4)
    for p in proponer_reruteo(esc_sin):
        assert (p["tarde_propuesto"], p["tard_propuesto_min"]) \
            <= (p["tarde_actual"], p["tard_actual_min"])
        assert p["orden_propuesto"] != p["orden_actual"] or p["reduccion_min"] > 0


def test_otif_menor_o_igual_que_otd_y_por_pedido():
    esc, inc = simular_incidencias(_esc(), tasa=0.25, seed=6)
    r = resumen_operacion(esc, inc)
    assert 0.0 <= r["otif"] <= r["otd"] <= 1.0          # a tiempo Y completo <= a tiempo
    df = tabla_operacion(esc)
    # OTIF por pedido = a_tiempo Y primer intento; nunca True si la entrega fallo o llego tarde
    assert not (df["otif"] & (~df["a_tiempo"])).any()
    assert not (df["otif"] & (~df["primer_intento_ok"])).any()
    # fallidas de primer intento = ausencias
    ausencias = sum(1 for x in inc if x["afecta_otif"])
    assert r["fallidas_primer_intento"] == ausencias


def test_incidencias_traen_causa_tipificada():
    esc, inc = simular_incidencias(_esc(), tasa=0.3, seed=2)
    from core.twin_sim import CATALOGO_INCIDENCIAS
    tipos_validos = {c["tipo"] for c in CATALOGO_INCIDENCIAS}
    assert inc and all(x["tipo"] in tipos_validos for x in inc)
    assert all(x["severidad"] in ("baja", "media", "alta") for x in inc)
    ti = tabla_incidencias(inc)
    assert {"tipo", "descripcion", "severidad", "franja", "retraso_min"} <= set(ti.columns)
    ag = agregados_incidencias(inc)
    assert ag["impacto_total_min"] > 0 and not ag["por_tipo"].empty


def test_por_camion_coherente():
    esc, _ = simular_incidencias(_esc(), tasa=0.2, seed=4)
    tc = tabla_por_camion(esc)
    assert (tc["a_tiempo"] + tc["fuera_ventana"] == tc["pedidos"]).all()
    assert ((tc["otd"] >= 0) & (tc["otd"] <= 1)).all()
    assert ((tc["otif"] <= tc["otd"] + 1e-9)).all()
    assert (tc["distancia_km"] > 0).all()


def test_comparar_rutas_marca_cambios():
    esc_sin, _ = simular_incidencias(_esc(), tasa=0.25, seed=8)
    esc_con, _ = mitigar_con_reruteo(esc_sin)
    cmp = comparar_rutas(esc_sin, esc_con)
    assert len(cmp) == len(esc_sin["rutas"])
    # un vehiculo marcado 'cambiada' debe tener distinto orden
    for _, row in cmp[cmp["cambiada"]].iterrows():
        assert row["orden_inicial"] != row["orden_final"]


def test_variabilidad_operacion_no_negativa():
    va = variabilidad_operacion(_esc(), tasa=0.2, n_corridas=12, seed=0)
    assert va["n"] == 12
    assert va["otd_std"] >= 0.0 and 0.0 <= va["otd_medio"] <= 1.0
    assert len(va["muestras"]) == 12


def test_reruteo_conserva_todos_los_pedidos():
    esc_sin, _ = simular_incidencias(_esc(), tasa=0.25, seed=11)
    esc_con, _ = mitigar_con_reruteo(esc_sin)
    ids_sin = sorted(p["pedido_id"] for r in esc_sin["rutas"].values() for p in r)
    ids_con = sorted(p["pedido_id"] for r in esc_con["rutas"].values() for p in r)
    assert ids_sin == ids_con                          # custodia: no se pierde ni transfiere
