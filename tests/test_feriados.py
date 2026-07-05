"""Feriados reales (Nager.Date) -> calendario de eventos. Incluye el guard de que un evento
FECHADO solo aplica al planificar para ESA fecha (con fecha=None = dia tipico, sin eventos)."""
from core.contextual_matrix import factores_por_nodo
from core.data_models import EventoCalendario, Zona
from services.feriados_client import FeriadosClient, eventos_desde_feriados


def _nodos():
    return [
        {"idx": 0, "distrito": "Callao", "tipo_pedido": "hub",
         "requiere_instalacion": False, "es_hub": True},
        {"idx": 1, "distrito": "Ate", "tipo_pedido": "Estandar",
         "requiere_instalacion": False, "es_hub": False},
    ]


def test_evento_fechado_solo_aplica_en_su_fecha():
    ev = [EventoCalendario(fecha="2026-12-24", tipo_evento="navidad",
                           factor_trafico=1.4, zonas_afectadas="todas")]
    zonas = [Zona(distrito="Ate", macrozona="Este")]
    # fecha=None -> dia tipico: el evento NO aplica (antes se apilaban todos = bug).
    f_none = factores_por_nodo(_nodos(), zonas, [], eventos=ev, fecha=None)
    assert abs(float(f_none[f_none["idx"] == 1]["f_evento"].iloc[0]) - 1.0) < 1e-6
    # fecha == la del evento -> aplica.
    f_dia = factores_por_nodo(_nodos(), zonas, [], eventos=ev, fecha="2026-12-24")
    assert abs(float(f_dia[f_dia["idx"] == 1]["f_evento"].iloc[0]) - 1.4) < 1e-6


def test_eventos_desde_feriados():
    ev = eventos_desde_feriados([{"fecha": "2026-07-28", "nombre": "Fiestas Patrias"}])
    assert len(ev) == 1
    assert ev[0].tipo_evento == "feriado"
    assert ev[0].fecha == "2026-07-28"
    assert ev[0].factor_trafico < 1.0                # dia no laborable -> menos trafico


def test_feriados_respaldo_sin_internet(tmp_path):
    c = FeriadosClient(base_url="http://127.0.0.1:9/noexiste", cache_dir=tmp_path, timeout_s=1)
    assert c.feriados(2026, "PE") == []              # sin red -> lista vacia, no rompe
