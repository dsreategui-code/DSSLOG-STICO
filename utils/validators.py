"""Validadores del dataset y de coherencia de datos."""
from pathlib import Path
import pandas as pd
from utils.constants import DATASET_FILES
from config.settings import DEMO_DATASET_DIR, NUM_PEDIDOS, NUM_VEHICULOS

REQUIRED_COLS = {
    "pedidos": [
        "pedido_id", "cliente", "distrito", "zona",
        "latitud", "longitud", "modelo", "peso_kg",
        "tipo_servicio", "tiempo_servicio_min",
        "ventana_inicio", "ventana_fin",
    ],
    "vehiculos": [
        "vehiculo_id", "placa", "capacidad_unidades", "capacidad_kg",
        "zona_preferente", "conductor",
    ],
    "almacen": ["nombre", "distrito", "latitud", "longitud"],
    "zonas_operativas": ["zona", "centro_lat", "centro_lon"],
    "matriz_tiempos_base": ["origen", "destino", "tiempo_min", "distancia_km"],
    "perfiles_trafico": ["franja_inicio", "franja_fin", "multiplicador"],
    "tiempos_servicio": ["tipo_servicio", "tiempo_base_min"],
    "probabilidades_incidencias": ["incidencia", "probabilidad"],
    "asignacion_inicial_referencial": ["vehiculo_id", "pedido_id", "secuencia"],
}


class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_info(self, msg: str):
        self.info.append(msg)


def validate_dataset_dir(path: Path = None) -> ValidationResult:
    """Valida que existan todos los archivos requeridos."""
    result = ValidationResult()
    path = Path(path) if path else DEMO_DATASET_DIR

    if not path.exists():
        result.add_error(f"La carpeta del dataset no existe: {path}")
        return result

    for f in DATASET_FILES:
        if not (path / f).exists():
            result.add_error(f"Falta archivo: {f}")

    if result.ok:
        result.add_info(f"Se encontraron {len(DATASET_FILES)} archivos del dataset.")
    return result


def validate_dataframes(dataset: dict) -> ValidationResult:
    """Valida la estructura y contenido de los dataframes cargados."""
    result = ValidationResult()
    if not dataset:
        result.add_error("Dataset vacio.")
        return result

    for key, cols in REQUIRED_COLS.items():
        df = dataset.get(key)
        if df is None:
            result.add_error(f"Falta dataframe: {key}")
            continue
        missing = [c for c in cols if c not in df.columns]
        if missing:
            result.add_error(f"Columnas faltantes en {key}: {', '.join(missing)}")

    pedidos = dataset.get("pedidos")
    vehiculos = dataset.get("vehiculos")
    almacen = dataset.get("almacen")
    incidencias = dataset.get("probabilidades_incidencias")
    tiempos_serv = dataset.get("tiempos_servicio")

    # Cantidades esperadas
    if pedidos is not None and len(pedidos) != NUM_PEDIDOS:
        result.add_warning(f"Se esperaban {NUM_PEDIDOS} pedidos, hay {len(pedidos)}.")
    if vehiculos is not None and len(vehiculos) != NUM_VEHICULOS:
        result.add_warning(f"Se esperaban {NUM_VEHICULOS} vehiculos, hay {len(vehiculos)}.")

    # Coordenadas plausibles de Lima Metropolitana
    if pedidos is not None and {"latitud", "longitud"}.issubset(pedidos.columns):
        try:
            if not pd.to_numeric(pedidos["latitud"], errors="coerce").between(-13.5, -11.0).all():
                result.add_error("Hay latitudes fuera del rango plausible de Lima.")
            if not pd.to_numeric(pedidos["longitud"], errors="coerce").between(-77.5, -76.5).all():
                result.add_error("Hay longitudes fuera del rango plausible de Lima.")
        except Exception:
            result.add_error("No se pudieron interpretar las coordenadas.")

    # Ventanas horarias HH:MM
    if pedidos is not None and {"ventana_inicio", "ventana_fin"}.issubset(pedidos.columns):
        try:
            ok = (
                pedidos["ventana_inicio"].astype(str).str.match(r"^\d{2}:\d{2}$").all()
                and pedidos["ventana_fin"].astype(str).str.match(r"^\d{2}:\d{2}$").all()
            )
            if not ok:
                result.add_error("Formato de ventana horaria invalido (esperado HH:MM).")
        except Exception:
            result.add_error("No se pudo validar el formato de ventanas horarias.")

    # Productos colchon
    if pedidos is not None and "modelo" in pedidos.columns:
        if pedidos["modelo"].isnull().any():
            result.add_error("Hay pedidos sin modelo de colchon.")

    # Probabilidades en [0,1]
    if incidencias is not None and "probabilidad" in incidencias.columns:
        try:
            if not pd.to_numeric(incidencias["probabilidad"], errors="coerce").between(0, 1).all():
                result.add_error("Hay probabilidades fuera del rango [0,1].")
        except Exception:
            result.add_error("Probabilidades no numericas.")

    # Tiempos positivos
    if tiempos_serv is not None and "tiempo_base_min" in tiempos_serv.columns:
        if (pd.to_numeric(tiempos_serv["tiempo_base_min"], errors="coerce") <= 0).any():
            result.add_error("Hay tiempos de servicio base no positivos.")
    if pedidos is not None and "tiempo_servicio_min" in pedidos.columns:
        if (pd.to_numeric(pedidos["tiempo_servicio_min"], errors="coerce") <= 0).any():
            result.add_error("Hay tiempos de servicio no positivos en pedidos.")

    # Almacen presente
    if almacen is not None and len(almacen) == 0:
        result.add_error("Almacen no definido.")

    # Coherencia replanificacion intravehiculo en la asignacion inicial
    asign = dataset.get("asignacion_inicial_referencial")
    if asign is not None and pedidos is not None:
        pedidos_asignados = set(asign["pedido_id"].unique())
        pedidos_totales = set(pedidos["pedido_id"].unique())
        faltantes = pedidos_totales - pedidos_asignados
        duplicados = asign["pedido_id"].duplicated().sum()
        if faltantes:
            result.add_warning(f"Hay {len(faltantes)} pedidos sin asignacion inicial.")
        if duplicados:
            result.add_error(f"Hay {duplicados} pedidos asignados a mas de un vehiculo (rompe la regla intravehiculo).")

    if result.ok:
        result.add_info("Validacion estructural superada.")
    return result
