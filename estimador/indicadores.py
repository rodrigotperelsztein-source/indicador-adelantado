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


OBJETIVO = Indicador("emae", "EMAE, serie original (INDEC)", "monitor", "emae.original", "nivel", "Objetivo")

INDICADORES = [
    # Industria
    Indicador("ipi", "IPI manufacturero (INDEC)", "monitor", "ipi.original", "nivel", "Industria"),
    Indicador("metalurgia", "Producción metalúrgica (ADIMRA)", "ma", "metalurgia_adimra", "nivel", "Industria"),
    Indicador("autos", "Producción automotriz (ADEFA)", "ma", "produccion_automotriz", "nivel", "Industria"),
    Indicador("acero", "Producción de acero crudo", "ma", "acero_crudo", "nivel", "Industria"),
    Indicador("capacidad", "Uso de la capacidad instalada (INDEC)", "ma", "capacidad_instalada", "dif12", "Industria"),
    Indicador("ipip", "Producción industrial pyme (CAME)", "monitor", "came.ipip_var_ia", "var_ia", "Industria"),
    Indicador("electricidad_industria", "Demanda eléctrica de grandes usuarios industriales (CAMMESA)", "monitor",
              "cammesa_gu_actividad_mensual.industrias", "nivel", "Industria"),
    # Construcción
    Indicador("isac", "ISAC (INDEC)", "monitor", "isac.original", "nivel", "Construcción"),
    Indicador("cemento", "Despacho de cemento (AFCP)", "ma", "despacho_cemento", "nivel", "Construcción"),
    Indicador("construya", "Índice Construya", "ma", "construya_desest", "nivel", "Construcción"),
    # Comercio y consumo
    Indicador("came", "Ventas minoristas pyme (CAME)", "monitor", "came.minoristas_var_ia", "var_ia", "Comercio y consumo"),
    Indicador("patentamientos", "Patentamientos de autos", "ma", "patentamientos_autos", "nivel", "Comercio y consumo"),
    Indicador("iva", "Recaudación de IVA DGI real", "ma", "recaudacion_iva_dgi_real", "nivel", "Comercio y consumo"),
    Indicador("naftas", "Ventas de naftas (Secretaría de Energía)", "monitor", "ventas_combustibles.naftas_total", "nivel",
              "Comercio y consumo"),
    # Transporte y combustibles
    Indicador("gasoil", "Ventas de gasoil sin usinas ni bunker (Secretaría de Energía)", "monitor",
              "ventas_combustibles.gasoil_total_sin_usinas_bunker", "nivel", "Transporte y combustibles"),
    Indicador("gasoil_g3", "Ventas de gasoil grado 3", "monitor", "ventas_combustibles.gasoil_g3_total", "nivel",
              "Transporte y combustibles"),
    Indicador("gasoil_carga", "Gasoil para transporte de carga", "monitor", "ventas_combustibles.gasoil_canal_carga", "nivel",
              "Transporte y combustibles"),
    # Comercio exterior
    Indicador("importaciones", "Importaciones (INDEC)", "ma", "importaciones", "nivel", "Comercio exterior"),
    Indicador("impo_capital", "Importaciones de bienes de capital", "ma", "impo_capital", "nivel", "Comercio exterior"),
    Indicador("impo_intermedios", "Importaciones de bienes intermedios", "ma", "impo_intermedios", "nivel", "Comercio exterior"),
    # Empleo, crédito y expectativas
    Indicador("seguridad_social", "Recaudación de seguridad social real", "ma", "recaudacion_ss_real", "nivel",
              "Empleo, crédito y expectativas"),
    Indicador("prestamos", "Préstamos comerciales reales", "ma", "prestamos_comerciales_real", "nivel",
              "Empleo, crédito y expectativas"),
    Indicador("indice_lider", "Índice Líder (UTDT)", "ma", "indice_lider", "nivel", "Empleo, crédito y expectativas"),
    # Agro
    Indicador("leche", "Producción de leche", "ma", "produccion_leche", "nivel", "Agro"),
    Indicador("faena", "Faena vacuna", "ma", "faena_vacuna", "nivel", "Agro"),
]
