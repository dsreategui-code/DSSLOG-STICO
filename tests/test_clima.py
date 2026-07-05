"""Factor climatico del contexto (Open-Meteo). Lima-aware: la NEBLINA (visibilidad baja) pesa
mas que la lluvia. Cliente con cache + respaldo degradado (sin red -> factor 1.0)."""
from core.contextual_matrix import factores_por_nodo
from core.data_models import Zona
from services.clima_client import ClimaClient, factor_desde_clima


def test_factor_lima_neblina_vs_despejado():
    assert factor_desde_clima(0.0, 20000) == 1.0                 # despejado -> neutro
    assert factor_desde_clima(0.0, 800) > 1.0                    # neblina cerrada -> mas lento
    # peor visibilidad => mayor factor
    assert factor_desde_clima(0.0, 800) >= factor_desde_clima(0.0, 4000) >= factor_desde_clima(0.0, 15000)
    assert factor_desde_clima(10.0, 20000) > 1.0                 # lluvia (rara) tambien sube
    assert factor_desde_clima(50.0, 500) <= 1.4                  # acotado al tope


def test_cliente_respaldo_sin_internet(tmp_path):
    # URL invalida -> sin red -> factor 1.0, fuente 'respaldo', nunca rompe.
    c = ClimaClient(base_url="http://127.0.0.1:9/noexiste", cache_dir=tmp_path, timeout_s=1)
    r = c.factor_clima("2024-07-01", -12.05, -77.04)
    assert r["factor"] == 1.0 and r["fuente"] == "respaldo"


def test_factor_clima_multiplica_la_matriz():
    nodos = [
        {"idx": 0, "distrito": "Callao", "tipo_pedido": "hub",
         "requiere_instalacion": False, "es_hub": True},
        {"idx": 1, "distrito": "Ate", "tipo_pedido": "Estandar",
         "requiere_instalacion": False, "es_hub": False},
    ]
    zonas = [Zona(distrito="Ate", macrozona="Este", factor_acceso=1.0,
                  factor_estacionamiento=1.0, factor_seguridad=1.0)]
    f1 = factores_por_nodo(nodos, zonas, [], factor_clima=1.0)
    f2 = factores_por_nodo(nodos, zonas, [], factor_clima=1.2)
    t1 = float(f1[f1["idx"] == 1]["f_total"].iloc[0])
    t2 = float(f2[f2["idx"] == 1]["f_total"].iloc[0])
    assert abs(t2 - 1.2 * t1) < 1e-6                             # el clima multiplica el f_total
    # el HUB tambien recibe el clima (afecta los retornos)
    assert abs(float(f2[f2["idx"] == 0]["f_total"].iloc[0]) - 1.2) < 1e-6
