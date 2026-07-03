"""Constantes del dominio DSS."""

# Modos
MODO_VALIDACION = "validacion"
MODO_DEMOSTRACION = "demostracion"
# Reservado para el futuro modo benchmark (SVRPBench). Sin vista activa por ahora.
MODO_BENCHMARK = "benchmark"

# Roles
ROL_SUPERVISOR = "supervisor"
ROL_CONDUCTOR = "conductor"

# Vistas
VISTA_HOME = "home"
VISTA_VALIDATION_DATA = "validation_data"
VISTA_VALIDATION_CONFIG = "validation_config"
VISTA_VALIDATION_SIMULATION = "validation_simulation"
VISTA_VALIDATION_RESULTS = "validation_results"
VISTA_VALIDATION_EXPORT = "validation_export"
VISTA_DEMO_ROLE_SELECTION = "demo_role_selection"
VISTA_SUPERVISOR_DATA = "supervisor_data"
VISTA_SUPERVISOR_CONFIG = "supervisor_config"
VISTA_SUPERVISOR_ROUTES = "supervisor_routes"
VISTA_SUPERVISOR_SIMULATION = "supervisor_simulation"
VISTA_SUPERVISOR_ALERTS = "supervisor_alerts"
VISTA_SUPERVISOR_RESULTS = "supervisor_results"
VISTA_SUPERVISOR_EXPORT = "supervisor_export"
VISTA_DRIVER = "driver_view"
# Reservado para el futuro modo benchmark (SVRPBench). Sin ruta activa por ahora.
VISTA_BENCHMARK = "benchmark"
# Gemelo digital operativo (CORTEX-LM, PyDeck).
VISTA_DIGITAL_TWIN = "digital_twin"
# Planificacion CORTEX-LM (pipeline completo).
VISTA_PLANNING = "planning"
# Flujo guiado de Demostracion (5 pasos: datos -> parametros -> motor -> gemelo -> export).
VISTA_DEMO_FLOW = "demo_flow"

# Zonas operativas
ZONAS_OPERATIVAS = [
    "Callao / Oeste",
    "Lima Centro",
    "Lima Norte",
    "Lima Sur",
    "Lima Este",
    "Lima Moderna",
]

DISTRITOS_POR_ZONA = {
    "Callao / Oeste": ["Callao", "Bellavista", "La Perla", "Carmen de la Legua", "Ventanilla"],
    "Lima Centro": ["Cercado de Lima", "Brena", "La Victoria", "Rimac", "San Luis"],
    "Lima Norte": ["Los Olivos", "San Martin de Porres", "Independencia", "Comas", "Puente Piedra"],
    "Lima Sur": ["Villa El Salvador", "Villa Maria del Triunfo", "Chorrillos", "Lurin", "San Juan de Miraflores"],
    "Lima Este": ["San Juan de Lurigancho", "Ate", "Santa Anita", "El Agustino", "La Molina"],
    "Lima Moderna": ["Miraflores", "San Isidro", "San Borja", "Surco", "Magdalena", "Jesus Maria", "Pueblo Libre", "Surquillo"],
}

# Ventanas horarias preferentes
VENTANAS_HORARIAS = [
    ("09:00", "12:00"),
    ("10:00", "13:00"),
    ("12:00", "15:00"),
    ("14:00", "17:00"),
    ("16:00", "19:00"),
]

# Tipos de servicio
TIPO_SERVICIO_ESTANDAR = "Estandar"
TIPO_SERVICIO_INSTALACION = "Instalacion"
TIPO_SERVICIO_SUBIDA = "Subida a departamento"
TIPO_SERVICIO_ESPECIAL = "Atencion especial"

TIPOS_SERVICIO = [
    TIPO_SERVICIO_ESTANDAR,
    TIPO_SERVICIO_INSTALACION,
    TIPO_SERVICIO_SUBIDA,
    TIPO_SERVICIO_ESPECIAL,
]

TIEMPO_SERVICIO_MIN = {
    TIPO_SERVICIO_ESTANDAR: 8,
    TIPO_SERVICIO_INSTALACION: 25,
    TIPO_SERVICIO_SUBIDA: 18,
    TIPO_SERVICIO_ESPECIAL: 30,
}

MODELOS_COLCHON = [
    {"modelo": "Comfort 1.5 plazas", "ancho": 1.05, "largo": 1.90, "peso_kg": 22},
    {"modelo": "Comfort 2 plazas",   "ancho": 1.35, "largo": 1.90, "peso_kg": 30},
    {"modelo": "Premium Queen",      "ancho": 1.60, "largo": 2.00, "peso_kg": 38},
    {"modelo": "Premium King",       "ancho": 2.00, "largo": 2.00, "peso_kg": 48},
    {"modelo": "Orthopedic 2 plazas","ancho": 1.35, "largo": 1.90, "peso_kg": 35},
]

PERFILES_TRAFICO = [
    ("09:00", "11:00", 1.15),
    ("11:00", "13:00", 1.05),
    ("13:00", "15:00", 1.20),
    ("15:00", "17:00", 1.35),
    ("17:00", "19:00", 1.55),
]

PROB_INCIDENCIAS = {
    "trafico_severo": 0.08,
    "estacionamiento_dificil": 0.12,
    "acceso_restringido": 0.05,
    "cliente_ausente": 0.07,
    "rechazo_entrega": 0.02,
    "demora_pago": 0.04,
}

# Estados de entrega
ESTADO_PENDIENTE = "Pendiente"
ESTADO_EN_RUTA = "En ruta"
ESTADO_A_TIEMPO = "A tiempo"
ESTADO_FUERA_VENTANA = "Fuera de ventana"
ESTADO_FALLIDA = "Fallida"
ESTADO_REPLANIFICADA = "Replanificada"
ESTADO_EN_RIESGO = "En riesgo"

ESTADOS_ENTREGA = [
    ESTADO_A_TIEMPO,
    ESTADO_FUERA_VENTANA,
    ESTADO_FALLIDA,
    ESTADO_REPLANIFICADA,
    ESTADO_PENDIENTE,
    ESTADO_EN_RIESGO,
]

COLOR_ESTADO = {
    ESTADO_A_TIEMPO:      "#027A48",
    ESTADO_FUERA_VENTANA: "#B54708",
    ESTADO_FALLIDA:       "#B42318",
    ESTADO_REPLANIFICADA: "#1570EF",
    ESTADO_PENDIENTE:     "#667085",
    ESTADO_EN_RIESGO:     "#DC6803",
    ESTADO_EN_RUTA:       "#0E96CC",
}

DATASET_FILES = [
    "pedidos.csv",
    "vehiculos.csv",
    "almacen.csv",
    "zonas_operativas.csv",
    "matriz_tiempos_base.csv",
    "perfiles_trafico.csv",
    "tiempos_servicio.csv",
    "probabilidades_incidencias.csv",
    "configuracion_simulacion.json",
    "asignacion_inicial_referencial.csv",
]
