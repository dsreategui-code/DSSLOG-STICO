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
    assert r_con["otd"] >= r_sin["otd"] - 1e-9         # accept-if-better: nunca empeora el OTD
    for a in acc:
        assert a["recuperadas"] >= 0
        # Objetivo lexicografico (nº de tardias, tardanza): si recupera entregas (menos
        # tardias) la tardanza total PUEDE subir (Moore difiere la mas costosa); si no
        # recupera ninguna, entonces debe bajar la tardanza.
        if a["recuperadas"] == 0:
            assert a["tard_despues_min"] <= a["tard_antes_min"]


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
    from core.uncertainty import TIPOS_INCIDENCIA
    assert inc and all(x["tipo"] in TIPOS_INCIDENCIA for x in inc)
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


def _esc_riesgo(ventana_py=560):
    """Escenario minimo SIN incidencia: PY (cerca del hub, ventana AJUSTADA) esta en la ruta
    DESPUES de PX (lejos, ventana holgada) -> PY llega tarde. Reordenar (PY primero) lo salva."""
    return {
        "hub": {"nombre": "HUB", "lat": -12.00, "lon": -77.00},
        "t_inicio_min": 540.0, "jornada_fin_min": 1140,
        "geometrias": {"V1": [[-77.00, -12.00]]},
        "rutas": {"V1": [
            {"pedido_id": "PX", "coord": (-12.20, -77.00), "eta_min": 642.0, "servicio_min": 10.0,
             "ventana_fin_min": 1200.0, "tardanza_min": 0.0, "incidencia": False,
             "incidencia_min": 0.0, "primer_intento_ok": True, "iri": 0.0, "distrito": "Lurin"},
            {"pedido_id": "PY", "coord": (-12.01, -77.00), "eta_min": 750.0, "servicio_min": 10.0,
             "ventana_fin_min": float(ventana_py), "tardanza_min": max(0.0, 750.0 - ventana_py),
             "incidencia": False, "incidencia_min": 0.0, "primer_intento_ok": True,
             "iri": 0.0, "distrito": "Callao"},
        ]},
    }


def test_reruteo_por_riesgo_de_ventana_sin_incidencia():
    props = proponer_reruteo(_esc_riesgo(ventana_py=560))
    assert len(props) == 1
    p = props[0]
    assert p["motivo"] == "riesgo de ventana"       # disparo por riesgo, no por incidencia
    assert p["ancla_idx"] == -1                       # re-planifica todo el vehiculo
    assert p["orden_propuesto"] == ["PY", "PX"]       # PY (ventana ajustada) primero
    assert p["recuperadas"] >= 1                       # recupera al menos una entrega


def test_reruteo_por_riesgo_no_empeora_y_recupera():
    esc = _esc_riesgo(ventana_py=560)
    esc_con, _ = mitigar_con_reruteo(esc)
    assert resumen_operacion(esc_con)["otd"] >= resumen_operacion(esc)["otd"]


def test_sin_riesgo_ni_incidencia_no_propone():
    # PY con ventana holgada: no hay riesgo -> no se toca un vehiculo sano.
    assert proponer_reruteo(_esc_riesgo(ventana_py=1200)) == []


def _esc_jornada():
    """Ruta larga (ventanas holgadas) cuyo span excede la jornada; reordenar por cercania
    (vecino-mas-cercano) la acorta y baja el exceso de jornada."""
    def _p(pid, lat, distrito):
        return {"pedido_id": pid, "coord": (lat, -77.00), "eta_min": 1000.0, "servicio_min": 20.0,
                "ventana_fin_min": 1400.0, "tardanza_min": 0.0, "incidencia": False,
                "incidencia_min": 0.0, "primer_intento_ok": True, "iri": 0.0, "distrito": distrito}
    return {
        "hub": {"nombre": "HUB", "lat": -12.00, "lon": -77.00}, "t_inicio_min": 540.0,
        "jornada_fin_min": 1140, "geometrias": {"V1": [[-77.00, -12.00]]},
        "rutas": {"V1": [_p("A", -12.30, "Lurin"), _p("B", -12.02, "Callao"),
                         _p("C", -12.32, "Lurin")]},
    }


def test_reruteo_por_riesgo_de_jornada():
    props = proponer_reruteo(_esc_jornada(), jornada_max=540.0)
    assert len(props) == 1
    p = props[0]
    assert p["motivo"] == "riesgo de jornada"
    assert p["jornada_propuesta_min"] < p["jornada_actual_min"]   # reduce el exceso de jornada
    assert p["tarde_propuesto"] <= p["tarde_actual"]               # sin empeorar ventanas
