"""Trafico real (TomTom, modo FACTORES): factor de congestion = current/freeFlow. Cliente con
resolucion de key + respaldo (sin key -> 1.0). El loader antepone las franjas reales por macrozona."""
from config.cortex_settings import PLANTILLAS_DIR
from services.cortex_loader import cargar_contexto
from services.tomtom_client import TomTomClient, factor_desde_flujo, factores_por_macrozona


def test_factor_desde_flujo():
    assert factor_desde_flujo(100, 100) == 1.0        # sin congestion
    assert factor_desde_flujo(200, 100) == 2.0        # el doble de lento
    assert factor_desde_flujo(80, 100) == 1.0         # el trafico no acelera -> clamp a 1.0
    assert factor_desde_flujo(500, 100) == 3.0        # acotado a 3.0
    assert factor_desde_flujo(100, 0) == 1.0          # sin dato de flujo libre -> 1.0


def test_sin_key_respaldo():
    c = TomTomClient(api_key="")                       # sin key -> no llama la API
    assert c.factor_trafico(-12.05, -77.04) == 1.0


def test_factores_por_macrozona_sin_key():
    c = TomTomClient(api_key="")
    f = factores_por_macrozona({"Centro": [(-12.05, -77.04)], "Norte": [(-12.0, -77.05)]}, client=c)
    assert f == {"Centro": 1.0, "Norte": 1.0}


def test_loader_antepone_trafico_real():
    # Escribe una tabla real temporal; el loader debe anteponerla (precedencia por macrozona).
    p = PLANTILLAS_DIR / "trafico_real.csv"
    p.write_text("macrozona,franja,hora_inicio,hora_fin,factor_trafico\n"
                 "Centro,tarde,16:00,20:00,1.9\n", encoding="utf-8")
    try:
        ctx = cargar_contexto()
        centro_tarde = [f for f in ctx["trafico"]
                        if f.macrozona == "Centro" and f.franja == "tarde"]
        assert centro_tarde and abs(centro_tarde[0].factor_trafico - 1.9) < 1e-6
        assert any("trafico_real" in a for a in ctx["avisos"])
    finally:
        p.unlink(missing_ok=True)
