"""Estimación del EMAE (variación interanual) a partir de indicadores que se publican antes.

Método ("bridge equations" con combinación de pronósticos):
  1. Para cada indicador i, una regresión de la variación interanual del EMAE en el mes t contra
     la del indicador en el mismo mes, la del EMAE del mes anterior y la diferencia de días hábiles
     contra el mismo mes del año anterior (h), del mes y del mes previo (ver calendario.py):
         y_t = a + b · x_it + c · y_(t-1) + d · h_t + e · h_(t-1)
     Se estima con datos desde 2017, sin marzo de 2020 a junio de 2021 (pandemia).
  2. Un modelo más, el "factor": el promedio de todos los indicadores disponibles, estandarizados.
  3. Evaluación en tiempo pseudo-real: para cada mes de los últimos años, cada modelo se estima
     solo con los datos anteriores a ese mes y se mide su error.
  4. La estimación final combina los modelos disponibles para el mes que se quiere estimar,
     con pesos inversos a su error cuadrático medio de los 24 meses previos (los 8 mejores).
  5. Las bandas son ±1 y ±1,645 veces el error típico que tuvo esa misma combinación en los
     últimos 24 meses (intervalos de 68% y 90% si los errores fueran normales). cobertura() mide
     cuántas veces el dato cayó efectivamente adentro.

Las variaciones se trabajan en logaritmos (×100) y se informan como % (exp − 1).
Limitación: la evaluación usa los datos tal como están hoy (no las versiones que había en cada
momento) y supone que todos los indicadores estaban disponibles; por eso el error real puede ser
algo mayor.
"""

import numpy as np
import pandas as pd

DESDE = pd.Period("2017-01", "M")
COVID = (pd.Period("2020-03", "M"), pd.Period("2021-06", "M"))
MIN_OBS = 24
VENTANA = 24
MAX_MODELOS = 8


def _muestra(idx: pd.PeriodIndex, hasta: pd.Period) -> np.ndarray:
    return (idx >= DESDE) & (idx < hasta) & ~((idx >= COVID[0]) & (idx <= COVID[1]))


def _regresores(x: pd.Series | None, y: pd.Series, h: pd.Series | None) -> pd.DataFrame:
    d = {"y": y, "lag": y.shift(1)}
    if x is not None:
        d["x"] = x
    if h is not None:
        d["h"], d["h_lag"] = h, h.shift(1)
    return pd.DataFrame(d)


def _ajustar(x: pd.Series | None, y: pd.Series, hasta: pd.Period, h: pd.Series | None = None, min_obs: int = MIN_OBS):
    """Coeficientes [a, (b), c, (d, e)] en el orden de _regresores sin la columna y."""
    d = _regresores(x, y, h)
    d = d[_muestra(d.index, hasta)].dropna()
    if len(d) < min_obs:
        return None
    A = np.c_[np.ones(len(d)), d.drop(columns="y").values]
    b, *_ = np.linalg.lstsq(A, d["y"].values, rcond=None)
    return b


def _factor(X: pd.DataFrame, hasta: pd.Period) -> pd.Series:
    """Promedio de los indicadores estandarizados con media y desvío de la muestra de estimación."""
    m = _muestra(X.index, hasta)
    mu, sd = X[m].mean(), X[m].std()
    ok = sd.index[(sd > 0) & (X[m].notna().sum() >= MIN_OBS)]
    return ((X[ok] - mu[ok]) / sd[ok]).mean(axis=1, skipna=True).where(X[ok].notna().sum(axis=1) >= 3)


def _predecir(b, x_t, lag, h: pd.Series | None, t: pd.Period) -> float:
    v = [1.0, lag] + ([x_t] if x_t is not None else []) + ([h.get(t), h.get(t - 1)] if h is not None else [])
    return float(np.dot(b, v))


def pronosticos(X: pd.DataFrame, y: pd.Series, t: pd.Period, hasta: pd.Period, lag: float,
                h: pd.Series | None = None) -> dict[str, float]:
    """Pronóstico de cada modelo para el mes t, estimando con datos anteriores a `hasta`."""
    out = {}
    cols = {c: X[c] for c in X.columns}
    cols["factor"] = _factor(X, hasta)
    for nombre, x in cols.items():
        if t not in x.index or pd.isna(x.get(t)):
            continue
        b = _ajustar(x, y, hasta, h)
        if b is not None:
            out[nombre] = _predecir(b, x[t], lag, h, t)
    return out


def evaluar(X: pd.DataFrame, y: pd.Series, desde: str = "2021-07", h: pd.Series | None = None) -> pd.DataFrame:
    """Errores de cada modelo mes a mes (pronóstico − dato), estimando solo con el pasado."""
    ultimo = y.last_valid_index()
    filas = {}
    for t in pd.period_range(desde, ultimo, freq="M"):
        if pd.isna(y.get(t)) or pd.isna(y.get(t - 1)):
            continue
        p = pronosticos(X, y, t, t, y[t - 1], h)
        filas[t] = {m: v - y[t] for m, v in p.items()}
        filas[t]["ingenuo"] = y[t - 1] - y[t]
    return pd.DataFrame(filas).T.sort_index()


def combinar(prons: dict[str, float], errores: pd.DataFrame, hasta: pd.Period) -> tuple[float, dict[str, float]]:
    """Promedio ponderado por 1/MSE de los 24 meses anteriores a `hasta` (los mejores modelos)."""
    ventana = errores[(errores.index < hasta) & (errores.index >= hasta - VENTANA)]
    mse = {}
    for m in prons:
        if m in ventana and ventana[m].notna().sum() >= 12:
            mse[m] = float((ventana[m] ** 2).mean())
    if not mse:
        return float("nan"), {}
    mejores = sorted(mse, key=mse.get)[:MAX_MODELOS]
    inv = {m: 1 / max(mse[m], 1e-6) for m in mejores}
    tot = sum(inv.values())
    pesos = {m: v / tot for m, v in inv.items()}
    return float(sum(prons[m] * w for m, w in pesos.items())), pesos


def evaluar_combinacion(errores: pd.DataFrame, X: pd.DataFrame, y: pd.Series, modelos: list[str] | None,
                        meses: int = 24) -> pd.DataFrame:
    """Error de la combinación en los últimos `meses` (solo con los modelos `modelos`, si se indica)."""
    filas = {}
    ult = y.last_valid_index()
    for t in pd.period_range(ult - meses + 1, ult, freq="M"):
        if t not in errores.index:
            continue
        p = {m: errores.loc[t, m] + y[t] for m in errores.columns
             if m != "ingenuo" and pd.notna(errores.loc[t, m]) and (modelos is None or m in modelos)}
        est, _ = combinar(p, errores, t)
        filas[t] = {"real": y[t], "combinada": est, "ingenuo": y[t - 1]}
    return pd.DataFrame(filas).T


def cobertura(errores: pd.DataFrame, X: pd.DataFrame, y: pd.Series, meses: int = 36) -> dict:
    """Cuántas veces el dato cayó dentro de las bandas de 68% y 90%, calculando cada banda como se habría
    calculado en su momento (error típico de la combinación en los 24 meses anteriores)."""
    bt = evaluar_combinacion(errores, X, y, None, meses=meses + VENTANA)
    e = (bt["combinada"] - bt["real"]).dropna()
    dentro68, dentro90 = [], []
    for t in e.index[-meses:]:
        prev = e[(e.index < t) & (e.index >= t - VENTANA)]
        if len(prev) < 12:
            continue
        s = float(np.sqrt((prev ** 2).mean()))
        dentro68.append(abs(e[t]) <= s)
        dentro90.append(abs(e[t]) <= 1.645 * s)
    n = len(dentro90)
    return {"meses": n, "banda68": round(100 * float(np.mean(dentro68)), 1) if n else None,
            "banda90": round(100 * float(np.mean(dentro90)), 1) if n else None}


def estimar(X: pd.DataFrame, y: pd.Series, h: pd.Series | None = None) -> dict:
    """Estimación de los meses posteriores al último EMAE publicado."""
    errores = evaluar(X, y, h=h)
    ult = y.last_valid_index()
    resultado = {"ultimo_emae": str(ult), "meses": []}
    yy = y.copy()
    t = ult + 1
    while True:
        lag = yy.get(t - 1)
        prons = pronosticos(X, yy, t, ult + 1, lag, h)
        if len([m for m in prons if m != "factor"]) < 3:
            break
        est, pesos = combinar(prons, errores, ult + 1)
        bt = evaluar_combinacion(errores, X, y, list(prons))
        rmse = float(np.sqrt(((bt["combinada"] - bt["real"]) ** 2).mean()))
        rmse_ing = float(np.sqrt(((bt["ingenuo"] - bt["real"]) ** 2).mean()))
        resultado["meses"].append({
            "mes": str(t), "estimacion": est, "error_tipico": rmse, "error_ingenuo": rmse_ing,
            "inferior": est - 1.645 * rmse, "superior": est + 1.645 * rmse,
            "inferior68": est - rmse, "superior68": est + rmse,
            "modelos": [{"modelo": m, "pronostico": prons[m], "peso": pesos.get(m, 0.0),
                         "indicador": (float(X.loc[t, m]) if m in X and pd.notna(X.loc[t, m]) else None)}
                        for m in sorted(prons, key=lambda m: -pesos.get(m, 0))],
            "disponibles": sorted(c for c in X.columns if pd.notna(X[c].get(t))),
        })
        yy.loc[t] = est
        t += 1
    resultado["errores"] = errores
    return resultado
