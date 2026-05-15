"""Exportacion de resultados a CSV y XLSX."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
import json
import pandas as pd

from config.settings import OUTPUTS_DIR


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def export_kpis_csv(kpis: dict) -> bytes:
    df = pd.DataFrame([
        {"indicador": k, "valor": v} for k, v in kpis.items()
    ])
    return df.to_csv(index=False).encode("utf-8")


def export_dataframe_csv(df: pd.DataFrame) -> bytes:
    if df is None or df.empty:
        return "".encode("utf-8")
    return df.to_csv(index=False).encode("utf-8")


def export_resultados_xlsx(resultados: dict) -> bytes:
    """Genera un XLSX con KPIs, entregas, evolucion OTD, alertas, bitacora y rutas."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        wb = writer.book
        title_fmt = wb.add_format({"bold": True, "font_color": "#0F172A", "font_size": 13})
        header_fmt = wb.add_format({
            "bold": True, "bg_color": "#0F172A", "font_color": "#FFFFFF",
            "border": 1,
        })

        def _write(df: pd.DataFrame, sheet: str):
            if df is None or df.empty:
                ws = wb.add_worksheet(sheet)
                ws.write(0, 0, f"Sin datos para {sheet}", title_fmt)
                return
            df.to_excel(writer, sheet_name=sheet[:31], index=False, startrow=1)
            ws = writer.sheets[sheet[:31]]
            ws.write(0, 0, sheet, title_fmt)
            for i, col in enumerate(df.columns):
                ws.write(1, i, str(col), header_fmt)
                width = min(max(12, int(df[col].astype(str).str.len().max() or 0) + 2), 36)
                ws.set_column(i, i, width)

        kpis = resultados.get("kpis") or {}
        if kpis:
            df_kpis = pd.DataFrame([{"indicador": k, "valor": v} for k, v in kpis.items()])
            _write(df_kpis, "KPIs")

        _write(resultados.get("entregas"), "Entregas")
        _write(resultados.get("evolucion_otd"), "Evolucion OTD")

        alertas = resultados.get("alertas") or []
        if alertas:
            df_alt = pd.DataFrame([{
                k: (", ".join(v) if isinstance(v, list) else v)
                for k, v in a.items()
            } for a in alertas])
            _write(df_alt, "Alertas")

        bitacora = resultados.get("bitacora") or []
        if bitacora:
            _write(pd.DataFrame(bitacora), "Bitacora")

        rutas = resultados.get("rutas_finales") or resultados.get("rutas_iniciales") or {}
        if rutas:
            rows = []
            for veh, ruta in rutas.items():
                sec = ruta.get("secuencia") if isinstance(ruta, dict) else getattr(ruta, "secuencia", [])
                for i, pid in enumerate(sec, start=1):
                    rows.append({"vehiculo_id": veh, "secuencia": i, "pedido_id": pid})
            _write(pd.DataFrame(rows), "Rutas")

        iteraciones = resultados.get("iteraciones")
        if isinstance(iteraciones, pd.DataFrame) and not iteraciones.empty:
            _write(iteraciones, "Iteraciones")

        resumen = resultados.get("resumen")
        if isinstance(resumen, pd.DataFrame) and not resumen.empty:
            _write(resumen, "Resumen escenarios")

    output.seek(0)
    return output.getvalue()


def save_outputs_to_disk(resultados: dict, prefix: str = "dss") -> Path:
    """Guarda los XLSX/CSV en data/outputs y devuelve la ruta principal."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _ts()
    xlsx_path = OUTPUTS_DIR / f"{prefix}_resultados_{ts}.xlsx"
    with open(xlsx_path, "wb") as fp:
        fp.write(export_resultados_xlsx(resultados))

    entregas = resultados.get("entregas")
    if isinstance(entregas, pd.DataFrame) and not entregas.empty:
        entregas.to_csv(OUTPUTS_DIR / f"{prefix}_entregas_{ts}.csv", index=False)

    bitacora = resultados.get("bitacora") or []
    if bitacora:
        pd.DataFrame(bitacora).to_csv(OUTPUTS_DIR / f"{prefix}_bitacora_{ts}.csv", index=False)

    return xlsx_path


def export_bitacora_csv(bitacora: list) -> bytes:
    if not bitacora:
        return "".encode("utf-8")
    return pd.DataFrame(bitacora).to_csv(index=False).encode("utf-8")


def export_alertas_csv(alertas: list) -> bytes:
    if not alertas:
        return "".encode("utf-8")
    return pd.DataFrame([{
        k: (", ".join(v) if isinstance(v, list) else v) for k, v in a.items()
    } for a in alertas]).to_csv(index=False).encode("utf-8")
