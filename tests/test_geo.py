"""Geo/POIs: Nominatim (direccion -> coord+distrito, puerta de entrada de datos reales) y
Overpass (densidad de POIs -> factor de zona). Clientes con respaldo degradado; el loader aplica
la tabla pre-descargada pois_zona.csv."""
from services.cortex_loader import cargar_contexto
from services.nominatim_client import NominatimClient, geocodificar_direcciones
from services.overpass_client import OverpassClient, factores_zona_desde_densidad


def test_factores_zona_desde_densidad_monotono():
    f = factores_zona_desde_densidad({"Poca": 5.0, "Media": 30.0, "Mucha": 120.0})
    assert f["Poca"]["acceso"] == 1.0                      # menos POIs -> acceso mas facil (min)
    assert f["Mucha"]["acceso"] > f["Media"]["acceso"] > f["Poca"]["acceso"]
    assert f["Mucha"]["estacionamiento"] > f["Poca"]["estacionamiento"]


def test_overpass_respaldo_sin_internet(tmp_path):
    c = OverpassClient(base_url="http://127.0.0.1:9/no", cache_dir=tmp_path, timeout_s=1)
    assert c.densidad_pois(-12.05, -77.04) is None         # sin red -> None, no rompe


def test_nominatim_respaldo_sin_internet(tmp_path):
    c = NominatimClient(base_url="http://127.0.0.1:9/no", cache_dir=tmp_path,
                        timeout_s=1, pausa_s=0.0)
    assert c.geocodificar("Av. Inexistente 1, Lima") is None
    lote = geocodificar_direcciones(["Dir 1", "Dir 2"], client=c)
    assert len(lote) == 2 and all(x["ok"] is False for x in lote)   # fallos marcados para revision


def test_loader_aplica_pois_zona():
    ctx = cargar_contexto()
    acc = {z.distrito: z.factor_acceso for z in ctx["zonas"]}
    # Independencia (mas POIs) debe tener acceso mas dificil que Villa El Salvador (pocos).
    if "Independencia" in acc and "Villa El Salvador" in acc:
        assert acc["Independencia"] >= acc["Villa El Salvador"]
    assert any("pois_zona" in a for a in ctx["avisos"])
