"""Baja los insumos (series de monitor-series y de Monitor Argy) y los guarda en data/insumos/.

Solo lee archivos públicos por HTTPS; no usa credenciales. Si una fuente falla, se usa la copia
guardada en la corrida anterior y queda anotado.
"""

import io
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from estimador.indicadores import INDICADORES, OBJETIVO, Indicador

RAIZ = Path(__file__).resolve().parent.parent
INSUMOS = RAIZ / "data" / "insumos"
MONITOR = "https://raw.githubusercontent.com/rodrigotperelsztein-source/monitor-series/main/data/series/{}.csv"
MA = "https://monitorargy.com/api/v1/series/{}"
UA = "indicador-adelantado (github.com/rodrigotperelsztein-source/indicador-adelantado)"


def _get(url: str) -> bytes:
    ultimo = None
    for i in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            r.raise_for_status()
            return r.content
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"No pude bajar {url}: {ultimo}")


def _leer(ind: Indicador, contenido: bytes) -> pd.Series:
    if ind.fuente == "monitor":
        d = pd.read_csv(io.BytesIO(contenido), parse_dates=["fecha"])
        s = pd.Series(d["valor"].values, index=d["fecha"].dt.to_period("M"))
    else:
        j = json.loads(contenido)
        pts = [p for p in j["puntos"] if p.get("valor") is not None]
        s = pd.Series({pd.Period(p["fecha"][:7], "M"): float(p["valor"]) for p in pts})
    s = s.groupby(level=0).last().sort_index()
    if len(s) < 12:
        raise ValueError(f"{ind.id}: serie demasiado corta ({len(s)} datos)")
    return s


def bajar(local: str | None = None) -> tuple[dict[str, pd.Series], list[str]]:
    """Series en niveles (o como las publica la fuente), por id. local: carpeta con copias, para pruebas."""
    INSUMOS.mkdir(parents=True, exist_ok=True)
    series, avisos = {}, []
    for ind in [OBJETIVO, *INDICADORES]:
        archivo = INSUMOS / f"{ind.id}.csv"
        try:
            if local:
                p = Path(local) / (f"{ind.serie}.csv" if ind.fuente == "monitor" else f"{ind.serie}.json")
                contenido = p.read_bytes()
            else:
                contenido = _get(MONITOR.format(ind.serie) if ind.fuente == "monitor" else MA.format(ind.serie))
                if ind.fuente == "ma":
                    time.sleep(0.5)  # Monitor Argy permite 30 consultas cada 10 segundos
            s = _leer(ind, contenido)
            s.rename("valor").rename_axis("fecha").to_frame().to_csv(archivo)
        except Exception as e:  # noqa: BLE001
            if ind is OBJETIVO and not archivo.exists():
                raise
            if not archivo.exists():
                avisos.append(f"{ind.id}: no se pudo bajar y no hay copia anterior ({e})")
                continue
            avisos.append(f"{ind.id}: se usa la copia anterior ({e})")
            d = pd.read_csv(archivo)
            s = pd.Series(d["valor"].values, index=pd.PeriodIndex(d["fecha"], freq="M"))
        series[ind.id] = s
    return series, avisos


MONITOR_DATA = "https://raw.githubusercontent.com/rodrigotperelsztein-source/monitor-series/main/data/{}.csv"
DIARIAS = {  # id: (descripción, origen)
    "prestamos_diario": "Préstamos comerciales en pesos, saldo diario (BCRA, vía Monitor Argy)",
    "electricidad_industria_diaria": "Demanda eléctrica diaria de grandes usuarios industriales (CAMMESA, vía monitor-series)",
}


def bajar_diarias(local: str | None = None) -> tuple[dict[str, pd.Series], pd.Series | None, list[str]]:
    """Series diarias para la estimación del mes en curso y el IPC (para deflactar los préstamos)."""
    avisos, out, ipc = [], {}, None
    pedidos = {
        "prestamos_diario": (MA.format("prestamos_comerciales") + "?resolucion=1d", "prestamos_comerciales_diaria.json"),
        "electricidad_industria_diaria": (MONITOR_DATA.format("cammesa_gu_actividad"), "cammesa_gu_actividad.csv"),
        "ipc": (MA.format("ipc_nivel_general"), "ipc_nivel_general.json"),
    }
    for nombre, (url, archivo_local) in pedidos.items():
        archivo = INSUMOS / f"{nombre}.csv"
        try:
            contenido = (Path(local) / archivo_local).read_bytes() if local else _get(url)
            if url.startswith(MA[:30]):
                pts = [p for p in json.loads(contenido)["puntos"] if p.get("valor") is not None]
                s = pd.Series({pd.Timestamp(p["fecha"][:10]): float(p["valor"]) for p in pts}).sort_index()
                if not local:
                    time.sleep(0.5)
            else:
                d = pd.read_csv(io.BytesIO(contenido), parse_dates=["fecha"])
                s = pd.Series(d["industrias"].values, index=d["fecha"]).sort_index()
            s.rename("valor").rename_axis("fecha").to_frame().to_csv(archivo)
        except Exception as e:  # noqa: BLE001
            if not archivo.exists():
                avisos.append(f"{nombre}: no se pudo bajar y no hay copia anterior ({e})")
                continue
            avisos.append(f"{nombre}: se usa la copia anterior ({e})")
            d = pd.read_csv(archivo, parse_dates=["fecha"])
            s = pd.Series(d["valor"].values, index=d["fecha"])
        if nombre == "ipc":
            s.index = s.index.to_period("M")
            ipc = 100 * np.log(s / s.shift(12))
        else:
            out[nombre] = s
    return out, ipc, avisos


def interanual(s: pd.Series, transformacion: str) -> pd.Series:
    """Variación interanual comparable con la del EMAE (ver indicadores.py)."""
    s = s.copy()
    s.index = pd.PeriodIndex(s.index, freq="M")
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
    if transformacion == "nivel":
        return 100 * np.log(s.where(s > 0) / s.where(s > 0).shift(12))
    if transformacion == "var_ia":
        return 100 * np.log1p(s / 100)
    if transformacion == "dif12":
        return s - s.shift(12)
    raise ValueError(transformacion)


if __name__ == "__main__":
    series, avisos = bajar(os.environ.get("INSUMOS_LOCAL"))
    print({k: str(v.index.max()) for k, v in series.items()}, avisos)
