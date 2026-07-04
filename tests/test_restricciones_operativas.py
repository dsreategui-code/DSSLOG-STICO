"""Restricciones operativas del motor: jornada del conductor y cuadrillas de instalacion."""
from core.candidate_generator import _cumple_operativo, _requiere_cuadrilla
from core.optimizer_ortools import ModeloNumerico, ParadaRuta, RutaCandidata
from core.planner import planificar
from services.cortex_loader import cargar_contexto


def test_todas_las_candidatas_respetan_cuadrillas_y_jornada():
    ctx = cargar_contexto()
    par = ctx["parametros"]
    nv = len(ctx["vehiculos"])
    n_cuad = max(1, min(nv, round(par.frac_cuadrillas * nv)))
    crew = {v.vehiculo_id for v in ctx["vehiculos"][:n_cuad]}
    req = {p.pedido_id for p in ctx["pedidos"] if _requiere_cuadrilla(p)}
    res = planificar(ctx, max_pedidos=40)
    assert res["factible"]
    for e in res["evaluaciones"]:                      # incluye candidatas OR-Tools y ALNS
        for veh, rc in e["resultado"]["rutas"].items():
            # (2) cuadrillas: un pedido de instalacion solo lo atiende un vehiculo con cuadrilla
            for s in rc.secuencia:
                if s.pedido_id in req:
                    assert veh in crew, f"{veh} sin cuadrilla atendio {s.pedido_id}"
            # (1) jornada: el turno (span = fin - inicio) no excede la jornada maxima
            assert (rc.tiempo_min - rc.inicio_min) <= par.jornada_max_min + 1


def _ruta(veh, nodos, inicio=0.0, fin=100.0):
    rc = RutaCandidata(vehiculo_id=veh, inicio_min=inicio, tiempo_min=fin)
    rc.secuencia = [ParadaRuta(idx_nodo=k, pedido_id=f"P{k}", eta_min=0.0, carga_m3_acum=0.0,
                               carga_kg_acum=0.0, tardanza_min=0.0, distancia_km_acum=0.0)
                    for k in nodos]
    return rc


def _modelo(req_cuadrilla, veh_cuadrilla, veh_ids):
    import numpy as np
    n = len(req_cuadrilla)
    return ModeloNumerico(
        tiempo_min=np.zeros((n, n)), dist_km=np.zeros((n, n)),
        demanda_m3=[0.0] * n, demanda_kg=[0.0] * n, ventanas_min=[(0, 100)] * n,
        servicio_min=[0.0] * n, pedido_ids=["HUB"] + [f"P{i}" for i in range(1, n)],
        num_vehiculos=len(veh_ids), cap_m3=[0.0] * len(veh_ids), cap_kg=[0.0] * len(veh_ids),
        vehiculo_ids=veh_ids, horizonte_min=600,
        requiere_cuadrilla=req_cuadrilla, vehiculo_cuadrilla=veh_cuadrilla)


def test_cumple_operativo_detecta_violaciones():
    # nodo 2 requiere cuadrilla; V01 tiene cuadrilla, V02 no.
    modelo = _modelo([False, False, True], [True, False], ["V01", "V02"])
    ok = {"rutas": {"V01": _ruta("V01", [1, 2], fin=500)}}           # crew atiende crew-order: OK
    mal_crew = {"rutas": {"V02": _ruta("V02", [2], fin=500)}}        # no-crew atiende crew-order
    mal_jornada = {"rutas": {"V01": _ruta("V01", [1], fin=600)}}     # span 600 > 540
    assert _cumple_operativo(ok, modelo, 540) is True
    assert _cumple_operativo(mal_crew, modelo, 540) is False
    assert _cumple_operativo(mal_jornada, modelo, 540) is False
