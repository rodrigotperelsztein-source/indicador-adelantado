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

from estimador import calendario, datos, en_curso, modelo
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
    h = calendario.diferencia_interanual(pd.period_range("2005-01", fin + 3, freq="M"))

    r = modelo.estimar(X, y, h)
    errores = r.pop("errores")
    nombres = {i.id: i.nombre for i in INDICADORES} | {"factor": "Factor común (promedio de todos los indicadores)"}
    grupos = {i.id: i.grupo for i in INDICADORES} | {"factor": "Todos"}

    # Evaluación de cada modelo (últimos 24 meses) y correlación con el EMAE.
    ult = y.last_valid_index()
    rec = errores[errores.index > ult - 24]
    eval_modelos = {m: round(float(np.sqrt((rec[m] ** 2).mean())), 2) for m in rec.columns if rec[m].notna().sum() >= 12}
    bt = modelo.evaluar_combinacion(errores, X, y, None, meses=36)
    cobertura = modelo.cobertura(errores, X, y)

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
            "inferior68": pct(mm["inferior68"]), "superior68": pct(mm["superior68"]),
            "dias_habiles_vs_anio_anterior": int(h[pd.Period(mm["mes"], "M")]),
            "error_tipico": round(mm["error_tipico"], 2), "error_ingenuo": round(mm["error_ingenuo"], 2),
            "indicadores_disponibles": len(mm["disponibles"]), "indicadores_totales": len(X.columns),
            "disponibles": mm["disponibles"],
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
        "cobertura_bandas_36m": cobertura,
        "indicadores": indicadores,
        "avisos": avisos,
    }
    for mm in salida["meses"]:
        mm["preliminar"] = False

    # Mes en curso (o ya terminado sin indicadores mensuales): estimación con datos diarios.
    diarias, ipc_ia, av2 = datos.bajar_diarias(os.environ.get("INSUMOS_LOCAL"))
    salida["avisos"] += av2
    hoy = ahora.astimezone(ZoneInfo("America/Argentina/Buenos_Aires"))
    previo = r["meses"][-1] if r["meses"] else None
    mes_ec = (pd.Period(previo["mes"], "M") if previo else ult) + 1
    if mes_ec <= pd.Period(hoy.strftime("%Y-%m"), "M"):
        lag = previo["estimacion"] if previo else y[ult]
        lag_err = previo["error_tipico"] if previo else 0.0
        insumos = {"prestamos_diario": (diarias["prestamos_diario"], ipc_ia)} if "prestamos_diario" in diarias and ipc_ia is not None else {}
        if "electricidad_industria_diaria" in diarias:
            insumos["electricidad_industria_diaria"] = (diarias["electricidad_industria_diaria"], None)
        nom_d = {"prestamos_diario": "Préstamos comerciales reales (mes hasta la fecha)",
                 "electricidad_industria_diaria": "Electricidad de grandes usuarios industriales (mes hasta la fecha)",
                 "ingenuo": "Repetir la variación del mes anterior"}
        nom_d["ingenuo"] = "Variación del mes anterior, corregida por días hábiles"
        ec = en_curso.estimar_mes(mes_ec, y, lag, lag_err, insumos, nom_d, h)
        if ec:
            salida["meses"].append({
                "mes": ec["mes"], "preliminar": True, "estimacion": pct(ec["estimacion"]), "inferior": pct(ec["inferior"]),
                "superior": pct(ec["superior"]), "inferior68": pct(ec["inferior68"]), "superior68": pct(ec["superior68"]),
                "dias_habiles_vs_anio_anterior": int(h[mes_ec]),
                "error_tipico": round(ec["error_tipico"], 2), "error_ingenuo": None,
                "indicadores_disponibles": len(ec["modelos"]) - 1, "indicadores_totales": len(insumos),
                "disponibles": [m["modelo"] for m in ec["modelos"] if m["modelo"] != "ingenuo"],
                "modelos": [{"id": m["modelo"], "nombre": m["nombre"], "grupo": "Mes en curso", "pronostico": pct(m["pronostico"]),
                             "peso": round(m["peso"], 4), "indicador": pct(m["indicador"]), "hasta_dia": m["hasta_dia"],
                             "ultimo_dato": m["ultimo_dato"], "error_tipico": round(m["error_tipico"], 2)} for m in ec["modelos"]],
            })

    # Acumulado del año: dato oficial y con los meses estimados.
    niv = series[OBJETIVO.id].copy()
    niv.index = pd.PeriodIndex(niv.index, freq="M")
    anio = ult.year
    def acumulado(niveles):
        meses = [m for m in niveles if m.year == anio]
        act = sum(niveles[m] for m in meses)
        ant = sum(niv[m - 12] for m in meses)
        return round(float((act / ant - 1) * 100), 2), str(max(meses))
    base = {m: niv[m] for m in niv.index if m.year == anio and m <= ult}
    real, hasta = acumulado(base)
    salida["acumulado"] = {"anio": anio, "real": {"hasta": hasta, "valor": real}, "estimados": []}
    centro, bajo, alto = dict(base), dict(base), dict(base)
    for mm in salida["meses"]:
        m = pd.Period(mm["mes"], "M")
        if m.year != anio:
            break
        for d, k in ((centro, "estimacion"), (bajo, "inferior"), (alto, "superior")):
            d[m] = niv[m - 12] * (1 + mm[k] / 100)
        v, h = acumulado(centro)
        salida["acumulado"]["estimados"].append({"hasta": h, "valor": v, "inferior": acumulado(bajo)[0],
                                                 "superior": acumulado(alto)[0], "preliminar": mm["preliminar"]})
    errores.rename_axis("mes").round(4).to_csv(DATA / "evaluacion.csv")

    # Historial: solo se agrega una fila si la estimación de ese mes cambió.
    p_hist = DATA / "historial.csv"
    hist = pd.read_csv(p_hist, dtype={"mes": str}) if p_hist.exists() else pd.DataFrame(
        columns=["corrida", "mes", "estimacion", "inferior", "superior", "inferior68", "superior68", "indicadores_disponibles", "ultimo_emae"])
    for c in ("indicadores", "nuevos", "inferior68", "superior68"):
        if c not in hist:
            hist[c] = ""
    hist[["indicadores", "nuevos"]] = hist[["indicadores", "nuevos"]].fillna("")
    nuevas = []
    for mm in salida["meses"]:
        prev = hist[hist["mes"] == mm["mes"]].tail(1)
        antes = set(filter(None, str(prev["indicadores"].iloc[0]).split("|"))) if not prev.empty else set()
        nuevos = [i for i in mm["disponibles"] if i not in antes] if antes else []
        if prev.empty or abs(float(prev["estimacion"].iloc[0]) - mm["estimacion"]) > 0.005 \
                or set(mm["disponibles"]) != antes:
            nuevas.append({"corrida": salida["corrida"], "mes": mm["mes"], "estimacion": mm["estimacion"],
                           "inferior": mm["inferior"], "superior": mm["superior"],
                           "inferior68": mm["inferior68"], "superior68": mm["superior68"],
                           "indicadores_disponibles": mm["indicadores_disponibles"], "ultimo_emae": salida["ultimo_emae"],
                           "indicadores": "|".join(mm["disponibles"]), "nuevos": "|".join(nuevos)})
    if nuevas:
        hist = pd.concat([hist, pd.DataFrame(nuevas)], ignore_index=True)
        hist.to_csv(p_hist, index=False)

    # Variación trimestral desestacionalizada: oficial y con los meses estimados. La serie desestacionalizada
    # de los meses estimados se aproxima con el factor estacional del mismo mes del año anterior
    # (original / desestacionalizada de INDEC).
    try:
        loc = os.environ.get("INSUMOS_LOCAL")
        contenido = (datos.Path(loc) / "emae.desest.csv").read_bytes() if loc else datos._get(datos.MONITOR.format("emae.desest"))
        des = pd.read_csv(datos.io.BytesIO(contenido), parse_dates=["fecha"])
        des = pd.Series(des["valor"].values, index=des["fecha"].dt.to_period("M"))
        tipo = {m: "oficial" for m in des.index}
        err_mes = {}
        for mm in salida["meses"]:
            err_mes[pd.Period(mm["mes"], "M")] = mm["error_tipico"]
            m = pd.Period(mm["mes"], "M")
            factor = niv[m - 12] / des[m - 12]
            des[m] = niv[m - 12] * (1 + mm["estimacion"] / 100) / factor
            tipo[m] = "preliminar" if mm["preliminar"] else "estimado"
        des = des.sort_index()
        q = pd.DataFrame({"v": des, "t": pd.Series(tipo)}).dropna(subset=["v"])
        q["trim"] = [f"{m.year}-T{m.quarter}" for m in q.index]
        trims = []
        for k, g in q.groupby("trim", sort=True):
            trims.append({"trimestre": k, "nivel": float(g["v"].mean()), "meses": len(g),
                          "oficiales": int((g["t"] == "oficial").sum()), "estimados": int((g["t"] == "estimado").sum()),
                          "preliminares": int((g["t"] == "preliminar").sum())})
        for i in range(1, len(trims)):
            trims[i]["variacion"] = round((trims[i]["nivel"] / trims[i - 1]["nivel"] - 1) * 100, 2)
            # Error de la variación trimestral: cada mes estimado pesa un tercio en el promedio del trimestre. Se suman
            # los errores de los meses (como si estuvieran perfectamente correlacionados, que es lo más prudente).
            y_, q_ = map(int, trims[i]["trimestre"].split("-T"))
            e = sum(err_mes.get(pd.Period(f"{y_}-{3 * (q_ - 1) + k:02d}", "M"), 0.0) for k in (1, 2, 3)) / 3
            if e > 0:
                v = trims[i]["variacion"]
                trims[i].update({"error_tipico": round(e, 2), "inferior": round(v - 1.645 * e, 2), "superior": round(v + 1.645 * e, 2)})
        trims = trims[-8:]
        for t in trims:
            t["nivel"] = round(t["nivel"], 2)
        completos = [t for t in trims if t["meses"] == 3 and "variacion" in t]
        salida["trimestres"] = trims
        salida["recesion_tecnica"] = len(completos) >= 2 and completos[-1]["variacion"] < 0 and completos[-2]["variacion"] < 0
        # ¿Se sostiene aun en el extremo optimista de la banda de 90%?
        salida["recesion_tecnica_robusta"] = salida["recesion_tecnica"] and all(t.get("superior", t["variacion"]) < 0 for t in completos[-2:])
        print("Trimestres (desest., var. %):", ", ".join(f"{t['trimestre']} {t.get('variacion', 0):+.2f}"
                                                      + ("" if t['meses'] == 3 else f" ({t['meses']} meses)") for t in trims[-4:]))
    except Exception as e:  # noqa: BLE001
        salida["avisos"].append(f"trimestres: no se pudo calcular ({e})")

    # Solo se reescribe si cambió algo además de la hora de la corrida (así no hay un commit por corrida).
    p_est = DATA / "estimacion.json"
    sin_hora = lambda d: {k: v for k, v in d.items() if k not in ("corrida", "corrida_local")}  # noqa: E731
    previa = json.loads(p_est.read_text(encoding="utf-8")) if p_est.exists() else {}
    if sin_hora(previa) != json.loads(json.dumps(sin_hora(salida), ensure_ascii=False)):
        p_est.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    a = salida["acumulado"]
    print(f"Acumulado {a['anio']} hasta {a['real']['hasta']}: {a['real']['valor']:+.2f}%; " +
          "; ".join(f"con {e['hasta']}: {e['valor']:+.2f}%" for e in a["estimados"]))
    for mm in salida["meses"]:
        print(f"{mm['mes']}{' (preliminar)' if mm['preliminar'] else ''}: {mm['estimacion']:+.1f}% i.a. (entre {mm['inferior']:+.1f}% y {mm['superior']:+.1f}%), "
              f"{mm['indicadores_disponibles']}/{mm['indicadores_totales']} indicadores, error típico {mm['error_tipico']} pp")
    print(f"Evaluación 36 meses: combinada {salida['error_tipico_combinada_36m']} pp, ingenuo {salida['error_tipico_ingenuo_36m']} pp; "
          f"el dato cayó dentro de la banda de 68% el {cobertura['banda68']}% de las veces y de la de 90% el {cobertura['banda90']}% "
          f"({cobertura['meses']} meses)")
    for a in avisos:
        print("AVISO:", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
