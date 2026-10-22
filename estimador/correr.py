"""Corrida completa: baja los insumos, estima y guarda los resultados en data/.

  data/estimacion.json   última estimación (meses sin EMAE publicado), con el aporte de cada
                         modelo, la evaluación y el estado de cada indicador; la lee la página.
  data/historial.csv     cada estimación nueva que se hizo (para ver cómo cambia con los datos
                         y compararla con el EMAE cuando sale).
  data/evaluacion.csv    error de cada modelo mes a mes en la evaluación en tiempo pseudo-real.
  data/insumos/          copia de las series usadas.

Uso: python -m estimador.correr   (INSUMOS_LOCAL=<carpeta> para probar con copias locales)
"""

import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from estimador import datos, modelo
from estimador.indicadores import INDICADORES, OBJETIVO

DATA = datos.RAIZ / "data"
pct = lambda v: None if v is None or pd.isna(v) else round(float(np.expm1(v / 100) * 100), 2)  # noqa: E731


def main() -> int:
    ahora = datetime.now(timezone.utc)
    series, avisos = datos.bajar(os.environ.get("INSUMOS_LOCAL"))
    y = datos.interanual(series[OBJETIVO.id], OBJETIVO.transformacion)
    X = pd.DataFrame({i.id: datos.interanual(series[i.id], i.transformacion) for i in INDICADORES if i.id in series})
    fin = max(X.index.max(), y.index.max() + 1)
    idx = pd.period_range("2005-01", fin, freq="M")
    X, y = X.reindex(idx), y.reindex(idx)

    r = modelo.estimar(X, y)
    errores = r.pop("errores")
    nombres = {i.id: i.nombre for i in INDICADORES} | {"factor": "Factor común (promedio de todos los indicadores)"}
    grupos = {i.id: i.grupo for i in INDICADORES} | {"factor": "Todos"}

    # Evaluación de cada modelo (últimos 24 meses) y correlación con el EMAE.
    ult = y.last_valid_index()
    rec = errores[errores.index > ult - 24]
    eval_modelos = {m: round(float(np.sqrt((rec[m] ** 2).mean())), 2) for m in rec.columns if rec[m].notna().sum() >= 12}
    bt = modelo.evaluar_combinacion(errores, X, y, None, meses=36)

    indicadores = []
    for i in INDICADORES:
        if i.id not in series:
            continue
        x = X[i.id]
        u = x.last_valid_index()
        m = (x.index >= pd.Period("2023-01", "M")) & x.notna() & y.notna()
        indicadores.append({
            "id": i.id, "nombre": i.nombre, "grupo": i.grupo, "fuente": "monitor-series" if i.fuente == "monitor" else "Monitor Argy",
            "serie": i.serie, "ultimo_mes": str(u) if u is not None else None,
            "variacion_ultimo": (pct(x[u]) if i.transformacion != "dif12" else round(float(x[u]), 2)) if u is not None else None,
            "unidad_variacion": "puntos" if i.transformacion == "dif12" else "%",
            "correlacion": round(float(x[m].corr(y[m])), 2) if m.sum() >= 12 else None,
            "error_tipico": eval_modelos.get(i.id),
        })

    salida = {
        "corrida": ahora.isoformat(timespec="seconds"),
        "corrida_local": ahora.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%d/%m/%Y %H:%M"),
        "ultimo_emae": r["ultimo_emae"],
        "meses": [{
            "mes": mm["mes"], "estimacion": pct(mm["estimacion"]), "inferior": pct(mm["inferior"]), "superior": pct(mm["superior"]),
            "error_tipico": round(mm["error_tipico"], 2), "error_ingenuo": round(mm["error_ingenuo"], 2),
            "indicadores_disponibles": len(mm["disponibles"]), "indicadores_totales": len(X.columns),
            "modelos": [{"id": mo["modelo"], "nombre": nombres.get(mo["modelo"], mo["modelo"]), "grupo": grupos.get(mo["modelo"], ""),
                         "pronostico": pct(mo["pronostico"]), "peso": round(mo["peso"], 4), "indicador": pct(mo["indicador"])
                         if mo["indicador"] is not None and mo["modelo"] != "capacidad" else mo["indicador"],
                         "error_tipico": eval_modelos.get(mo["modelo"])} for mo in mm["modelos"]],
        } for mm in r["meses"]],
        "emae": [{"mes": str(p), "variacion": pct(v)} for p, v in y[y.index >= pd.Period("2017-01", "M")].dropna().items()],
        "evaluacion": [{"mes": str(p), "real": pct(f["real"]), "estimada": pct(f["combinada"]), "ingenuo": pct(f["ingenuo"])}
                       for p, f in bt.iterrows()],
        "error_tipico_combinada_36m": round(float(np.sqrt(((bt["combinada"] - bt["real"]) ** 2).mean())), 2),
        "error_tipico_ingenuo_36m": round(float(np.sqrt(((bt["ingenuo"] - bt["real"]) ** 2).mean())), 2),
        "indicadores": indicadores,
        "avisos": avisos,
    }
    (DATA / "estimacion.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    errores.rename_axis("mes").round(4).to_csv(DATA / "evaluacion.csv")

    # Historial: solo se agrega una fila si la estimación de ese mes cambió.
    p_hist = DATA / "historial.csv"
    hist = pd.read_csv(p_hist, dtype={"mes": str}) if p_hist.exists() else pd.DataFrame(
        columns=["corrida", "mes", "estimacion", "inferior", "superior", "indicadores_disponibles", "ultimo_emae"])
    nuevas = []
    for mm in salida["meses"]:
        prev = hist[hist["mes"] == mm["mes"]].tail(1)
        if prev.empty or abs(float(prev["estimacion"].iloc[0]) - mm["estimacion"]) > 0.005 \
                or int(prev["indicadores_disponibles"].iloc[0]) != mm["indicadores_disponibles"]:
            nuevas.append({"corrida": salida["corrida"], "mes": mm["mes"], "estimacion": mm["estimacion"],
                           "inferior": mm["inferior"], "superior": mm["superior"],
                           "indicadores_disponibles": mm["indicadores_disponibles"], "ultimo_emae": salida["ultimo_emae"]})
    if nuevas:
        hist = pd.concat([hist, pd.DataFrame(nuevas)], ignore_index=True)
        hist.to_csv(p_hist, index=False)

    for mm in salida["meses"]:
        print(f"{mm['mes']}: {mm['estimacion']:+.1f}% i.a. (entre {mm['inferior']:+.1f}% y {mm['superior']:+.1f}%), "
              f"{mm['indicadores_disponibles']}/{mm['indicadores_totales']} indicadores, error típico {mm['error_tipico']} pp")
    print(f"Evaluación 36 meses: combinada {salida['error_tipico_combinada_36m']} pp, ingenuo {salida['error_tipico_ingenuo_36m']} pp")
    for a in avisos:
        print("AVISO:", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
