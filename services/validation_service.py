"""Orquestador del experimento de validacion (Monte Carlo multi-escenario)."""
import pandas as pd

from simulation.sim_engine import simular_escenarios
from simulation.metrics import aggregate_iterations


ESCENARIOS_DEFAULT = [
    {"id": "sin_dss",      "nombre": "Sin DSS"},
    {"id": "solo_ruta",    "nombre": "Ruta optimizada"},
    {"id": "dss_completo", "nombre": "DSS completo"},
]


def run_validation(dataset: dict, configuracion: dict) -> dict:
    """Ejecuta el experimento Monte Carlo y devuelve resultados agregados.

    Estructura de retorno:
        {
          "escenarios": {esc_id: {entregas, kpis, evolucion_otd, alertas, ...}, ...},
          "iteraciones": DataFrame [escenario, iteracion, kpis...],
          "resumen": DataFrame [escenario, otd_prom, otd_std, cv_otd_pct, ...],
          "evolucion_otd": DataFrame [escenario, hora, otd] (jornada representativa),
          "kpis_por_escenario": DataFrame con los KPIs principales de la ultima iter,
        }
    """
    iteraciones = int(configuracion.get("iteraciones", 30))
    raw = simular_escenarios(dataset, configuracion, iteraciones=iteraciones)
    iters_df = raw["iteraciones"]
    resumen = aggregate_iterations(iters_df)

    # KPIs por escenario (ultima iteracion como representativa)
    kpis_rows = []
    evolucion_concat = []
    for esc_id, res in raw["escenarios"].items():
        kpis = res.get("kpis", {})
        kpis_rows.append({"escenario": esc_id, **kpis})
        evol = res.get("evolucion_otd")
        if evol is not None and not evol.empty:
            tmp = evol.copy()
            tmp["escenario"] = esc_id
            evolucion_concat.append(tmp)

    kpis_df = pd.DataFrame(kpis_rows)
    evol_all = pd.concat(evolucion_concat, ignore_index=True) if evolucion_concat else pd.DataFrame()

    return {
        "escenarios": raw["escenarios"],
        "iteraciones": iters_df,
        "resumen": resumen,
        "evolucion_otd": evol_all,
        "kpis_por_escenario": kpis_df,
        "escenarios_lista": raw["escenarios_lista"],
    }


def label_escenario(esc_id: str) -> str:
    for esc in ESCENARIOS_DEFAULT:
        if esc["id"] == esc_id:
            return esc["nombre"]
    return esc_id
