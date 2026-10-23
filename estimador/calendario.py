"""Días hábiles de cada mes, para corregir el efecto calendario en la variación interanual del EMAE.

Un mes con más días hábiles que el mismo mes del año anterior (por cómo caen los fines de semana,
Semana Santa, Carnaval o los feriados puente) muestra más actividad aunque la economía no haya
cambiado. Las regresiones del modelo incluyen la diferencia de días hábiles contra el mismo mes del
año anterior, la del mes estimado y la del mes previo (porque la variación del mes previo, que entra
como regresor, trae su propio efecto calendario).

Día hábil: lunes a viernes que no es feriado nacional ni día no laborable con fines turísticos.
Los feriados salen de la librería `holidays`; CORRECCIONES agrega los traslados que le faltan.
"""

from datetime import date

import holidays
import pandas as pd

# Traslados decretados que la librería no tiene (fecha: motivo). Revisar cuando se decreten nuevos.
CORRECCIONES = {
    date(2025, 10, 10): "Día del Respeto a la Diversidad Cultural (trasladado del domingo 12/10)",
}


def dias_habiles(desde: str, hasta: str) -> pd.Series:
    meses = pd.period_range(desde, hasta, freq="M")
    fer = holidays.Argentina(years=range(meses[0].year, meses[-1].year + 1))
    fer.update(CORRECCIONES)
    out = {}
    for m in meses:
        dias = pd.date_range(m.start_time, m.end_time, freq="D")
        out[m] = sum(1 for d in dias if d.weekday() < 5 and d.date() not in fer)
    return pd.Series(out, dtype=float)


def diferencia_interanual(idx: pd.PeriodIndex) -> pd.Series:
    """Días hábiles del mes menos los del mismo mes del año anterior, para cada mes de idx."""
    h = dias_habiles(str(idx.min() - 12), str(idx.max()))
    return (h - h.shift(12)).reindex(idx)
