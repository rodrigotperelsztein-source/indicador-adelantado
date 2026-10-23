"""Aporte estimado de la cosecha a la variación interanual del EMAE.

INDEC asigna la producción de cada campaña agrícola a los meses en que se cosecha: por eso el EMAE
salta en abril-junio según cómo vino la soja y el maíz, algo que el EMAE del mes anterior y los demás
indicadores no anticipan. Acá se reproduce esa lógica de forma simplificada:

  1. Producción de soja, maíz, trigo y girasol por campaña (Secretaría de Agricultura, vía la API de
     series de datos.gob.ar; la última campaña es la estimación vigente).
  2. Cada cultivo se reparte en los meses de cosecha con un calendario típico (CALENDARIO) y se valúa con
     un precio de referencia fijo (PRECIO, solo para ponderar los cultivos entre sí).
  3. La variación interanual de ese valor cosechado en el mes se multiplica por el peso relativo del agro
     en el EMAE de ese mes (PESO_AGRO): es el regresor k_t que entra en todos los modelos.

Si falta la producción de una campaña para un cultivo (p. ej. la que todavía no se estimó), se usa la de la
campaña anterior: ese cultivo aporta cero variación y queda anotado como aviso. data/cosecha_manual.csv
permite cargar a mano una estimación más nueva (de la Secretaría o de la Bolsa de Cereales), que tiene
prioridad sobre la de la API.
"""

import io
from pathlib import Path

import numpy as np
import pandas as pd

from estimador import datos

API = ("https://apis.datos.gob.ar/series/api/series/?ids=34.2_STSOJ_0_P_16,34.2_MTMAI_0_P_16,34.2_TTTRI_0_P_17,"
       "34.2_GTGIR_0_P_19&start_date=2000-01-01&format=csv")
COLUMNAS = {"soja_toneladadas": "soja", "maiz_toneladadas": "maiz", "trigo_toneladadas": "trigo",
            "girasol_toneladadas": "girasol"}
MANUAL = datos.RAIZ / "data" / "cosecha_manual.csv"

# Parte de la cosecha de cada cultivo que se levanta en cada mes (calendario típico de la región pampeana).
CALENDARIO = {
    "soja": {3: .03, 4: .45, 5: .42, 6: .08, 7: .02},
    "maiz": {3: .08, 4: .20, 5: .15, 6: .17, 7: .20, 8: .12, 9: .06, 10: .02},
    "girasol": {1: .10, 2: .30, 3: .35, 4: .20, 5: .05},
    "trigo": {11: .15, 12: .65, 1: .20},
}
PRECIO = {"soja": 350, "maiz": 180, "trigo": 220, "girasol": 380}  # US$/t de referencia, solo como ponderador
# Peso relativo del agro en el EMAE por mes: promedio 2004-2026 del índice del sector A sobre el EMAE total
# (ambos base 2004 = 100). La escala no importa: la regresión estima el coeficiente.
PESO_AGRO = {1: .57, 2: .57, 3: .99, 4: 1.42, 5: 1.87, 6: 1.33, 7: .79, 8: .53, 9: .50, 10: .51, 11: .62, 12: .73}


def bajar(local: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Producción por campaña (índice: año de inicio de la campaña; 2025 = 2025/26) y avisos."""
    archivo, avisos = datos.INSUMOS / "cosecha.csv", []
    try:
        contenido = (Path(local) / "cosecha_api.csv").read_bytes() if local else datos._get(API)
        d = pd.read_csv(io.BytesIO(contenido))
        d["campania"] = pd.to_datetime(d["indice_tiempo"]).dt.year
        prod = d.set_index("campania").rename(columns=COLUMNAS)[list(COLUMNAS.values())].astype(float)
        if len(prod) < 10:
            raise ValueError(f"solo {len(prod)} campañas")
        prod.to_csv(archivo)
    except Exception as e:  # noqa: BLE001
        if not archivo.exists():
            return pd.DataFrame(columns=list(COLUMNAS.values()), dtype=float), [f"cosecha: no se pudo bajar ({e})"]
        avisos.append(f"cosecha: se usa la copia anterior ({e})")
        prod = pd.read_csv(archivo, index_col="campania").astype(float)
    if MANUAL.exists():
        m = pd.read_csv(MANUAL, comment="#")
        for r in m.itertuples():
            prod.loc[int(r.campania), str(r.cultivo)] = float(r.toneladas)
    return prod.sort_index(), avisos


def _campania(cultivo: str, t: pd.Period) -> int:
    # El trigo de noviembre y diciembre es de la campaña que empieza ese año; el resto, de la que empezó el anterior.
    return t.year if (cultivo == "trigo" and t.month >= 11) else t.year - 1


def aporte(idx: pd.PeriodIndex, prod: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    """Regresor k_t para cada mes de idx, y avisos sobre campañas sin estimación."""
    faltan = set()

    def valor(t: pd.Period, completar: bool) -> float:
        v = 0.0
        for c, cal in CALENDARIO.items():
            if t.month not in cal:
                continue
            k = _campania(c, t)
            p = prod[c].get(k, np.nan) if c in prod else np.nan
            ultima = prod[c].last_valid_index() if c in prod else None
            if pd.isna(p) and completar and ultima is not None and k > ultima:
                # campaña todavía sin estimación: se repite la última conocida (el cultivo no aporta variación)
                p = prod[c][ultima]
                faltan.add(f"{c} {k}/{str(k + 1)[2:]}")
            if pd.isna(p):
                return np.nan
            v += PRECIO[c] * cal[t.month] * p
        return v

    k = {}
    for t in idx:
        act, ant = valor(t, True), valor(t - 12, False)
        k[t] = 100 * np.log(act / ant) * PESO_AGRO[t.month] if act and ant and not np.isnan(act + ant) else np.nan
    avisos = [f"cosecha: sin estimación de {', '.join(sorted(faltan))}; se repite la campaña anterior"] if faltan else []
    return pd.Series(k, dtype=float), avisos
