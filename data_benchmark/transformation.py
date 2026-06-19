from pathlib import Path
import json
import csv
import pandas as pd


# ============================================================
# CONFIGURACIÓN DE RUTAS
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
BENCHMARK_DIR = SCRIPT_DIR

RAW_DIR = BENCHMARK_DIR / "raw_json" / "almrrc2021"
OUT_CSV = BENCHMARK_DIR / "processed_csv"
OUT_EXCEL = BENCHMARK_DIR / "processed_excel"

OUT_CSV.mkdir(parents=True, exist_ok=True)
OUT_EXCEL.mkdir(parents=True, exist_ok=True)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def find_json_file(filename: str) -> Path:
    """
    Busca un archivo JSON dentro de la carpeta raw_json/almrrc2021.
    Prioriza la carpeta model_build_inputs si existe.
    """
    matches = list(RAW_DIR.rglob(filename))

    if not matches:
        raise FileNotFoundError(f"No se encontró {filename} dentro de {RAW_DIR}")

    for path in matches:
        if "model_build_inputs" in str(path):
            return path

    return matches[0]


def load_json(filename: str) -> dict:
    path = find_json_file(filename)
    print(f"Leyendo: {path}")

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_dataframe(df: pd.DataFrame, name: str, save_excel: bool = True) -> None:
    """
    Guarda un DataFrame en CSV y, si no es muy grande, también en Excel.
    """
    csv_path = OUT_CSV / f"{name}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"CSV generado: {csv_path}")

    if save_excel:
        if len(df) <= 1_000_000:
            excel_path = OUT_EXCEL / f"{name}.xlsx"
            df.to_excel(excel_path, index=False)
            print(f"Excel generado: {excel_path}")
        else:
            print(f"No se generó Excel para {name} porque supera el límite práctico de filas.")


def safe_get(dictionary: dict, key: str, default=None):
    if isinstance(dictionary, dict):
        return dictionary.get(key, default)
    return default


# ============================================================
# 1. TRANSFORMAR route_data.json
# ============================================================

def transform_route_data(route_data: dict):
    routes_rows = []
    stops_rows = []

    for route_id, route_info in route_data.items():
        routes_rows.append({
            "route_id": route_id,
            "station_code": safe_get(route_info, "station_code"),
            "date": safe_get(route_info, "date_YYYY_MM_DD"),
            "departure_time_utc": safe_get(route_info, "departure_time_utc"),
            "executor_capacity_cm3": safe_get(route_info, "executor_capacity_cm3"),
            "route_score": safe_get(route_info, "route_score"),
        })

        stops = safe_get(route_info, "stops", {})

        for stop_id, stop_info in stops.items():
            stops_rows.append({
                "route_id": route_id,
                "stop_id": stop_id,
                "lat": safe_get(stop_info, "lat"),
                "lng": safe_get(stop_info, "lng"),
                "type": safe_get(stop_info, "type"),
                "zone_id": safe_get(stop_info, "zone_id"),
            })

    df_routes = pd.DataFrame(routes_rows)
    df_stops = pd.DataFrame(stops_rows)

    save_dataframe(df_routes, "01_routes")
    save_dataframe(df_stops, "02_stops")

    return df_routes, df_stops


# ============================================================
# 2. TRANSFORMAR actual_sequences.json
# ============================================================

def transform_actual_sequences(actual_sequences: dict):
    sequence_rows = []

    for route_id, sequence_info in actual_sequences.items():
        actual = safe_get(sequence_info, "actual", {})

        for stop_id, sequence_order in actual.items():
            sequence_rows.append({
                "route_id": route_id,
                "stop_id": stop_id,
                "actual_sequence": sequence_order,
            })

    df_sequences = pd.DataFrame(sequence_rows)

    if not df_sequences.empty:
        df_sequences = df_sequences.sort_values(
            by=["route_id", "actual_sequence"],
            ascending=[True, True]
        )

    save_dataframe(df_sequences, "03_actual_sequences")

    return df_sequences


# ============================================================
# 3. TRANSFORMAR package_data.json
# ============================================================

def transform_package_data(package_data: dict):
    package_rows = []

    for route_id, stops in package_data.items():
        for stop_id, packages in stops.items():
            for package_id, package_info in packages.items():

                time_window = safe_get(package_info, "time_window", {})
                dimensions = safe_get(package_info, "dimensions", {})

                package_rows.append({
                    "route_id": route_id,
                    "stop_id": stop_id,
                    "package_id": package_id,
                    "scan_status": safe_get(package_info, "scan_status"),
                    "planned_service_time_seconds": safe_get(package_info, "planned_service_time_seconds"),
                    "time_window_start_utc": safe_get(time_window, "start_time_utc"),
                    "time_window_end_utc": safe_get(time_window, "end_time_utc"),
                    "depth_cm": safe_get(dimensions, "depth_cm"),
                    "height_cm": safe_get(dimensions, "height_cm"),
                    "width_cm": safe_get(dimensions, "width_cm"),
                })

    df_packages = pd.DataFrame(package_rows)

    save_dataframe(df_packages, "04_packages")

    return df_packages


# ============================================================
# 4. TRANSFORMAR travel_times.json
# ============================================================

def transform_travel_times_to_csv(travel_times: dict):
    """
    Convierte la matriz de tiempos a formato largo:
    route_id, origen, destino, tiempo_viaje_seg, tiempo_viaje_min

    Se escribe directamente en CSV para evitar consumo excesivo de memoria.
    """
    output_path = OUT_CSV / "05_travel_times_long.csv"

    if output_path.exists():
        print(f"El archivo ya existe y no se volverá a generar: {output_path}")
        return

    with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow([
            "route_id",
            "origen_stop_id",
            "destino_stop_id",
            "tiempo_viaje_seg",
            "tiempo_viaje_min"
        ])

        row_count = 0

        for route_id, matrix in travel_times.items():
            for origen_stop_id, destinos in matrix.items():
                for destino_stop_id, tiempo_seg in destinos.items():
                    tiempo_min = None

                    if tiempo_seg is not None:
                        tiempo_min = tiempo_seg / 60

                    writer.writerow([
                        route_id,
                        origen_stop_id,
                        destino_stop_id,
                        tiempo_seg,
                        tiempo_min
                    ])

                    row_count += 1

    print(f"CSV generado: {output_path}")
    print(f"Filas generadas en matriz de tiempos: {row_count:,}")
    print("No se genera Excel de matriz de tiempos porque puede ser muy pesada.")


# ============================================================
# 5. CREAR TABLA BASE DE PEDIDOS PARA EL DSS
# ============================================================

def create_dss_orders_table(df_stops: pd.DataFrame,
                            df_sequences: pd.DataFrame,
                            df_packages: pd.DataFrame):
    """
    Crea una tabla tipo pedidos a nivel de parada.
    Esta tabla sirve como base para adaptarla a pedidos.xlsx de tu DSS.
    """

    df_orders = df_stops.copy()

    if not df_sequences.empty:
        df_orders = df_orders.merge(
            df_sequences,
            on=["route_id", "stop_id"],
            how="left"
        )

    if not df_packages.empty:
        df_packages = df_packages.copy()

        # Limpieza de tipos de datos para evitar errores de agregación
        df_packages["planned_service_time_seconds"] = pd.to_numeric(
            df_packages["planned_service_time_seconds"],
            errors="coerce"
        ).fillna(0)

        df_packages["time_window_start_utc"] = pd.to_datetime(
            df_packages["time_window_start_utc"],
            errors="coerce",
            utc=True
        )

        df_packages["time_window_end_utc"] = pd.to_datetime(
            df_packages["time_window_end_utc"],
            errors="coerce",
            utc=True
        )

        package_summary = (
            df_packages
            .groupby(["route_id", "stop_id"], as_index=False)
            .agg(
                cantidad_paquetes=("package_id", "count"),
                tiempo_servicio_total_seg=("planned_service_time_seconds", "sum"),
                ventana_inicio_utc=("time_window_start_utc", "min"),
                ventana_fin_utc=("time_window_end_utc", "max"),
            )
        )

        package_summary["tiempo_servicio_total_min"] = (
            package_summary["tiempo_servicio_total_seg"] / 60
        )

        # Convertir fechas a texto para que Excel/CSV las maneje mejor
        package_summary["ventana_inicio_utc"] = package_summary["ventana_inicio_utc"].astype(str)
        package_summary["ventana_fin_utc"] = package_summary["ventana_fin_utc"].astype(str)

        package_summary["ventana_inicio_utc"] = package_summary["ventana_inicio_utc"].replace("NaT", "")
        package_summary["ventana_fin_utc"] = package_summary["ventana_fin_utc"].replace("NaT", "")

        df_orders = df_orders.merge(
            package_summary,
            on=["route_id", "stop_id"],
            how="left"
        )

    # Excluir estación/depot para la tabla de pedidos, pero mantenerlo en stops.csv
    df_orders["type"] = df_orders["type"].astype(str)
    df_orders = df_orders[df_orders["type"].str.lower().ne("station")]

    df_orders = df_orders.rename(columns={
        "stop_id": "pedido_id",
        "lat": "latitud",
        "lng": "longitud",
        "zone_id": "zona"
    })

    columns_order = [
        "route_id",
        "pedido_id",
        "actual_sequence",
        "latitud",
        "longitud",
        "type",
        "zona",
        "cantidad_paquetes",
        "tiempo_servicio_total_seg",
        "tiempo_servicio_total_min",
        "ventana_inicio_utc",
        "ventana_fin_utc"
    ]

    existing_columns = [col for col in columns_order if col in df_orders.columns]
    df_orders = df_orders[existing_columns]

    save_dataframe(df_orders, "06_dss_pedidos_base")

    return df_orders

# ============================================================
# 6. CREAR RESUMEN POR RUTA
# ============================================================

def create_route_summary(df_routes: pd.DataFrame,
                         df_stops: pd.DataFrame,
                         df_packages: pd.DataFrame):
    stops_summary = (
        df_stops
        .groupby("route_id", as_index=False)
        .agg(
            total_paradas=("stop_id", "count"),
            total_zonas=("zone_id", "nunique")
        )
    )

    if not df_packages.empty:
        packages_summary = (
            df_packages
            .groupby("route_id", as_index=False)
            .agg(
                total_paquetes=("package_id", "count"),
                tiempo_servicio_total_seg=("planned_service_time_seconds", "sum")
            )
        )

        packages_summary["tiempo_servicio_total_min"] = (
            packages_summary["tiempo_servicio_total_seg"] / 60
        )
    else:
        packages_summary = pd.DataFrame(columns=[
            "route_id",
            "total_paquetes",
            "tiempo_servicio_total_seg",
            "tiempo_servicio_total_min"
        ])

    df_summary = df_routes.merge(stops_summary, on="route_id", how="left")
    df_summary = df_summary.merge(packages_summary, on="route_id", how="left")

    save_dataframe(df_summary, "07_route_summary")

    return df_summary


# ============================================================
# EJECUCIÓN PRINCIPAL
# ============================================================

def main():
    print("==============================================")
    print("CONVERSIÓN DEL DATASET ALM RRC")
    print("==============================================")

    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"No existe la carpeta {RAW_DIR}. "
            "Verifica que el dataset esté dentro de data_benchmark/raw_json/almrrc2021/"
        )

    route_data = load_json("route_data.json")
    actual_sequences = load_json("actual_sequences.json")
    package_data = load_json("package_data.json")
    travel_times = load_json("travel_times.json")

    print("\nTransformando route_data.json...")
    df_routes, df_stops = transform_route_data(route_data)

    print("\nTransformando actual_sequences.json...")
    df_sequences = transform_actual_sequences(actual_sequences)

    print("\nTransformando package_data.json...")
    df_packages = transform_package_data(package_data)

    print("\nTransformando travel_times.json...")
    transform_travel_times_to_csv(travel_times)

    print("\nCreando tabla base de pedidos para el DSS...")
    create_dss_orders_table(df_stops, df_sequences, df_packages)

    print("\nCreando resumen por ruta...")
    create_route_summary(df_routes, df_stops, df_packages)

    print("\n==============================================")
    print("CONVERSIÓN FINALIZADA CORRECTAMENTE")
    print("Archivos generados en:")
    print(f"- {OUT_CSV}")
    print(f"- {OUT_EXCEL}")
    print("==============================================")


if __name__ == "__main__":
    main()