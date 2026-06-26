"""Pruebas minimas del modo benchmark ALM RRC.

Cubren:
  - el DSS actual sigue corriendo (imports + optimizador del DSS);
  - el adaptador convierte una ruta ALM al caso interno;
  - el optimizador produce una secuencia valida (permutacion de las paradas);
  - las metricas se calculan de forma coherente;
  - el runner exporta resultados sin errores;
  - si el cache esta preparado, una ruta real se ejecuta de extremo a extremo.

Los tests del nucleo usan datos sinteticos y NO requieren el cache de 9.5 GB.
"""
import pandas as pd
import pytest

from benchmark import paths, alm_loader, adapter, optimizer_adapter, metrics, runner


# ---------------------------------------------------------------------------
# 1) El DSS actual sigue corriendo (no se rompio nada).
# ---------------------------------------------------------------------------

def test_dss_optimizer_intacto(pedidos_min, vehiculos_min):
    from optimization.route_optimizer import construir_rutas_iniciales
    rutas = construir_rutas_iniciales(pedidos_min, vehiculos_min, motor="greedy")
    asignados = sum(len(r.secuencia) for r in rutas.values())
    assert asignados == len(pedidos_min)


def test_app_importa_con_benchmark():
    import importlib
    import app as app_mod
    importlib.reload(app_mod)
    from utils.constants import VISTA_BENCHMARK
    assert VISTA_BENCHMARK in app_mod.ROUTES


# ---------------------------------------------------------------------------
# Caso sintetico minimo (3 paradas + depot) para el nucleo del benchmark.
# ---------------------------------------------------------------------------

@pytest.fixture
def ruta_alm_sintetica():
    """Imita la salida de alm_loader.cargar_ruta para una ruta de 3 paradas."""
    meta = {
        "route_id": "RouteID_test", "station_code": "TST",
        "station_stop_id": "D", "station_lat": -12.0, "station_lng": -77.0,
        "date": "2018-07-27", "departure_time_utc": "16:00:00",
        "route_score": "High", "total_paradas": 3,
    }
    pedidos = pd.DataFrame([
        {"pedido_id": "A", "actual_sequence": 1, "latitud": -12.01, "longitud": -77.01,
         "type": "Dropoff", "zona": "Z1", "tiempo_servicio_total_min": 2.0,
         "ventana_inicio_utc": "", "ventana_fin_utc": ""},
        {"pedido_id": "B", "actual_sequence": 2, "latitud": -12.02, "longitud": -77.02,
         "type": "Dropoff", "zona": "Z1", "tiempo_servicio_total_min": 3.0,
         "ventana_inicio_utc": "", "ventana_fin_utc": ""},
        {"pedido_id": "C", "actual_sequence": 3, "latitud": -12.03, "longitud": -77.03,
         "type": "Dropoff", "zona": "Z2", "tiempo_servicio_total_min": 1.0,
         "ventana_inicio_utc": "", "ventana_fin_utc": ""},
    ])
    # Matriz real: D-A-B-C casi lineal; D->C es largo.
    pares = {
        ("D", "A"): 5, ("D", "B"): 10, ("D", "C"): 30,
        ("A", "B"): 4, ("A", "C"): 12, ("A", "D"): 5,
        ("B", "C"): 4, ("B", "A"): 4, ("B", "D"): 10,
        ("C", "A"): 12, ("C", "B"): 4, ("C", "D"): 30,
        ("A", "A"): 0, ("B", "B"): 0, ("C", "C"): 0, ("D", "D"): 0,
    }
    filas = [{"origen_stop_id": o, "destino_stop_id": d, "tiempo_viaje_min": t}
             for (o, d), t in pares.items()]
    matriz = pd.DataFrame(filas)
    return {"meta": meta, "pedidos": pedidos, "matriz": matriz}


def test_adapter_construye_caso(ruta_alm_sintetica):
    caso = adapter.construir_caso(ruta_alm_sintetica)
    assert caso.depot_stop_id == "D"
    assert caso.n_paradas == 3
    assert caso.secuencia_real == ["A", "B", "C"]
    assert caso.tiempo("D", "A") == 5
    assert caso.servicio_min["B"] == 3.0
    # Zona capturada para SDzone.
    assert caso.zonas["A"] == "Z1" and caso.zonas["C"] == "Z2"
    assert caso.zonas[caso.depot_stop_id] == "DEPOT"


def test_optimizer_devuelve_permutacion_valida(ruta_alm_sintetica):
    caso = adapter.construir_caso(ruta_alm_sintetica)
    res = optimizer_adapter.optimizar_secuencia(caso, motor="auto", time_limit_seconds=3)
    prop = res["secuencia_propuesta"]
    assert sorted(prop) == sorted(caso.stops_entrega)
    assert res["status"] == "ok"


def test_greedy_funciona_sin_ortools(ruta_alm_sintetica):
    caso = adapter.construir_caso(ruta_alm_sintetica)
    res = optimizer_adapter.optimizar_secuencia(caso, motor="greedy")
    # Greedy desde D por tiempo: D->A(5) -> A->B(4) -> B->C(4) = A,B,C
    assert res["secuencia_propuesta"] == ["A", "B", "C"]
    assert res["motor_usado"] == "greedy"


def test_tiempo_total(ruta_alm_sintetica):
    caso = adapter.construir_caso(ruta_alm_sintetica)
    # Tiempo real D->A->B->C con servicio = 5+2 +4+3 +4+1 = 19
    assert metrics.tiempo_total(caso.secuencia_real, caso) == pytest.approx(19.0)


def test_sd_stop_oficial(ruta_alm_sintetica):
    caso = adapter.construir_caso(ruta_alm_sintetica)
    # Misma secuencia que la real => SDstop = 0.
    assert metrics.sd_stop(caso, ["A", "B", "C"]) == pytest.approx(0.0)
    # Orden inverso => SDstop > 0 (maxima desviacion).
    sd_inv = metrics.sd_stop(caso, ["C", "B", "A"])
    assert sd_inv is not None and sd_inv > 0


def test_sd_zone():
    """SDzone con 4 zonas. Nota: la SD oficial es 0 ante inversion total (preserva
    adyacencias); se usa una permutacion que rompe adyacencias para verificar > 0."""
    pedidos = pd.DataFrame([
        {"pedido_id": "A", "actual_sequence": 1, "latitud": -12.01, "longitud": -77.01,
         "type": "Dropoff", "zona": "Z1", "tiempo_servicio_total_min": 1.0},
        {"pedido_id": "B", "actual_sequence": 2, "latitud": -12.02, "longitud": -77.02,
         "type": "Dropoff", "zona": "Z2", "tiempo_servicio_total_min": 1.0},
        {"pedido_id": "C", "actual_sequence": 3, "latitud": -12.03, "longitud": -77.03,
         "type": "Dropoff", "zona": "Z3", "tiempo_servicio_total_min": 1.0},
        {"pedido_id": "E", "actual_sequence": 4, "latitud": -12.04, "longitud": -77.04,
         "type": "Dropoff", "zona": "Z4", "tiempo_servicio_total_min": 1.0},
    ])
    nodos = ["D", "A", "B", "C", "E"]
    matriz = pd.DataFrame([{"origen_stop_id": o, "destino_stop_id": d,
                            "tiempo_viaje_min": 0 if o == d else 5}
                           for o in nodos for d in nodos])
    meta = {"route_id": "R4", "station_code": "S", "station_stop_id": "D",
            "station_lat": -12.0, "station_lng": -77.0, "date": "2018-07-27",
            "departure_time_utc": "16:00:00", "route_score": "High", "total_paradas": 4}
    caso = adapter.construir_caso({"meta": meta, "pedidos": pedidos, "matriz": matriz})
    # Mismo orden de zonas => SDzone = 0.
    assert metrics.sd_zone(caso, ["A", "B", "C", "E"]) == pytest.approx(0.0)
    # Permutacion que rompe adyacencias de zonas (Z1,Z3,Z2,Z4) => SDzone > 0.
    sdz = metrics.sd_zone(caso, ["A", "C", "B", "E"])
    assert sdz is not None and sdz > 0


def test_erp_ratio_cero_si_identica(ruta_alm_sintetica):
    caso = adapter.construir_caso(ruta_alm_sintetica)
    # Secuencia identica: ERP empareja todo con costo 0 => ERPratio = 0.
    assert metrics.erp_ratio(caso, ["A", "B", "C"]) == pytest.approx(0.0)
    # Secuencia distinta: ERPratio >= 0 y finito.
    er = metrics.erp_ratio(caso, ["C", "A", "B"])
    assert er is not None and er >= 0


def test_evaluar_ruta_fila_consolidada(ruta_alm_sintetica):
    caso = adapter.construir_caso(ruta_alm_sintetica)
    res = optimizer_adapter.optimizar_secuencia(caso, motor="greedy")
    fila = metrics.evaluar_ruta(caso, res)
    for col in ("route_id", "n_paradas", "tiempo_real_min", "tiempo_propuesto_min",
                "brecha_pct", "sd_stop", "sd_zone", "erp_ratio_min",
                "score_aprox", "status"):
        assert col in fila
    assert fila["n_paradas"] == 3
    assert fila["status"] == "ok"
    # Greedy reproduce A,B,C => SDstop 0 y score_aprox 0.
    assert fila["sd_stop"] == pytest.approx(0.0)
    assert fila["score_aprox"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 5) El runner exporta resultados sin errores (df sintetico).
# ---------------------------------------------------------------------------

def test_runner_exporta(tmp_path, monkeypatch, ruta_alm_sintetica):
    caso = adapter.construir_caso(ruta_alm_sintetica)
    res = optimizer_adapter.optimizar_secuencia(caso, motor="greedy")
    df = pd.DataFrame([metrics.evaluar_ruta(caso, res)])
    monkeypatch.setattr(runner, "OUTPUTS_DIR", tmp_path)
    out = runner.exportar_resultados(df, prefijo="test_bench")
    assert out["csv"].exists()
    assert out["resumen"]["rutas_evaluadas"] == 1


# ---------------------------------------------------------------------------
# 6) Ruta real de extremo a extremo (solo si el cache esta preparado).
# ---------------------------------------------------------------------------

def test_indice_solo_high_si_hay_cache():
    if not alm_loader.cache_listo():
        pytest.skip("Cache de benchmark no preparado.")
    idx = alm_loader.cargar_indice(solo_high=True)
    if "route_score" in idx.columns and not idx.empty:
        scores = set(idx["route_score"].astype(str).str.lower().unique())
        assert scores <= {"high"}, f"El benchmark principal debe ser solo High; vi: {scores}"


def test_ruta_real_end_to_end_si_hay_cache():
    if not alm_loader.cache_listo():
        pytest.skip("Cache de benchmark no preparado (python -m benchmark.prepare_cache).")
    ids = alm_loader.listar_route_ids()
    if not ids:
        pytest.skip("Cache sin rutas High.")
    rid = ids[0]
    data = alm_loader.cargar_ruta(rid)
    caso = adapter.construir_caso(data)
    res = optimizer_adapter.optimizar_secuencia(caso, motor="auto", time_limit_seconds=5)
    fila = metrics.evaluar_ruta(caso, res)
    assert sorted(res["secuencia_propuesta"]) == sorted(caso.stops_entrega)
    assert fila["tiempo_real_min"] > 0
    assert fila["status"] == "ok"
