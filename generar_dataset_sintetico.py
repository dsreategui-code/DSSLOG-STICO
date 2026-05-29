"""Generador de dataset sintetico para el DSS Logistico - Callao 80 pedidos.

Crea la carpeta data/datasets/dataset_demo_callao_80pedidos/ con:
  pedidos.csv, vehiculos.csv, almacen.csv, zonas_operativas.csv,
  matriz_tiempos_base.csv, perfiles_trafico.csv, tiempos_servicio.csv,
  probabilidades_incidencias.csv, configuracion_simulacion.json,
  asignacion_inicial_referencial.csv

Uso:
  python generar_dataset_sintetico.py
"""
from pathlib import Path
import json
import math
import random
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Configuracion base
# ---------------------------------------------------------------------------
SEED = 42
NUM_PEDIDOS = 80
NUM_VEHICULOS = 10

ALMACEN = {
    "nombre": "Almacen Callao",
    "distrito": "Callao",
    "latitud": -12.0500,
    "longitud": -77.1200,
}

# Centroides aproximados y radio de dispersion (en grados) por zona
ZONAS = {
    "Callao / Oeste":   {"centro": (-12.058, -77.115), "radio": 0.035},
    "Lima Centro":      {"centro": (-12.060, -77.040), "radio": 0.030},
    "Lima Norte":       {"centro": (-11.985, -77.060), "radio": 0.045},
    "Lima Sur":         {"centro": (-12.180, -76.990), "radio": 0.050},
    "Lima Este":        {"centro": (-12.050, -76.940), "radio": 0.050},
    "Lima Moderna":     {"centro": (-12.105, -77.015), "radio": 0.030},
}

DISTRITOS_POR_ZONA = {
    "Callao / Oeste": ["Callao", "Bellavista", "La Perla", "Carmen de la Legua", "Ventanilla"],
    "Lima Centro": ["Cercado de Lima", "Brena", "La Victoria", "Rimac", "San Luis"],
    "Lima Norte": ["Los Olivos", "San Martin de Porres", "Independencia", "Comas", "Puente Piedra"],
    "Lima Sur": ["Villa El Salvador", "Villa Maria del Triunfo", "Chorrillos", "Lurin", "San Juan de Miraflores"],
    "Lima Este": ["San Juan de Lurigancho", "Ate", "Santa Anita", "El Agustino", "La Molina"],
    "Lima Moderna": ["Miraflores", "San Isidro", "San Borja", "Surco", "Magdalena", "Jesus Maria", "Pueblo Libre", "Surquillo"],
}

VENTANAS = [
    ("09:00", "12:00"),
    ("10:00", "13:00"),
    ("12:00", "15:00"),
    ("14:00", "17:00"),
    ("16:00", "19:00"),
]

MODELOS = [
    {"modelo": "Comfort 1.5 plazas", "peso_kg": 22},
    {"modelo": "Comfort 2 plazas",   "peso_kg": 30},
    {"modelo": "Premium Queen",      "peso_kg": 38},
    {"modelo": "Premium King",       "peso_kg": 48},
    {"modelo": "Orthopedic 2 plazas","peso_kg": 35},
]

# tipo_servicio, tiempo_base_min, peso_para_eleccion
TIPOS_SERVICIO = [
    ("Estandar",                8,  0.45),
    ("Instalacion",            25,  0.20),
    ("Subida a departamento", 18,  0.25),
    ("Atencion especial",     30,  0.10),
]

PERFILES_TRAFICO = [
    ("09:00", "11:00", 1.15),
    ("11:00", "13:00", 1.05),
    ("13:00", "15:00", 1.20),
    ("15:00", "17:00", 1.35),
    ("17:00", "19:00", 1.55),
]

PROB_INCIDENCIAS = [
    ("zona_dificil_acceso",     0.05),
    ("cliente_no_encontrado",   0.07),
    ("demora_estacionamiento",  0.10),
    ("congestion_inesperada",   0.08),
    ("restriccion_acceso",      0.04),
    ("demora_instalacion",      0.05),
    ("direccion_incompleta",    0.04),
]

NOMBRES = [
    "Diego", "Maria", "Carlos", "Lucia", "Jose", "Andrea", "Pedro", "Sofia",
    "Luis", "Camila", "Renato", "Valeria", "Jorge", "Patricia", "Ricardo",
    "Daniela", "Manuel", "Rocio", "Felipe", "Gabriela", "Ivan", "Mariana",
    "Hugo", "Paola", "Tomas", "Karla", "Bruno", "Lorena", "Adrian", "Cinthia",
]
APELLIDOS = [
    "Rojas", "Quispe", "Gutierrez", "Castro", "Mendoza", "Salinas", "Torres",
    "Romero", "Vargas", "Flores", "Cordero", "Paredes", "Ramos", "Salazar",
    "Aliaga", "Perez", "Bustamante", "Aguilar", "Leon", "Vega",
]


# ---------------------------------------------------------------------------
# Utilitarios
# ---------------------------------------------------------------------------
def _punto_en_zona(centro, radio):
    """Genera un punto plausible dentro de un circulo aproximado."""
    angle = random.uniform(0, 2 * math.pi)
    r = radio * math.sqrt(random.random())
    lat = centro[0] + r * math.cos(angle)
    lon = centro[1] + r * math.sin(angle)
    return round(lat, 6), round(lon, 6)


def _haversine_aprox_km(lat1, lon1, lat2, lon2):
    """Distancia aprox. en km con conversion grado -> km (suficiente para sintetico)."""
    dx = (lat2 - lat1) * 111.0
    dy = (lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dx * dx + dy * dy)


# ---------------------------------------------------------------------------
# Generadores
# ---------------------------------------------------------------------------
def gen_pedidos() -> pd.DataFrame:
    pedidos = []
    zonas_lista = list(ZONAS.keys())
    pesos_zona = [0.18, 0.16, 0.18, 0.16, 0.16, 0.16]

    for i in range(NUM_PEDIDOS):
        zona = random.choices(zonas_lista, weights=pesos_zona, k=1)[0]
        distrito = random.choice(DISTRITOS_POR_ZONA[zona])
        lat, lon = _punto_en_zona(ZONAS[zona]["centro"], ZONAS[zona]["radio"])

        modelo = random.choice(MODELOS)
        tipo_idx = random.choices(
            range(len(TIPOS_SERVICIO)),
            weights=[t[2] for t in TIPOS_SERVICIO], k=1,
        )[0]
        tipo, base, _ = TIPOS_SERVICIO[tipo_idx]
        tiempo_serv = max(5, int(round(np.random.normal(base, base * 0.18))))

        ventana = random.choice(VENTANAS)
        cliente = f"{random.choice(NOMBRES)} {random.choice(APELLIDOS)}"

        pedidos.append({
            "pedido_id": f"P{i+1:03d}",
            "cliente": cliente,
            "distrito": distrito,
            "zona": zona,
            "latitud": lat,
            "longitud": lon,
            "modelo": modelo["modelo"],
            "peso_kg": modelo["peso_kg"],
            "tipo_servicio": tipo,
            "tiempo_servicio_min": tiempo_serv,
            "ventana_inicio": ventana[0],
            "ventana_fin": ventana[1],
            "telefono": f"9{random.randint(10000000, 99999999)}",
            "direccion": f"Av. {random.choice(APELLIDOS)} {random.randint(100, 2400)}",
        })
    return pd.DataFrame(pedidos)


def gen_vehiculos() -> pd.DataFrame:
    placas_alfa = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K"]
    zonas_lista = list(ZONAS.keys())
    rows = []
    for i in range(NUM_VEHICULOS):
        rows.append({
            "vehiculo_id": f"V{i+1:02d}",
            "placa": f"AB{i+1:02d}-{placas_alfa[i % len(placas_alfa)]}{random.randint(100, 999)}",
            "capacidad_unidades": random.choice([10, 12, 14]),
            "capacidad_kg": random.choice([450, 550, 650]),
            "zona_preferente": zonas_lista[i % len(zonas_lista)],
            "conductor": f"{random.choice(NOMBRES)} {random.choice(APELLIDOS)}",
        })
    return pd.DataFrame(rows)


def gen_almacen() -> pd.DataFrame:
    return pd.DataFrame([ALMACEN])


def gen_zonas() -> pd.DataFrame:
    rows = []
    for zona, info in ZONAS.items():
        rows.append({
            "zona": zona,
            "centro_lat": info["centro"][0],
            "centro_lon": info["centro"][1],
            "radio_aprox_grados": info["radio"],
            "distritos": ", ".join(DISTRITOS_POR_ZONA[zona]),
        })
    return pd.DataFrame(rows)


def gen_matriz_tiempos(pedidos_df: pd.DataFrame) -> pd.DataFrame:
    """Matriz origen-destino con tiempo y distancia entre almacen y pedidos."""
    puntos = [("ALMACEN", ALMACEN["latitud"], ALMACEN["longitud"])]
    for _, p in pedidos_df.iterrows():
        puntos.append((p["pedido_id"], p["latitud"], p["longitud"]))

    rows = []
    for i, (oid, olat, olon) in enumerate(puntos):
        for j, (did, dlat, dlon) in enumerate(puntos):
            if i == j:
                continue
            dist = _haversine_aprox_km(olat, olon, dlat, dlon)
            # Velocidad urbana promedio 18 km/h + ruido suave
            tiempo = (dist / 18.0) * 60.0 * random.uniform(0.95, 1.15)
            rows.append({
                "origen": oid,
                "destino": did,
                "distancia_km": round(dist, 3),
                "tiempo_min": round(tiempo, 2),
            })
    return pd.DataFrame(rows)


def gen_perfiles_trafico() -> pd.DataFrame:
    return pd.DataFrame(PERFILES_TRAFICO, columns=["franja_inicio", "franja_fin", "multiplicador"])


def gen_tiempos_servicio() -> pd.DataFrame:
    return pd.DataFrame(
        [{"tipo_servicio": t[0], "tiempo_base_min": t[1]} for t in TIPOS_SERVICIO]
    )


def gen_probabilidades_incidencias() -> pd.DataFrame:
    return pd.DataFrame(PROB_INCIDENCIAS, columns=["incidencia", "probabilidad"])


def gen_configuracion_simulacion() -> dict:
    return {
        "jornada_inicio": "09:00",
        "jornada_fin": "19:00",
        "semilla": SEED,
        "num_vehiculos": NUM_VEHICULOS,
        "num_pedidos": NUM_PEDIDOS,
        "replanificacion": {
            "tipo": "intravehiculo",
            "requiere_aprobacion_supervisor": True,
            "umbral_riesgo_min": 15,
            "permitir_reasignacion_entre_vehiculos": False,
        },
        "variabilidad": {
            "trafico": True,
            "estacionamiento": True,
            "tiempo_servicio": True,
            "incidencias": True,
        },
        "iteraciones_montecarlo": 30,
        "escenarios": [
            {"id": "sin_dss",         "nombre": "Sin DSS",              "replanifica": False, "ruta_optimizada": False},
            {"id": "solo_ruta",       "nombre": "Ruta optimizada",      "replanifica": False, "ruta_optimizada": True},
            {"id": "dss_completo",    "nombre": "DSS completo",         "replanifica": True,  "ruta_optimizada": True},
        ],
    }


def gen_asignacion_inicial(pedidos_df: pd.DataFrame, vehiculos_df: pd.DataFrame) -> pd.DataFrame:
    """Asignacion referencial respetando regla intravehiculo (cada pedido a un solo vehiculo).

    Asigna por zona preferente y ordena dentro del vehiculo por inicio de ventana
    horaria para permitir pruebas tempranas de rutas.
    """
    df = pedidos_df.copy()
    df["v_min"] = (
        df["ventana_inicio"].str[:2].astype(int) * 60
        + df["ventana_inicio"].str[3:].astype(int)
    )
    df = df.sort_values(["zona", "v_min", "pedido_id"]).reset_index(drop=True)

    veh_por_zona = vehiculos_df.groupby("zona_preferente")["vehiculo_id"].apply(list).to_dict()
    seq_por_veh = {v: 1 for v in vehiculos_df["vehiculo_id"]}
    contador_zona = {z: 0 for z in veh_por_zona}

    rows = []
    for _, p in df.iterrows():
        zona = p["zona"]
        candidatos = veh_por_zona.get(zona) or list(vehiculos_df["vehiculo_id"])
        idx = contador_zona.get(zona, 0) % len(candidatos)
        veh = candidatos[idx]
        contador_zona[zona] = contador_zona.get(zona, 0) + 1
        rows.append({
            "vehiculo_id": veh,
            "pedido_id": p["pedido_id"],
            "secuencia": seq_por_veh[veh],
        })
        seq_por_veh[veh] += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------
def main():
    random.seed(SEED)
    np.random.seed(SEED)

    out_dir = Path(__file__).resolve().parent / "data" / "datasets" / "dataset_demo_callao_80pedidos"
    out_dir.mkdir(parents=True, exist_ok=True)

    pedidos = gen_pedidos()
    vehiculos = gen_vehiculos()
    almacen = gen_almacen()
    zonas = gen_zonas()
    matriz = gen_matriz_tiempos(pedidos)
    perfiles = gen_perfiles_trafico()
    tiempos_serv = gen_tiempos_servicio()
    probs = gen_probabilidades_incidencias()
    config = gen_configuracion_simulacion()
    asignacion = gen_asignacion_inicial(pedidos, vehiculos)

    pedidos.to_csv(out_dir / "pedidos.csv", index=False, encoding="utf-8")
    vehiculos.to_csv(out_dir / "vehiculos.csv", index=False, encoding="utf-8")
    almacen.to_csv(out_dir / "almacen.csv", index=False, encoding="utf-8")
    zonas.to_csv(out_dir / "zonas_operativas.csv", index=False, encoding="utf-8")
    matriz.to_csv(out_dir / "matriz_tiempos_base.csv", index=False, encoding="utf-8")
    perfiles.to_csv(out_dir / "perfiles_trafico.csv", index=False, encoding="utf-8")
    tiempos_serv.to_csv(out_dir / "tiempos_servicio.csv", index=False, encoding="utf-8")
    probs.to_csv(out_dir / "probabilidades_incidencias.csv", index=False, encoding="utf-8")
    asignacion.to_csv(out_dir / "asignacion_inicial_referencial.csv", index=False, encoding="utf-8")

    with open(out_dir / "configuracion_simulacion.json", "w", encoding="utf-8") as fp:
        json.dump(config, fp, indent=2, ensure_ascii=False)

    print(f"OK: dataset generado en {out_dir}")
    print(f"  - {len(pedidos)} pedidos, {len(vehiculos)} vehiculos")
    print(f"  - Matriz O/D: {len(matriz)} pares ({len(pedidos)+1} puntos)")


if __name__ == "__main__":
    main()
