"""Carga del CONTEXTO completo para el motor CORTEX-LM.

Une el dataset operativo existente (pedidos/vehiculos/almacen) con las plantillas nuevas de
contexto (hub, zonas, factores de trafico, calendario de eventos, incidencias, perfiles de
decision, parametros). Carga RETROCOMPATIBLE: si una plantilla falta, usa valores por
defecto razonables y deja un aviso (no rompe ni inventa datos operativos criticos).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pandas as pd

from config.cortex_settings import PLANTILLAS_DIR
from core.data_models import (EventoCalendario, FranjaSeguridad, FranjaTrafico, Hub, Incidencia,
                              Parametros, Pedido, PerfilDecision, TiempoServicio, Vehiculo, Zona,
                              PERFILES_POR_DEFECTO)
from services.data_loader import load_dataset


def _leer(nombre: str, carpeta: Path) -> Optional[pd.DataFrame]:
    f = carpeta / nombre
    if f.exists():
        return pd.read_csv(f)
    return None


def cargar_contexto(plantillas_dir: Optional[Path] = None) -> dict:
    """Devuelve el contexto del dominio + lista de avisos sobre datos faltantes."""
    carpeta = Path(plantillas_dir) if plantillas_dir else PLANTILLAS_DIR
    ds = load_dataset()
    avisos: List[str] = []

    # HUB: plantilla hub.csv, o el almacen del dataset.
    df_hub = _leer("hub.csv", carpeta)
    if df_hub is not None and not df_hub.empty:
        hub = Hub.desde_fila(df_hub.iloc[0])
    else:
        hub = Hub.desde_fila(ds["almacen"].iloc[0])
        avisos.append("hub.csv no encontrado: se uso el almacen del dataset.")

    pedidos = [Pedido.desde_fila(r) for _, r in ds["pedidos"].iterrows()]
    vehiculos = [Vehiculo.desde_fila(r) for _, r in ds["vehiculos"].iterrows()]

    # Zonas (contexto urbano).
    df_z = _leer("zonas.csv", carpeta)
    if df_z is not None:
        zonas = [Zona.desde_fila(r) for _, r in df_z.iterrows()]
    else:
        distritos = {p.distrito for p in pedidos} | {hub.distrito}
        zonas = [Zona(distrito=d) for d in distritos]
        avisos.append("zonas.csv no encontrado: factores de zona neutros (1.0).")

    # Criminalidad REAL (opcional): si existe criminalidad.csv, deriva el factor_seguridad por
    # distrito desde el indice delictivo (datos INEI/Mininter). Si no, se usa el de zonas.csv.
    df_crim = _leer("criminalidad.csv", carpeta)
    if df_crim is not None and "distrito" in df_crim.columns:
        col = next((c for c in ("indice_delictivo", "denuncias_por_mil", "tasa_delitos",
                                "victimizacion", "indice") if c in df_crim.columns), None)
        if col:
            from services.criminalidad import factores_desde_criminalidad
            indices = {str(r["distrito"]): float(r[col]) for _, r in df_crim.iterrows()
                       if pd.notna(r[col])}
            factores_seg = factores_desde_criminalidad(indices)
            n_over = 0
            for z in zonas:
                if z.distrito in factores_seg:
                    z.factor_seguridad = factores_seg[z.distrito]
                    n_over += 1
            avisos.append(f"criminalidad.csv: factor_seguridad real aplicado a {n_over} distritos.")

    # POIs REALES (opcional): si existe pois_zona.csv (pre-descargado de Overpass), deriva el
    # factor de acceso/estacionamiento por distrito desde la densidad comercial. Si no, zonas.csv.
    df_pois = _leer("pois_zona.csv", carpeta)
    if df_pois is not None and {"distrito", "densidad_pois"}.issubset(df_pois.columns):
        from services.overpass_client import factores_zona_desde_densidad
        dens = {str(r["distrito"]): float(r["densidad_pois"]) for _, r in df_pois.iterrows()
                if pd.notna(r["densidad_pois"])}
        fz = factores_zona_desde_densidad(dens)
        n_pois = 0
        for z in zonas:
            if z.distrito in fz:
                z.factor_acceso = fz[z.distrito]["acceso"]
                z.factor_estacionamiento = fz[z.distrito]["estacionamiento"]
                n_pois += 1
        avisos.append(f"pois_zona.csv: F_zona real (Overpass) aplicado a {n_pois} distritos.")

    df_t = _leer("factores_trafico.csv", carpeta)
    trafico = [FranjaTrafico.desde_fila(r) for _, r in df_t.iterrows()] if df_t is not None else []
    if df_t is None:
        avisos.append("factores_trafico.csv no encontrado: sin ajuste por franja.")

    # Trafico REAL (opcional): si existe trafico_real.csv (pre-descargado de TomTom por macrozona),
    # sus filas se ANTEPONEN (ganan por macrozona en resolver_franja); la tabla sintetica global
    # queda como respaldo para las macrozonas sin dato real.
    df_tr = _leer("trafico_real.csv", carpeta)
    if df_tr is not None and {"macrozona", "franja", "factor_trafico"}.issubset(df_tr.columns):
        reales = [FranjaTrafico.desde_fila(r) for _, r in df_tr.iterrows()]
        trafico = reales + trafico
        avisos.append(f"trafico_real.csv: {len(reales)} franjas reales (TomTom) con precedencia.")

    # Peligrosidad por FRANJA horaria (curva de seguridad); se combina con el factor por distrito.
    df_seg = _leer("seguridad_horaria.csv", carpeta)
    seguridad_horaria = ([FranjaSeguridad.desde_fila(r) for _, r in df_seg.iterrows()]
                         if df_seg is not None else [])
    if df_seg is None:
        avisos.append("seguridad_horaria.csv no encontrado: peligrosidad constante por distrito.")

    df_e = _leer("calendario_eventos.csv", carpeta)
    eventos = [EventoCalendario.desde_fila(r) for _, r in df_e.iterrows()] if df_e is not None else []

    df_i = _leer("incidencias.csv", carpeta)
    incidencias = [Incidencia.desde_fila(r) for _, r in df_i.iterrows()] if df_i is not None else []

    df_p = _leer("perfiles_decision.csv", carpeta)
    perfiles = ([PerfilDecision.desde_fila(r) for _, r in df_p.iterrows()]
                if df_p is not None else list(PERFILES_POR_DEFECTO))
    if df_p is None:
        avisos.append("perfiles_decision.csv no encontrado: se usaron los perfiles por defecto.")

    df_par = _leer("parametros.csv", carpeta)
    parametros = Parametros.desde_dataframe(df_par) if df_par is not None else Parametros()
    if df_par is None:
        avisos.append("parametros.csv no encontrado: se usaron parametros por defecto.")

    # Feriados REALES (Nager.Date): dia no laborable -> menos trafico de commuters. Cache-first +
    # respaldo (sin internet -> nada). Solo aplican al planificar PARA esa fecha.
    if getattr(parametros, "usar_feriados", True):
        try:
            from datetime import date as _date
            from services.feriados_client import FeriadosClient, eventos_desde_feriados
            anio = _date.today().year
            fer = FeriadosClient().feriados(anio, pais=str(getattr(parametros, "pais_feriados", "PE")))
            ev_fer = eventos_desde_feriados(fer)
            if ev_fer:
                eventos = list(eventos) + ev_fer
                avisos.append(f"Nager.Date: {len(ev_fer)} feriados {anio} anadidos al calendario.")
        except Exception:  # noqa: BLE001
            pass

    # Tiempos de servicio: del dataset (tiempos_servicio) si existe, mapeados.
    tiempos_servicio: List[TiempoServicio] = []
    if "tiempos_servicio" in ds:
        for _, r in ds["tiempos_servicio"].iterrows():
            tiempos_servicio.append(TiempoServicio.desde_fila(r))

    return {
        "hub": hub, "pedidos": pedidos, "vehiculos": vehiculos, "zonas": zonas,
        "trafico": trafico, "seguridad_horaria": seguridad_horaria, "eventos": eventos,
        "incidencias": incidencias, "perfiles": perfiles, "parametros": parametros,
        "tiempos_servicio": tiempos_servicio, "avisos": avisos,
    }
