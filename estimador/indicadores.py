"""Indicadores que entran en la estimación del EMAE y de dónde salen.

Cada indicador se pasa a variación interanual (en logaritmos, ×100) para compararlo con la
variación interanual del EMAE original:
  - "nivel": serie en niveles -> 100 · ln(x_t / x_{t-12});
  - "var_ia": la fuente ya publica la variación % interanual -> 100 · ln(1 + v/100);
  - "dif12": tasa o porcentaje (p. ej. uso de la capacidad) -> x_t - x_{t-12}, en puntos.

Fuentes:
  - "monitor": repositorio monitor-series (data/series/<id>.csv);
  - "ma": API pública de Monitor Argy (monitorargy.com/api/v1/series/<id>).

Para sumar un indicador alcanza con agregarlo acá: el modelo lo evalúa solo (cuánto acertó en
los últimos años) y le da peso según eso.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Indicador:
    id: str
    nombre: str
    fuente: str          # "monitor" o "ma"
    serie: str           # id en la fuente
    transformacion: str  # "nivel", "var_ia" o "dif12"
    grupo: str           # para mostrar
    publica: str = ""    # cuándo sale, si no está en ningún calendario ({mes}: el mes siguiente al del dato pendiente);
                         # las de INDEC y Monitor Argy se toman de sus calendarios


OBJETIVO = Indicador("emae", "EMAE, serie original (INDEC)", "monitor", "emae.original", "nivel", "Objetivo")

INDICADORES = [
    # Industria
    Indicador("ipi", "IPI manufacturero (INDEC)", "monitor", "ipi.original", "nivel", "Industria"),
    Indicador("metalurgia", "Producción metalúrgica (ADIMRA)", "monitor", "adimra.indice", "nivel", "Industria",
              "≈ del 15 al 25 de {mes}"),
    Indicador("autos", "Producción automotriz (ADEFA)", "monitor", "adefa.produccion", "nivel", "Industria",
              "≈ principios de {mes}"),
    Indicador("acero", "Producción de acero crudo", "monitor", "acero.acero_crudo", "nivel", "Industria",
              "≈ mediados de {mes}"),
    Indicador("capacidad", "Uso de la capacidad instalada (INDEC)", "monitor", "capacidad_instalada.nivel_general", "dif12",
              "Industria"),
    Indicador("ipip", "Producción industrial pyme (CAME)", "monitor", "came.ipip_var_ia", "var_ia", "Industria",
              "≈ primera quincena de {mes}"),
    Indicador("electricidad_industria", "Demanda eléctrica de grandes usuarios industriales (CAMMESA)", "monitor",
              "cammesa_gu_actividad_mensual.industrias", "nivel", "Industria",
              "a principios de {mes} (dato diario de CAMMESA)"),
    # Construcción
    Indicador("isac", "ISAC (INDEC)", "monitor", "isac.original", "nivel", "Construcción"),
    Indicador("cemento", "Despacho de cemento (AFCP)", "monitor", "cemento.despacho", "nivel", "Construcción",
              "≈ principios de {mes}"),
    Indicador("construya", "Índice Construya", "monitor", "construya.indice_desest", "nivel", "Construcción",
              "≈ principios de {mes}"),
    # Comercio y consumo
    Indicador("came", "Ventas minoristas pyme (CAME)", "monitor", "came.minoristas_var_ia", "var_ia", "Comercio y consumo",
              "≈ primer fin de semana de {mes}"),
    Indicador("patentamientos", "Patentamientos de autos", "monitor", "patentamientos.autos", "nivel", "Comercio y consumo",
              "≈ principios de {mes}"),
    Indicador("iva", "Recaudación de IVA DGI real (ARCA)", "monitor", "recaudacion_real.iva_dgi_real", "nivel", "Comercio y consumo",
              "a mediados de {mes}, con el IPC del INDEC"),
    Indicador("naftas", "Ventas de naftas (Secretaría de Energía)", "monitor", "ventas_combustibles.naftas_total", "nivel",
              "Comercio y consumo", "≈ del 20 a fin de {mes}"),
    # Transporte y combustibles
    Indicador("gasoil", "Ventas de gasoil sin usinas ni bunker (Secretaría de Energía)", "monitor",
              "ventas_combustibles.gasoil_total_sin_usinas_bunker", "nivel", "Transporte y combustibles",
              "≈ del 20 a fin de {mes}"),
    Indicador("gasoil_g3", "Ventas de gasoil grado 3", "monitor", "ventas_combustibles.gasoil_g3_total", "nivel",
              "Transporte y combustibles", "≈ del 20 a fin de {mes}"),
    Indicador("gasoil_carga", "Gasoil para transporte de carga", "monitor", "ventas_combustibles.gasoil_canal_carga", "nivel",
              "Transporte y combustibles", "≈ del 20 a fin de {mes}"),
    # Comercio exterior
    Indicador("importaciones", "Importaciones (INDEC)", "monitor", "comercio_exterior.importaciones", "nivel", "Comercio exterior"),
    Indicador("impo_capital", "Importaciones de bienes de capital", "monitor", "comercio_exterior.impo_capital", "nivel",
              "Comercio exterior"),
    Indicador("impo_intermedios", "Importaciones de bienes intermedios", "monitor", "comercio_exterior.impo_intermedios", "nivel",
              "Comercio exterior"),
    # Empleo, crédito y expectativas
    Indicador("seguridad_social", "Recaudación de seguridad social real (ARCA)", "monitor",
              "recaudacion_real.seguridad_social_real", "nivel", "Empleo, crédito y expectativas",
              "a mediados de {mes}, con el IPC del INDEC"),
    Indicador("prestamos", "Préstamos comerciales reales (BCRA)", "monitor", "bcra_real.prestamos_comerciales_real", "nivel",
              "Empleo, crédito y expectativas", "a mediados de {mes}, con el IPC del INDEC"),
    Indicador("indice_lider", "Índice Líder (UTDT)", "monitor", "utdt.indice_lider", "nivel", "Empleo, crédito y expectativas",
              "≈ del 15 al 25 de {mes}"),
    # Agro
    Indicador("leche", "Producción de leche", "monitor", "leche.produccion", "nivel", "Agro",
              "≈ mediados de {mes}"),
    Indicador("faena", "Faena vacuna", "monitor", "faena.vacunos", "nivel", "Agro",
              "≈ mediados de {mes}"),
]
