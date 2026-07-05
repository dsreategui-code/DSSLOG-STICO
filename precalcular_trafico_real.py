"""Pre-descarga UNA vez el factor de TRAFICO real por macrozona (TomTom) y lo escribe en
data/plantillas/trafico_real.csv para la FRANJA actual. El motor lo lee (no llama en vivo); las
filas reales tienen precedencia por macrozona y la tabla sintetica queda de respaldo.

Consumo: ~3 puntos x nº de macrozonas (independiente del nº de pedidos). Corre este script a
distintas horas (manana / mediodia / tarde) para llenar las 3 franjas; cada corrida MERGEA.

Requiere una API key GRATIS de TomTom (free tier, sin tarjeta): crea la cuenta en
developer.tomtom.com y expone la key:
    Windows PowerShell:  $env:TOMTOM_API_KEY = 'tu_key';  .venv\\Scripts\\python.exe precalcular_trafico_real.py
    (o ponla en .streamlit/secrets.toml como TOMTOM_API_KEY para la nube)
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from services.cortex_loader import cargar_contexto
from services.tomtom_client import TomTomClient, factores_por_macrozona

# Franjas ALINEADAS con data/plantillas/factores_trafico.csv (para que el override coincida).
FRANJAS = [("manana", "07:00", "10:00"), ("mediodia", "10:00", "16:00"),
           ("tarde", "16:00", "20:00"), ("noche", "20:00", "23:59")]
OUT = Path("data/plantillas/trafico_real.csv")


def _franja_actual() -> tuple:
    ahora = datetime.now().hour * 60 + datetime.now().minute
    for nombre, hi, hf in FRANJAS:
        h0 = int(hi[:2]) * 60 + int(hi[3:5])
        h1 = int(hf[:2]) * 60 + int(hf[3:5])
        if h0 <= ahora <= h1:
            return nombre, hi, hf
    return FRANJAS[0]


def main():
    key = os.environ.get("TOMTOM_API_KEY", "")
    if not key:
        print("Falta TOMTOM_API_KEY. Crea la cuenta gratis en developer.tomtom.com y expórtala.")
        return
    ctx = cargar_contexto()
    zmap = {z.distrito: z.macrozona for z in ctx["zonas"]}
    pts = defaultdict(list)
    for p in ctx["pedidos"]:
        mz = zmap.get(p.distrito)
        if mz:
            pts[mz].append((float(p.lat), float(p.lon)))
    muestras = {mz: coords[:3] for mz, coords in pts.items()}   # ~3 puntos representativos/macrozona
    fac = factores_por_macrozona(muestras, client=TomTomClient(api_key=key))
    franja, hi, hf = _franja_actual()

    filas = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                filas[(r["macrozona"], r["franja"])] = r
    for mz, fval in fac.items():
        filas[(mz, franja)] = {"macrozona": mz, "franja": franja, "hora_inicio": hi,
                               "hora_fin": hf, "factor_trafico": round(float(fval), 3)}
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["macrozona", "franja", "hora_inicio", "hora_fin",
                                          "factor_trafico"])
        w.writeheader()
        for row in filas.values():
            w.writerow(row)
    print(f"Franja '{franja}': factores TomTom de {len(fac)} macrozonas escritos en {OUT}")
    for mz, fval in sorted(fac.items(), key=lambda kv: -kv[1]):
        print(f"  {mz:12s} factor_trafico = {fval}")


if __name__ == "__main__":
    main()
