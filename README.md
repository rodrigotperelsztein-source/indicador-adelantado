# Indicador adelantado del EMAE

Estimación de la variación interanual del **EMAE** (Estimador Mensual de Actividad Económica, INDEC)
antes de que se publique, con indicadores que salen antes: importaciones, cemento, Construya, ventas
de combustibles, recaudación, producción automotriz y metalúrgica, ventas minoristas pyme (CAME),
patentamientos, crédito y otros.

**Página:** https://rodrigotperelsztein-source.github.io/indicador-adelantado/

**Origen de los datos.** Buena parte de los indicadores (y los préstamos diarios y el IPC con que se deflactan) se
leen de la API pública de [Monitor Argy](https://monitorargy.com), un sitio que publica series oficiales argentinas
con datos abiertos; el resto sale de [monitor-series](https://github.com/rodrigotperelsztein-source/monitor-series).
`estimador/indicadores.py` dice de dónde sale cada uno (`fuente="ma"` es Monitor Argy). Gracias a Monitor Argy por
abrir sus datos.

## Cómo funciona

1. `estimador/datos.py` baja los indicadores de [monitor-series](https://github.com/rodrigotperelsztein-source/monitor-series)
   (`data/series/<id>.csv`) y de la API pública de [Monitor Argy](https://monitorargy.com), y guarda una copia en `data/insumos/`.
2. `estimador/modelo.py` estima, para cada indicador, una regresión de la variación interanual del EMAE contra la del
   indicador, la del EMAE del mes anterior y la diferencia de días hábiles contra el mismo mes del año anterior
   (`estimador/calendario.py`, con los feriados de la librería `holidays` más los traslados que le faltan), desde 2017 y
   sin la pandemia, más un "factor común" con el promedio de todos. Todos los modelos incluyen además el aporte estimado
   de la cosecha (`estimador/cosecha.py`): la producción de soja, maíz, trigo y girasol por campaña (Secretaría de
   Agricultura, vía la API de series de datos.gob.ar) repartida en los meses de cosecha con un calendario típico. La
   campaña en curso sale del informe mensual de la Secretaría (fuente `estimaciones_agricolas` de monitor-series) o de
   una estimación cargada a mano en `data/cosecha_manual.csv`, la más reciente; mientras nadie la estimó, de la
   superficie implantada por el rendimiento tendencial. Se probó repartir con el avance semanal real de la cosecha en
   lugar del calendario típico y no mejoró la estimación (INDEC parece usar un calendario fijo).
   La página compara los trimestres con la última expectativa del REM del BCRA (fuente `rem` de monitor-series). El REM
   se probó también como indicador (variación trimestral esperada y crecimiento anual esperado) y no mejoró el error.
   Cada modelo se evalúa en tiempo pseudo-real (cada mes estimado solo con datos anteriores) y la estimación final
   combina los 8 mejores de los que ya tienen dato del mes, con pesos inversos a su error de los últimos 24 meses.
   Hay dos bandas: ±1 error típico de esa combinación (68%) y ±1,645 (90%); `cobertura_bandas_36m` informa cuántas
   veces el dato cayó efectivamente adentro.
3. `estimador/correr.py` guarda los resultados:

| Archivo | Contenido |
|---|---|
| `data/estimacion.json` | Estimación actual (cada mes sin EMAE publicado con al menos 3 indicadores), aporte y peso de cada modelo, evaluación, estado de cada indicador |
| `data/historial.csv` | Cada versión de la estimación (cambia cuando entra un dato), para compararla con el EMAE publicado |
| `data/evaluacion.csv` | Error de cada modelo, mes a mes, en la evaluación en tiempo pseudo-real |
| `data/insumos/` | Copia de las series usadas |

Para sumar un indicador alcanza con agregarlo en `estimador/indicadores.py`: el modelo mide solo cuánto acierta y le
da peso según eso. Las series nuevas conviene sumarlas primero a monitor-series.

## Mes en curso y acumulado

- **Mes en curso** (`estimador/en_curso.py`): mientras el mes transcurre solo hay datos diarios. Se usa la variación
  interanual de lo que va del mes (contra los mismos días del año anterior) de los préstamos comerciales reales (BCRA,
  vía Monitor Argy) y de la demanda eléctrica de grandes usuarios industriales (CAMMESA), más la estimación del mes
  anterior. Es preliminar y su banda incluye el error de la estimación del mes previo.
- **Acumulado del año**: variación de enero hasta el último mes con dato contra el mismo período del año anterior,
  oficial y sumando cada mes estimado (con su banda).

## Cuándo corre

GitHub Actions (`.github/workflows/estimar.yml`), todos los días a las 08:17 y 22:53 (hora de Buenos Aires), después
de las corridas del monitor. Solo guarda un commit si cambió algún insumo o la estimación.

Probar en local: `pip install -r requirements.txt` y `python -m estimador.correr`.

## Limitaciones

La evaluación usa los datos tal como están hoy (INDEC revisa el EMAE y algunos indicadores) y supone que todos los
indicadores estaban disponibles en cada momento; el error real puede ser algo mayor. Es una estimación propia, no oficial.
