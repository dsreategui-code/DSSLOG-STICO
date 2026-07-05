"""Criminalidad real -> factor de seguridad por distrito. Conector CSV (INEI/Mininter) con
respaldo al factor sintetico de zonas.csv."""
from services.criminalidad import factores_desde_criminalidad
from services.cortex_loader import cargar_contexto


def test_conversor_normaliza_seguro_a_peligroso():
    idx = {"SafeTown": 10.0, "MidTown": 50.0, "DangerTown": 90.0}
    f = factores_desde_criminalidad(idx, f_min=1.0, f_max=1.5)
    assert f["SafeTown"] == 1.0                       # el mas seguro -> f_min
    assert f["DangerTown"] == 1.5                      # el mas peligroso -> f_max
    assert f["SafeTown"] < f["MidTown"] < f["DangerTown"]   # monotono


def test_conversor_todos_iguales_devuelve_medio():
    f = factores_desde_criminalidad({"A": 30.0, "B": 30.0}, f_min=1.0, f_max=1.5)
    assert f["A"] == f["B"] == 1.25


def test_conversor_vacio():
    assert factores_desde_criminalidad({}) == {}


def test_loader_aplica_criminalidad_real():
    ctx = cargar_contexto()
    seg = {z.distrito: z.factor_seguridad for z in ctx["zonas"]}
    # Con criminalidad.csv, SJL (indice alto) debe ser mas peligroso que San Isidro (bajo).
    assert seg["San Juan de Lurigancho"] > seg["San Isidro"]
    assert 1.0 <= seg["San Isidro"] <= seg["San Juan de Lurigancho"] <= 1.5
    assert any("criminalidad" in a for a in ctx["avisos"])
