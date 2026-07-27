# Política de seguridad

## Versiones compatibles

La rama principal y la versión más reciente del proyecto reciben correcciones
de seguridad. Las fotografías de fases anteriores se conservan como evidencia
del proceso, pero no deben desplegarse públicamente.

## Reportar una vulnerabilidad

No publiques credenciales, tokens, datos privados ni detalles explotables en
un issue público. Contacta al responsable del repositorio por un canal privado
e incluye:

- Componente y versión afectados.
- Pasos mínimos para reproducir el problema.
- Impacto observado o posible.
- Propuesta de mitigación, si existe.

## Controles operativos

- Los endpoints de escritura admiten `X-API-Key` o `Authorization: Bearer`.
- Producción exige una clave administrativa de 32 caracteres como mínimo.
- Swagger y OpenAPI se desactivan por defecto en producción.
- Hosts y orígenes CORS deben declararse explícitamente.
- Las respuestas incluyen encabezados defensivos y un identificador de
  solicitud.
- Las imágenes de Docker ejecutan la API sin privilegios de root.
- PostgreSQL no publica su puerto en la composición de producción.

Las claves y contraseñas deben almacenarse en variables de entorno o en el
gestor de secretos de la plataforma. Nunca deben confirmarse en Git.
