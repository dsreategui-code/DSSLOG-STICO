"""Modelos de datos del dominio del motor CORTEX-LM.

Dataclasses tipadas que describen el esquema esperado de las entradas del sistema. Cada
una incluye `desde_fila` para construirse desde una fila de DataFrame de forma
RETROCOMPATIBLE: si falta un campo nuevo, se usa un valor por defecto razonable y se deja
registro (no se rompe la carga ni se inventan datos operativos criticos).

Convencion geografica del proyecto: las coordenadas del dominio se manejan como
(latitud, longitud). OSRM requiere (lon, lat); esa conversion vive en geo.osrm_client.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pandas as pd


def _f(fila, col, defecto=None):
    """Lee una columna de una fila (Series) de forma tolerante a ausencia/NaN."""
    if col in fila and pd.notna(fila[col]):
        return fila[col]
    return defecto


def _num(fila, col, defecto=0.0):
    v = _f(fila, col, None)
    try:
        return float(v) if v is not None else float(defecto)
    except (TypeError, ValueError):
        return float(defecto)


# --------------------------------------------------------------------------- #
# Nodos geograficos
# --------------------------------------------------------------------------- #
@dataclass
class Hub:
    """Nodo 0 del problema: almacen/centro de distribucion."""
    hub_id: str
    nombre: str
    distrito: str
    lat: float
    lon: float
    hora_apertura: str = "09:00"
    hora_cierre: str = "19:00"

    @property
    def coord(self) -> Tuple[float, float]:
        return (self.lat, self.lon)

    @classmethod
    def desde_fila(cls, fila) -> "Hub":
        return cls(
            hub_id=str(_f(fila, "hub_id", "HUB")),
            nombre=str(_f(fila, "nombre", _f(fila, "nombre_almacen", "Hub"))),
            distrito=str(_f(fila, "distrito", "")),
            lat=_num(fila, "lat", _num(fila, "latitud")),
            lon=_num(fila, "lon", _num(fila, "longitud")),
            hora_apertura=str(_f(fila, "hora_apertura", "09:00")),
            hora_cierre=str(_f(fila, "hora_cierre", "19:00")),
        )


@dataclass
class Pedido:
    pedido_id: str
    cliente_id: str
    distrito: str
    lat: float
    lon: float
    ventana_inicio: str
    ventana_fin: str
    volumen_m3: float = 0.0
    peso_kg: float = 0.0
    tipo_producto: str = "general"
    tipo_pedido: str = "estandar"
    requiere_instalacion: bool = False
    detalle_cliente: str = "regular"
    detalle_zona: str = ""
    prioridad: int = 3
    estado_inicial: str = "pendiente"
    direccion: str = ""
    zona: str = ""

    @property
    def coord(self) -> Tuple[float, float]:
        return (self.lat, self.lon)

    @classmethod
    def desde_fila(cls, fila) -> "Pedido":
        req = _f(fila, "requiere_instalacion", False)
        req = bool(req) if not isinstance(req, str) else req.strip().lower() in ("1", "true", "si", "sí", "x")
        return cls(
            pedido_id=str(_f(fila, "pedido_id", "")),
            cliente_id=str(_f(fila, "cliente_id", _f(fila, "cliente", ""))),
            distrito=str(_f(fila, "distrito", "")),
            lat=_num(fila, "lat", _num(fila, "latitud")),
            lon=_num(fila, "lon", _num(fila, "longitud")),
            ventana_inicio=str(_f(fila, "ventana_inicio", "09:00")),
            ventana_fin=str(_f(fila, "ventana_fin", "19:00")),
            volumen_m3=_num(fila, "volumen_m3", 0.0),
            peso_kg=_num(fila, "peso_kg", 0.0),
            tipo_producto=str(_f(fila, "tipo_producto", "general")),
            tipo_pedido=str(_f(fila, "tipo_pedido", _f(fila, "tipo_servicio", "estandar"))),
            requiere_instalacion=req,
            detalle_cliente=str(_f(fila, "detalle_cliente", "regular")),
            detalle_zona=str(_f(fila, "detalle_zona", "")),
            prioridad=int(_num(fila, "prioridad", 3)),
            estado_inicial=str(_f(fila, "estado_inicial", "pendiente")),
            direccion=str(_f(fila, "direccion", "")),
            zona=str(_f(fila, "zona", "")),
        )

    def tiene_coordenadas(self) -> bool:
        return self.lat != 0.0 and self.lon != 0.0


@dataclass
class Vehiculo:
    vehiculo_id: str
    tipo_vehiculo: str = "furgon"
    capacidad_m3: float = 0.0
    capacidad_kg: float = 0.0
    hora_inicio: str = "09:00"
    hora_fin: str = "19:00"
    lat_inicial: Optional[float] = None
    lon_inicial: Optional[float] = None
    estado_inicial: str = "disponible"

    @classmethod
    def desde_fila(cls, fila) -> "Vehiculo":
        return cls(
            vehiculo_id=str(_f(fila, "vehiculo_id", "")),
            tipo_vehiculo=str(_f(fila, "tipo_vehiculo", "furgon")),
            capacidad_m3=_num(fila, "capacidad_m3", 0.0),
            capacidad_kg=_num(fila, "capacidad_kg", 0.0),
            hora_inicio=str(_f(fila, "hora_inicio", "09:00")),
            hora_fin=str(_f(fila, "hora_fin", "19:00")),
            lat_inicial=(_num(fila, "lat_inicial") if _f(fila, "lat_inicial") is not None else None),
            lon_inicial=(_num(fila, "lon_inicial") if _f(fila, "lon_inicial") is not None else None),
            estado_inicial=str(_f(fila, "estado_inicial", "disponible")),
        )


# --------------------------------------------------------------------------- #
# Contexto urbano (Lima Metropolitana)
# --------------------------------------------------------------------------- #
@dataclass
class Zona:
    distrito: str
    macrozona: str = ""
    factor_acceso: float = 1.0
    factor_estacionamiento: float = 1.0
    factor_seguridad: float = 1.0
    tipo_zona: str = "mixta"
    observacion: str = ""

    @classmethod
    def desde_fila(cls, fila) -> "Zona":
        return cls(
            distrito=str(_f(fila, "distrito", "")),
            macrozona=str(_f(fila, "macrozona", "")),
            factor_acceso=_num(fila, "factor_acceso", 1.0),
            factor_estacionamiento=_num(fila, "factor_estacionamiento", 1.0),
            factor_seguridad=_num(fila, "factor_seguridad", 1.0),
            tipo_zona=str(_f(fila, "tipo_zona", "mixta")),
            observacion=str(_f(fila, "observacion", "")),
        )


@dataclass
class FranjaTrafico:
    macrozona: str
    franja: str
    hora_inicio: str
    hora_fin: str
    factor_trafico: float = 1.0

    @classmethod
    def desde_fila(cls, fila) -> "FranjaTrafico":
        return cls(
            macrozona=str(_f(fila, "macrozona", "")),
            franja=str(_f(fila, "franja", "")),
            hora_inicio=str(_f(fila, "hora_inicio", "00:00")),
            hora_fin=str(_f(fila, "hora_fin", "23:59")),
            factor_trafico=_num(fila, "factor_trafico", 1.0),
        )


@dataclass
class EventoCalendario:
    fecha: str
    tipo_evento: str
    descripcion: str = ""
    factor_trafico: float = 1.0
    factor_demanda: float = 1.0
    zonas_afectadas: str = ""   # lista separada por comas; "" o "todas" = global

    @classmethod
    def desde_fila(cls, fila) -> "EventoCalendario":
        return cls(
            fecha=str(_f(fila, "fecha", "")),
            tipo_evento=str(_f(fila, "tipo_evento", "")),
            descripcion=str(_f(fila, "descripcion", "")),
            factor_trafico=_num(fila, "factor_trafico", 1.0),
            factor_demanda=_num(fila, "factor_demanda", 1.0),
            zonas_afectadas=str(_f(fila, "zonas_afectadas", "")),
        )


@dataclass
class Incidencia:
    incidencia_id: str
    tipo_incidencia: str
    distrito: str = ""
    macrozona: str = ""
    franja: str = ""
    probabilidad: float = 0.0
    duracion_min: float = 0.0
    impacto_tiempo: float = 1.0   # multiplicador del tiempo de tramo afectado
    severidad: str = "media"
    activa_demo: bool = False

    @classmethod
    def desde_fila(cls, fila) -> "Incidencia":
        act = _f(fila, "activa_demo", False)
        act = bool(act) if not isinstance(act, str) else act.strip().lower() in ("1", "true", "si", "sí", "x")
        return cls(
            incidencia_id=str(_f(fila, "incidencia_id", "")),
            tipo_incidencia=str(_f(fila, "tipo_incidencia", "")),
            distrito=str(_f(fila, "distrito", "")),
            macrozona=str(_f(fila, "macrozona", "")),
            franja=str(_f(fila, "franja", "")),
            probabilidad=_num(fila, "probabilidad", 0.0),
            duracion_min=_num(fila, "duracion_min", 0.0),
            impacto_tiempo=_num(fila, "impacto_tiempo", 1.0),
            severidad=str(_f(fila, "severidad", "media")),
            activa_demo=act,
        )


@dataclass
class TiempoServicio:
    tipo_pedido: str
    detalle_cliente: str = ""
    detalle_zona: str = ""
    min: float = 5.0
    moda: float = 8.0
    max: float = 15.0

    @classmethod
    def desde_fila(cls, fila) -> "TiempoServicio":
        return cls(
            tipo_pedido=str(_f(fila, "tipo_pedido", _f(fila, "tipo_servicio", "estandar"))),
            detalle_cliente=str(_f(fila, "detalle_cliente", "")),
            detalle_zona=str(_f(fila, "detalle_zona", "")),
            min=_num(fila, "min", _num(fila, "tiempo_base_min", 5.0)),
            moda=_num(fila, "moda", _num(fila, "tiempo_base_min", 8.0)),
            max=_num(fila, "max", _num(fila, "tiempo_base_min", 15.0)),
        )


@dataclass
class PerfilDecision:
    """Perfil que pondera la funcion de costo/decision para generar rutas candidatas.

    Los pesos modulan penalizaciones REALES del optimizador y de la utilidad DSS; no son
    solo etiquetas (ver core.candidate_generator y core.recommender)."""
    perfil: str
    w_tiempo: float = 1.0
    w_tardanza: float = 1.0
    w_riesgo: float = 1.0
    w_balance: float = 0.0
    w_estabilidad: float = 0.0

    @classmethod
    def desde_fila(cls, fila) -> "PerfilDecision":
        return cls(
            perfil=str(_f(fila, "perfil", "balanceada")),
            w_tiempo=_num(fila, "w_tiempo", 1.0),
            w_tardanza=_num(fila, "w_tardanza", 1.0),
            w_riesgo=_num(fila, "w_riesgo", 1.0),
            w_balance=_num(fila, "w_balance", 0.0),
            w_estabilidad=_num(fila, "w_estabilidad", 0.0),
        )


@dataclass
class Parametros:
    """Parametros operativos del motor (de parametros.xlsx). NO hardcodear en codigo."""
    iteraciones_montecarlo: int = 100
    semilla_base: int = 42
    tiempo_solver_seg: int = 10
    espera_max_min: int = 0
    jornada_max_min: int = 600
    penalizacion_tardanza: float = 1.0
    penalizacion_riesgo: float = 1.0
    umbral_retraso_replanificar: float = 20.0
    umbral_riesgo_critico: float = 0.81
    max_replanificaciones: int = 3
    usar_osrm: bool = True
    usar_cache_osrm: bool = True
    velocidad_simulacion_demo: float = 1.0

    @classmethod
    def desde_dataframe(cls, df: pd.DataFrame) -> "Parametros":
        """Acepta un DataFrame de dos columnas (parametro, valor)."""
        d = {}
        if df is not None and {"parametro", "valor"}.issubset(df.columns):
            d = dict(zip(df["parametro"].astype(str), df["valor"]))
        base = cls()
        for campo in base.__dataclass_fields__:
            if campo in d and pd.notna(d[campo]):
                tipo = type(getattr(base, campo))
                try:
                    val = tipo(d[campo]) if tipo is not bool else str(d[campo]).strip().lower() in ("1", "true", "si", "sí", "x")
                    setattr(base, campo, val)
                except (TypeError, ValueError):
                    pass
        return base


# Catalogo de perfiles por defecto (si no existe perfiles_decision.xlsx). Editable.
PERFILES_POR_DEFECTO: List[PerfilDecision] = [
    PerfilDecision("eficiente",   w_tiempo=1.0, w_tardanza=0.4, w_riesgo=0.3, w_balance=0.0, w_estabilidad=0.0),
    PerfilDecision("puntual",     w_tiempo=0.5, w_tardanza=1.0, w_riesgo=0.7, w_balance=0.0, w_estabilidad=0.0),
    PerfilDecision("robusta",     w_tiempo=0.5, w_tardanza=0.8, w_riesgo=1.0, w_balance=0.2, w_estabilidad=0.3),
    PerfilDecision("balanceada",  w_tiempo=0.7, w_tardanza=0.7, w_riesgo=0.6, w_balance=0.3, w_estabilidad=0.2),
    PerfilDecision("estable",     w_tiempo=0.5, w_tardanza=0.6, w_riesgo=0.6, w_balance=0.3, w_estabilidad=1.0),
]
