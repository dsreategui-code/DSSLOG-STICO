"""Preparacion UNICA del cache de benchmark (paso offline).

Extrae una muestra manejable de rutas desde los archivos transformados del
ALM RRC -incluido `05_travel_times_long.csv` de ~9.5 GB- hacia un cache compacto
en `data_benchmark/cache/`. El runner y la vista de Streamlit leen SOLO del cache,
por lo que nunca cargan los archivos pesados en tiempo de ejecucion.

BENCHMARK PRINCIPAL: por defecto se filtran UNICAMENTE rutas High Quality
(route_score == "High"), para que la comparacion sea con la base de rutas de alta
calidad usada por la literatura del ALM RRC. El filtro es obligatorio salvo que se
pida explicitamente lo contrario con --score (no recomendado para el principal).

NO modifica ni sobrescribe los archivos fuente.

Uso:
    python -m benchmark.prepare_cache --n-rutas 30 --seed 42                 # solo High
    python -m benchmark.prepare_cache --n-rutas 20 --min-paradas 80 --max-paradas 160
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from benchmark import paths


def _seleccionar_rutas(n: int, seed: int, score: str = None,
                       min_paradas: int = None, max_paradas: int = None) -> pd.DataFrame:
    """Selecciona una muestra de rutas desde 07_route_summary (+ 01_routes)."""
    f_sum = paths.processed_csv("route_summary")
    f_routes = paths.processed_csv("routes")
    if f_sum is None or f_routes is None:
        raise FileNotFoundError(
            "No se encontraron 07_route_summary.csv o 01_routes.csv. "
            "Verifica que el dataset ALM RRC transformado este en data_benchmark/processed_csv/."
        )
    resumen = pd.read_csv(f_sum)
    routes = pd.read_csv(f_routes)

    df = resumen.merge(
        routes[["route_id", "departure_time_utc", "date", "station_code", "route_score"]],
        on="route_id", how="left", suffixes=("", "_r"),
    )
    # Filtros opcionales.
    if score:
        df = df[df["route_score"].astype(str).str.lower() == score.lower()]
    if min_paradas is not None:
        df = df[df["total_paradas"] >= min_paradas]
    if max_paradas is not None:
        df = df[df["total_paradas"] <= max_paradas]
    if df.empty:
        raise ValueError("Ningun ruta cumple los filtros indicados.")

    n = min(n, len(df))
    return df.sample(n=n, random_state=seed).reset_index(drop=True)


def _slice_por_rutas(clave_archivo: str, route_ids: set,
                     chunksize: int = 500_000) -> pd.DataFrame:
    """Lee un CSV grande por chunks y devuelve solo las filas de las rutas objetivo."""
    f = paths.processed_csv(clave_archivo)
    if f is None:
        return pd.DataFrame()
    partes = []
    for chunk in pd.read_csv(f, chunksize=chunksize):
        if "route_id" not in chunk.columns:
            break
        partes.append(chunk[chunk["route_id"].isin(route_ids)])
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def _extraer_matrices(route_ids: set, chunksize: int = 1_000_000) -> dict:
    """Stream del archivo de tiempos de viaje (9.5 GB) con corte temprano.

    Devuelve {route_id: DataFrame[origen_stop_id, destino_stop_id, tiempo_viaje_min]}.
    """
    f = paths.processed_csv("travel_times")
    if f is None:
        raise FileNotFoundError(
            "No se encontro 05_travel_times_long.csv (matriz de tiempos)."
        )
    acumulado = {rid: [] for rid in route_ids}
    por_ver = set(route_ids)
    ya_vistas = set()
    cols = ["route_id", "origen_stop_id", "destino_stop_id", "tiempo_viaje_min"]

    for chunk in pd.read_csv(f, chunksize=chunksize, usecols=lambda c: c.strip() in cols):
        chunk.columns = [c.strip() for c in chunk.columns]
        presentes = set(chunk["route_id"].unique()) & route_ids
        if presentes:
            sub = chunk[chunk["route_id"].isin(presentes)]
            for rid, g in sub.groupby("route_id"):
                acumulado[rid].append(
                    g[["origen_stop_id", "destino_stop_id", "tiempo_viaje_min"]]
                )
            ya_vistas |= presentes
        aun_no_vistas = por_ver - ya_vistas
        # Corte temprano: ya vimos todas las rutas objetivo y este chunk ya no
        # contiene ninguna de ellas -> hemos pasado el ultimo bloque relevante.
        if not aun_no_vistas and not presentes:
            break

    return {
        rid: (pd.concat(lst, ignore_index=True) if lst else pd.DataFrame(columns=cols[1:]))
        for rid, lst in acumulado.items()
    }


def preparar_cache(n_rutas: int = 30, seed: int = 42, score: str = "High",
                   min_paradas: int = None, max_paradas: int = None,
                   verbose: bool = True) -> Path:
    """Construye el cache de muestra y devuelve la ruta del indice.

    Por defecto score="High": el benchmark principal usa solo rutas High Quality.
    """
    if not paths.benchmark_disponible():
        raise FileNotFoundError(
            "Dataset ALM RRC transformado no encontrado. Esperado en "
            "data_benchmark/processed_csv/ (06_dss_pedidos_base.csv y 05_travel_times_long.csv)."
        )

    muestra = _seleccionar_rutas(n_rutas, seed, score, min_paradas, max_paradas)
    if verbose and score:
        print(f"[0/4] Filtro de calidad: route_score == '{score}'")
    route_ids = set(muestra["route_id"].tolist())
    if verbose:
        print(f"[1/4] Rutas seleccionadas: {len(route_ids)}")

    pedidos_all = _slice_por_rutas("dss_pedidos_base", route_ids)
    stops_all = _slice_por_rutas("stops", route_ids)
    if verbose:
        print(f"[2/4] Pedidos extraidos: {len(pedidos_all)} filas | "
              f"stops: {len(stops_all)} filas")

    if verbose:
        print("[3/4] Extrayendo matrices de tiempo (stream del archivo grande)...")
    matrices = _extraer_matrices(route_ids)

    # Estaciones (depot) por ruta.
    estaciones = stops_all[stops_all["type"].astype(str).str.lower() == "station"]
    est_idx = estaciones.set_index("route_id")

    cache = paths.cache_dir()
    index_rows = []
    escritas = 0
    for _, r in muestra.iterrows():
        rid = r["route_id"]
        ped = pedidos_all[pedidos_all["route_id"] == rid].copy()
        mat = matrices.get(rid, pd.DataFrame())
        if ped.empty or mat.empty or rid not in est_idx.index:
            if verbose:
                print(f"    - {rid}: datos incompletos, se omite.")
            continue
        est = est_idx.loc[rid]
        if isinstance(est, pd.DataFrame):
            est = est.iloc[0]

        rdir = paths.cache_ruta_dir(rid)
        rdir.mkdir(parents=True, exist_ok=True)
        ped.to_csv(rdir / "pedidos.csv", index=False)
        mat.to_csv(rdir / "matriz.csv", index=False)

        index_rows.append({
            "route_id": rid,
            "station_code": r.get("station_code", ""),
            "station_stop_id": est["stop_id"],
            "station_lat": float(est["lat"]),
            "station_lng": float(est["lng"]),
            "date": r.get("date", ""),
            "departure_time_utc": r.get("departure_time_utc", ""),
            "route_score": r.get("route_score", ""),
            "total_paradas": int(r.get("total_paradas", len(ped))),
            "total_paquetes": int(r.get("total_paquetes", 0)),
            "tiempo_servicio_total_min": round(float(r.get("tiempo_servicio_total_min", 0)), 2),
        })
        escritas += 1

    if not index_rows:
        raise RuntimeError("No se pudo construir ninguna ruta de benchmark valida.")

    index_df = pd.DataFrame(index_rows)
    index_df.to_csv(paths.cache_index_file(), index=False)

    meta = {
        "n_rutas": escritas,
        "seed": seed,
        "score": score,
        "min_paradas": min_paradas,
        "max_paradas": max_paradas,
        "fuente": "ALM RRC 2021 (transformado)",
    }
    with open(cache / "cache_meta.json", "w", encoding="utf-8") as fp:
        json.dump(meta, fp, indent=2, ensure_ascii=False)

    if verbose:
        print(f"[4/4] Cache listo: {escritas} rutas en {cache}")
        print(f"      Indice: {paths.cache_index_file()}")
    return paths.cache_index_file()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prepara el cache de benchmark ALM RRC.")
    ap.add_argument("--n-rutas", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--score", type=str, default="High",
                    help="Filtra por route_score (default High = benchmark principal).")
    ap.add_argument("--min-paradas", type=int, default=None)
    ap.add_argument("--max-paradas", type=int, default=None)
    args = ap.parse_args(argv)
    try:
        preparar_cache(args.n_rutas, args.seed, args.score,
                       args.min_paradas, args.max_paradas)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
