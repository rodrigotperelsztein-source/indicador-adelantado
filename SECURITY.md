# Seguridad

Mismo criterio que [monitor-series](https://github.com/rodrigotperelsztein-source/monitor-series/blob/main/SECURITY.md):
el repositorio solo usa y publica **datos públicos**, no guarda credenciales ni recibe datos de quienes lo usan.

- Acciones de GitHub fijadas por commit; Dependabot revisa acciones y dependencias.
- Dependencias de Python con huella SHA-256 (`--require-hashes --only-binary=:all:`); `pip-audit` sin vulnerabilidades conocidas.
- Permisos mínimos: el workflow arranca sin permisos y el paso que baja datos de afuera corre sin token; solo el último
  paso, que guarda `data/`, tiene permiso de escritura, y frena si hay cambios fuera de `data/`.
- Solo lee por HTTPS `raw.githubusercontent.com` (monitor-series) y `monitorargy.com`.
- Página sin terceros: ECharts 5.5.1 alojado en `docs/vendor/` (con su huella en `SHA256SUMS`); la política de seguridad
  de contenido solo permite leer `raw.githubusercontent.com`. Sin cookies ni analítica.

Configuración recomendada en GitHub: verificación en dos pasos, regla que proteja `main` (sin force push ni borrado),
acciones solo de GitHub, token por defecto de solo lectura, Dependabot y escaneo de secretos activados, Pages con HTTPS.

Reportar un problema: *Security > Report a vulnerability* (reporte privado).
