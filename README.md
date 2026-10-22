# Indicador adelantado del EMAE

Estimación de la variación interanual del **EMAE** (Estimador Mensual de Actividad Económica, INDEC)
antes de que se publique, con indicadores que salen antes: importaciones, cemento, Construya, ventas
de combustibles, recaudación, producción automotriz y metalúrgica, ventas minoristas pyme (CAME),
patentamientos, crédito y otros.

**Página:** https://rodrigotperelsztein-source.github.io/indicador-adelantado/

## Cómo funciona

1. `estimador/datos.py` baja los indicadores de [monitor-series](https://github.com/rodrigotperelsztein-source/monitor-series)
   (`data/series/<id>.csv`) y de la API pública de [Monitor Argy](https://monitorargy.com), y guarda una copia en `data/insumos/`.
2. `estimador/modelo.py` estima, para cada indicador, una regresión de la variación interanual del EMAE contra la del
   indicador y la del EMAE del mes anterior (desde 2017, sin la pandemia), más un "factor común" con el promedio de todos.
   Cada modelo se evalúa en tiempo pseudo-real (cada mes estimado solo con datos anteriores) y la estimación final
   combina los 8 mejores de los que ya tienen dato del mes, con pesos inversos a su error de los últimos 24 meses.
   La banda es ±1,645 errores típicos de esa combinación (90%).
3. `estimador/correr.py` guarda los resultados:

| Archivo | Contenido |
|---|---|
| `data/estimacion.json` | Estimación actual (cada mes sin EMAE publicado con al menos 3 indicadores), aporte y peso de cada modelo, evaluación, estado de cada indicador |
| `data/historial.csv` | Cada versión de la estimación (cambia cuando entra un dato), para compararla con el EMAE publicado |
| `data/evaluacion.csv` | Error de cada modelo, mes a mes, en la evaluación en tiempo pseudo-real |
| `data/insumos/` | Copia de las series usadas |

Para sumar un indicador alcanza con agregarlo en `estimador/indicadores.py`: el modelo mide solo cuánto acierta y le
da peso según eso. Las series nuevas conviene sumarlas primero a monitor-series.

## Cuándo corre

GitHub Actions (`.github/workflows/estimar.yml`), todos los días a las 08:17 y 22:53 (hora de Buenos Aires), después
de las corridas del monitor. Solo guarda un commit si cambió algún insumo o la estimación.

Probar en local: `pip install -r requirements.txt` y `python -m estimador.correr`.

## Limitaciones

La evaluación usa los datos tal como están hoy (INDEC revisa el EMAE y algunos indicadores) y supone que todos los
indicadores estaban disponibles en cada momento; el error real puede ser algo mayor. Es una estimación propia, no oficial.
