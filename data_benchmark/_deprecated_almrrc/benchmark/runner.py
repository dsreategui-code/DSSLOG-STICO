"""Runner del benchmark ALM RRC.

Ejecuta, para una muestra de rutas, el flujo:
    cargar (cache) -> adaptar -> optimizar (motor DSS sobre matriz real) -> metricas
y consolida los resultados en un DataFrame, exportable a CSV/XLSX.

Tolerante a fallos: cada ruta se procesa en su propio try/except; los errores se
registran como una fila con status de error, sin abortar el lote.

Uso CLI:
    python -m benchmark.runner --n 10 --motor auto --time-limit 10
    python -m benchmark.runner --rutas RouteID_xxx RouteID_yyy
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from config.settings import OUTPUTS_DIR
from benchmark import alm_loader, adapter, optimizer_adapter, metrics


def correr_benchmark(route_ids: Optional[List[str]] = None,
                     n: Optional[int] = None,
                     motor: str = "auto",
                     time_limit_seconds: int = 10,
                     usar_ventanas: bool = False,
                     progress_callback=None) -> pd.DataFrame:
    """Ejecuta el benchmark y devuelve el DataFrame consolidado de resultados.

    Args:
        route_ids: lista explicita de rutas; si None usa el indice del cache.
        n: si route_ids es None, limita a las primeras n rutas del indice.
        progress_callback: callback(i, total, route_id) opcional para la UI.
    """
    if route_ids is None:
        disponibles = alm_loader.listar_route_ids()
        route_ids = disponibles[:n] if n else disponibles
    if not route_ids:
        raise RuntimeError(
            "No hay rutas en el cache. Ejecuta primero: "
            "python -m benchmark.prepare_cache --n-rutas 30"
        )

    filas = []
    total = len(route_ids)
    for i, rid in enumerate(route_ids, start=1):
        if progress_callback:
            try:
                progress_callback(i, total, rid)
            except Exception:
                pass
        try:
            data = alm_loader.cargar_ruta(rid)
            caso = adapter.construir_caso(data)
            opt = optimizer_adapter.optimizar_secuencia(
                caso, motor=motor, time_limit_seconds=time_limit_seconds,
                usar_ventanas=usar_ventanas,
            )
            fila = metrics.evaluar_ruta(caso, opt)
        except Exception as e:  # noqa: BLE001
            fila = {
                "route_id": rid, "station_code": "", "route_score": "",
                "n_paradas": None,
                "sd_stop": None, "sd_zone": None, "erp_ratio_min": None,
                "score_aprox": None,
                "tiempo_real_min": None, "tiempo_propuesto_min": None,
                "brecha_pct": None,
                "motor_usado": motor, "tiempo_computo_seg": None,
                "status": f"error: {e}",
            }
        filas.append(fila)

    df = pd.DataFrame(filas)
    # Orden canonico de columnas (las faltantes se ignoran).
    cols = [c for c in metrics.COLUMNAS_RESULTADO if c in df.columns]
    extra = [c for c in df.columns if c not in cols]
    return df[cols + extra]


def exportar_resultados(df: pd.DataFrame, prefijo: str = "benchmark_almrrc") -> dict:
    """Guarda CSV y XLSX en data/outputs y devuelve las rutas escritas."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUTS_DIR / f"{prefijo}_{ts}.csv"
    xlsx_path = OUTPUTS_DIR / f"{prefijo}_{ts}.xlsx"

    df.to_csv(csv_path, index=False, encoding="utf-8")

    resumen = metrics.resumen_global(df.to_dict("records"))
    try:
        with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
            df.to_excel(writer, sheet_name="Detalle_por_ruta", index=False)
            if resumen:
                pd.DataFrame([resumen]).to_excel(
                    writer, sheet_name="Resumen", index=False
                )
    except Exception:
        xlsx_path = None  # openpyxl/xlsxwriter ausente: el CSV sigue disponible

    return {"csv": csv_path, "xlsx": xlsx_path, "resumen": resumen}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Runner de benchmark ALM RRC.")
    ap.add_argument("--n", type=int, default=None, help="Numero de rutas del cache a correr.")
    ap.add_argument("--rutas", nargs="*", default=None, help="route_ids explicitos.")
    ap.add_argument("--motor", default="auto", choices=["auto", "ortools", "greedy"])
    ap.add_argument("--time-limit", type=int, default=10)
    ap.add_argument("--ventanas", action="store_true",
                    help="Aplica ventanas confiables como restriccion en el solver.")
    args = ap.parse_args(argv)

    try:
        df = correr_benchmark(
            route_ids=args.rutas, n=args.n, motor=args.motor,
            time_limit_seconds=args.time_limit, usar_ventanas=args.ventanas,
            progress_callback=lambda i, t, r: print(f"  [{i}/{t}] {r}"),
        )
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    out = exportar_resultados(df)
    print("\n=== RESUMEN GLOBAL ===")
    for k, v in (out["resumen"] or {}).items():
        print(f"  {k}: {v}")
    print(f"\nCSV : {out['csv']}")
    print(f"XLSX: {out['xlsx']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
