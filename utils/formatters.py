"""Formateadores para fechas, horas, numeros y porcentajes."""


def fmt_pct(value, decimals: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{decimals}f}%"


def fmt_num(value, decimals: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"


def fmt_int(value) -> str:
    if value is None:
        return "-"
    return f"{int(value):,}".replace(",", " ")


def fmt_minutes(minutes) -> str:
    if minutes is None:
        return "-"
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    if h == 0:
        return f"{m} min"
    return f"{h}h {m:02d}min"


def fmt_hora(hhmm: str) -> str:
    return hhmm if hhmm else "-"


def hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def minutes_to_hhmm(total_minutes: int) -> str:
    total_minutes = int(total_minutes) % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def fmt_kg(value) -> str:
    if value is None:
        return "-"
    return f"{value:.1f} kg"


def fmt_km(value) -> str:
    if value is None:
        return "-"
    return f"{value:.2f} km"


def fmt_coord(lat, lon) -> str:
    return f"{lat:.4f}, {lon:.4f}"
