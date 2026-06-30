"""Pruebas del recomendador explicable (utilidad DSS)."""
from core.recommender import recomendar


def _kpis(otd, riesgo, dist, p90=10, otif=None, cob=1.0, tmax=300):
    return {"cobertura": cob, "otd": otd, "otif": otif if otif is not None else otd,
            "tardanza_p90_min": p90, "pedidos_en_riesgo": riesgo,
            "distancia_km": dist, "tiempo_max_min": tmax}


def test_no_recomienda_solo_por_menor_distancia():
    # 'eficiente' es la mas barata pero con peor OTD y mas riesgo; debe perder.
    evals = [
        {"perfil": "eficiente", "kpis": _kpis(otd=0.85, riesgo=6, dist=100, p90=40)},
        {"perfil": "puntual", "kpis": _kpis(otd=0.97, riesgo=1, dist=112, p90=8)},
    ]
    r = recomendar(evals)
    assert r["recomendada"] == "puntual"
    assert "OTD" in r["explicacion"] or "riesgo" in r["explicacion"]


def test_empate_en_calidad_prefiere_menor_costo():
    evals = [
        {"perfil": "A", "kpis": _kpis(otd=0.95, riesgo=2, dist=120)},
        {"perfil": "B", "kpis": _kpis(otd=0.95, riesgo=2, dist=100)},   # mismo servicio, mas barata
    ]
    r = recomendar(evals)
    assert r["recomendada"] == "B"


def test_penaliza_cobertura_incompleta():
    evals = [
        {"perfil": "completa", "kpis": _kpis(otd=0.90, riesgo=3, dist=130, cob=1.0)},
        {"perfil": "parcial", "kpis": _kpis(otd=0.99, riesgo=0, dist=90, cob=0.7)},
    ]
    r = recomendar(evals)
    assert r["recomendada"] == "completa"


def test_ranking_y_explicacion_presentes():
    evals = [
        {"perfil": "eficiente", "kpis": _kpis(0.88, 5, 100)},
        {"perfil": "robusta", "kpis": _kpis(0.96, 1, 110)},
        {"perfil": "balanceada", "kpis": _kpis(0.93, 3, 105)},
    ]
    r = recomendar(evals)
    assert list(r["ranking"]["rank"]) == [1, 2, 3]
    assert isinstance(r["explicacion"], str) and len(r["explicacion"]) > 10
    assert r["ranking"].iloc[0]["utilidad"] >= r["ranking"].iloc[1]["utilidad"]
