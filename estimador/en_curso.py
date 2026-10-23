"""Estimación preliminar del mes en curso (antes de que salgan los indicadores mensuales).

Mientras el mes transcurre solo hay datos diarios. Para cada indicador diario se calcula la
variación interanual del mes hasta la fecha: el promedio de los días 1 a d del mes contra el de
los mismos días un año antes (364 días, para comparar los mismos días de la semana). La
regresión de cada indicador se estima con ese mismo corte d en los meses pasados:

    y_t = a + b · x_t(hasta el día d) + c · y_(t-1) + d · h_t + e · h_(t-1)

donde y_(t-1) es la estimación del mes anterior si el EMAE todavía no salió y h la diferencia de
días hábiles contra el mismo mes del año anterior (ver calendario.py). Se combina, por la inversa
del error, con el modelo "ingenuo" (la variación del mes anterior corregida por días hábiles).

Indicadores diarios:
  - préstamos comerciales en pesos (BCRA, vía Monitor Argy), deflactados restando la variación
    interanual del IPC del mes anterior (la del mes en curso todavía no se conoce);
  - demanda eléctrica de grandes usuarios industriales (CAMMESA, vía monitor-series).
"""

import numpy as np
import pandas as pd

from estimador.modelo import MIN_OBS, _ajustar as _ajustar_modelo, _predecir

BASE_EVAL = pd.Period("2023-01", "M")


def mtd(diaria: pd.Series, mes: pd.Period, dia: int, ipc_ia: pd.Series | None = None) -> float | None:
    """Variación interanual (log ×100) del promedio de los días 1..dia del mes."""
    ini = mes.start_time
    fin = min(ini + pd.Timedelta(days=dia - 1), mes.end_time.normalize())
    cur = diaria[ini:fin]
    ant = diaria[ini - pd.Timedelta(days=364):fin - pd.Timedelta(days=364)]
    minimo = 3 if ipc_ia is not None else max(1, int(0.7 * ((fin - ini).days + 1)))
    if len(cur) < minimo or len(ant) < minimo:
        return None
    v = 100 * np.log(cur.mean() / ant.mean())
    if ipc_ia is not None:
        infl = ipc_ia.get(mes - 1)
        if infl is None or pd.isna(infl):
            return None
        v -= infl
    return float(v)


def _serie_mtd(diaria, dia, ipc_ia, hasta):
    meses = pd.period_range(diaria.index.min().to_period("M") + 12, hasta, freq="M")
    return pd.Series({m: mtd(diaria, m, dia, ipc_ia) for m in meses}, dtype=float)


def _ajustar(x, y, hasta, h):
    return _ajustar_modelo(x, y, hasta, h, min_obs=min(MIN_OBS, 18))


def _evaluar(x, y, h, ult):
    """Errores en tiempo pseudo-real (cada mes estimado solo con los anteriores)."""
    err = []
    for t in pd.period_range(BASE_EVAL, ult, freq="M"):
        bt = _ajustar(x, y, t, h)
        if bt is None or (x is not None and pd.isna(x.get(t))) or pd.isna(y.get(t - 1)) or pd.isna(y.get(t)):
            continue
        err.append(_predecir(bt, None if x is None else x[t], y[t - 1], h, t) - y[t])
    return err


def estimar_mes(mes: pd.Period, y: pd.Series, lag: float, lag_error: float,
                diarias: dict[str, tuple[pd.Series, pd.Series | None]], nombres: dict[str, str],
                h: pd.Series | None = None) -> dict | None:
    """Estimación del mes `mes` con los indicadores diarios. y: EMAE i.a. publicado; lag: y del mes anterior
    (dato o estimación); lag_error: error típico de esa estimación (0 si es dato)."""
    ult = y.last_valid_index()
    modelos, errores = {}, {}
    for nombre, (diaria, ipc_ia) in diarias.items():
        diaria = diaria.dropna()
        if diaria.empty or diaria.index.max() < mes.start_time:
            continue
        dia = int((min(diaria.index.max(), mes.end_time.normalize()) - mes.start_time).days) + 1
        x = _serie_mtd(diaria, dia, ipc_ia, mes)
        if pd.isna(x.get(mes)):
            continue
        b = _ajustar(x, y, ult + 1, h)
        if b is None:
            continue
        err = _evaluar(x, y, h, ult)  # con el mismo corte de días
        if len(err) < 12:
            continue
        modelos[nombre] = {"pronostico": _predecir(b, x[mes], lag, h, mes), "c": float(b[1]),
                           "indicador": float(x[mes]), "hasta_dia": dia, "ultimo_dato": str(diaria.index.max().date())}
        errores[nombre] = float(np.mean(np.square(err)))
    # Modelo ingenuo: la variación del mes anterior, corregida por días hábiles si hay calendario.
    if h is not None and (b := _ajustar(None, y, ult + 1, h)) is not None:
        modelos["ingenuo"] = {"pronostico": _predecir(b, None, lag, h, mes), "c": float(b[1]),
                              "indicador": None, "hasta_dia": None, "ultimo_dato": None}
        errores["ingenuo"] = float(np.mean(np.square(_evaluar(None, y, h, ult))))
    else:
        ing = [y[t - 1] - y[t] for t in pd.period_range(BASE_EVAL, ult, freq="M") if pd.notna(y.get(t)) and pd.notna(y.get(t - 1))]
        modelos["ingenuo"] = {"pronostico": float(lag), "c": 1.0, "indicador": None, "hasta_dia": None, "ultimo_dato": None}
        errores["ingenuo"] = float(np.mean(np.square(ing)))
    if len(modelos) < 2:
        return None
    inv = {m: 1 / errores[m] for m in modelos}
    tot = sum(inv.values())
    pesos = {m: v / tot for m, v in inv.items()}
    est = sum(modelos[m]["pronostico"] * w for m, w in pesos.items())
    # Error: el de la combinación (aprox. por la media ponderada de los errores) más el que arrastra
    # la estimación del mes anterior, según cuánto pesa el mes anterior en los modelos.
    rmse = float(np.sqrt(sum(w * errores[m] for m, w in pesos.items())))
    c = sum(w * modelos[m]["c"] for m, w in pesos.items())
    total = float(np.sqrt(rmse ** 2 + (c * lag_error) ** 2))
    return {
        "mes": str(mes), "estimacion": est, "error_tipico": total, "inferior": est - 1.645 * total, "superior": est + 1.645 * total,
        "inferior68": est - total, "superior68": est + total,
        "modelos": [{"modelo": m, "nombre": nombres.get(m, m), "pronostico": v["pronostico"], "peso": pesos[m],
                     "indicador": v["indicador"], "hasta_dia": v["hasta_dia"], "ultimo_dato": v["ultimo_dato"],
                     "error_tipico": float(np.sqrt(errores[m]))} for m, v in sorted(modelos.items(), key=lambda kv: -pesos[kv[0]])],
    }
