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
from core.data_models import (EventoCalendario, FranjaTrafico, Hub, Incidencia, Parametros,
                              Pedido, PerfilDecision, TiempoServicio, Vehiculo, Zona,
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

    df_t = _leer("factores_trafico.csv", carpeta)
    trafico = [FranjaTrafico.desde_fila(r) for _, r in df_t.iterrows()] if df_t is not None else []
    if df_t is None:
        avisos.append("factores_trafico.csv no encontrado: sin ajuste por franja.")

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

    # Tiempos de servicio: del dataset (tiempos_servicio) si existe, mapeados.
    tiempos_servicio: List[TiempoServicio] = []
    if "tiempos_servicio" in ds:
        for _, r in ds["tiempos_servicio"].iterrows():
            tiempos_servicio.append(TiempoServicio.desde_fila(r))

    return {
        "hub": hub, "pedidos": pedidos, "vehiculos": vehiculos, "zonas": zonas,
        "trafico": trafico, "eventos": eventos, "incidencias": incidencias,
        "perfiles": perfiles, "parametros": parametros,
        "tiempos_servicio": tiempos_servicio, "avisos": avisos,
    }
