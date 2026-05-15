"""Tipos de evento y helpers para el motor de simulacion."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Evento:
    """Evento atomico generado durante la simulacion."""
    timestamp_min: int
    tipo: str            # 'salida', 'llegada', 'inicio_servicio', 'fin_servicio',
                         # 'incidencia', 'alerta_riesgo', 'replanificacion'
    vehiculo_id: str
    pedido_id: Optional[str] = None
    detalle: str = ""
    severidad: str = "info"   # info / warning / danger
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp_min": self.timestamp_min,
            "tipo": self.tipo,
            "vehiculo_id": self.vehiculo_id,
            "pedido_id": self.pedido_id,
            "detalle": self.detalle,
            "severidad": self.severidad,
            **self.metadata,
        }


def evento_salida(min_t: int, vehiculo_id: str) -> Evento:
    return Evento(min_t, "salida", vehiculo_id,
                  detalle=f"{vehiculo_id} sale del almacen.", severidad="info")


def evento_llegada(min_t: int, vehiculo_id: str, pedido_id: str) -> Evento:
    return Evento(min_t, "llegada", vehiculo_id, pedido_id,
                  detalle=f"{vehiculo_id} llega a {pedido_id}.")


def evento_inicio_servicio(min_t: int, vehiculo_id: str, pedido_id: str) -> Evento:
    return Evento(min_t, "inicio_servicio", vehiculo_id, pedido_id,
                  detalle=f"Inicio de servicio en {pedido_id}.")


def evento_fin_servicio(min_t: int, vehiculo_id: str, pedido_id: str,
                        estado: str) -> Evento:
    sev = "info" if estado == "A tiempo" else (
        "warning" if estado in ("Fuera de ventana", "En riesgo") else "danger"
    )
    return Evento(min_t, "fin_servicio", vehiculo_id, pedido_id,
                  detalle=f"Entrega {pedido_id}: {estado}.",
                  severidad=sev, metadata={"estado": estado})


def evento_incidencia(min_t: int, vehiculo_id: str, pedido_id: str,
                      tipo_inc: str, demora_min: float) -> Evento:
    return Evento(min_t, "incidencia", vehiculo_id, pedido_id,
                  detalle=f"Incidencia {tipo_inc} (+{demora_min:.0f} min).",
                  severidad="warning",
                  metadata={"tipo_incidencia": tipo_inc, "demora_min": demora_min})


def evento_alerta_riesgo(min_t: int, vehiculo_id: str, motivo: str) -> Evento:
    return Evento(min_t, "alerta_riesgo", vehiculo_id,
                  detalle=motivo, severidad="warning")


def evento_replanificacion(min_t: int, vehiculo_id: str, motivo: str,
                           pedidos_afectados: list) -> Evento:
    return Evento(min_t, "replanificacion", vehiculo_id,
                  detalle=motivo, severidad="info",
                  metadata={"pedidos_afectados": pedidos_afectados})
