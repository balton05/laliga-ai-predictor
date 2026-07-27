# Fase 16 — Calidad, seguridad y documentación

## Objetivo

Cerrar la preparación técnica del proyecto antes de publicarlo. Esta fase no
modifica las probabilidades ni reentrena modelos; fortalece la operación,
automatiza controles finales y documenta cómo reproducir el sistema.

## Cambios

- Configuración diferenciada para desarrollo, pruebas y producción.
- API key opcional en local y obligatoria en producción.
- Protección de todos los endpoints que modifican estado.
- Hosts, CORS, tamaño de solicitudes y documentación interactiva configurables.
- Encabezados defensivos e identificador por solicitud.
- Errores de salud sin detalles internos de base de datos.
- Contenedor de API ejecutado como usuario no root.
- Healthcheck incorporado a la imagen.
- Nginx con proxy `/api`, CSP y encabezados defensivos.
- Persistencia del modelo activo en API y automatización.
- Composición independiente de producción sin PostgreSQL público.
- Integración continua de backend y frontend.
- Verificador de contratos de datos y preparación para lanzamiento.
- README y guías de arquitectura, seguridad, pruebas y contribución.

## Compatibilidad

La configuración de desarrollo mantiene el comportamiento anterior:

- La API key es opcional.
- Swagger continúa disponible.
- Los 380 partidos, predicciones y 50,000 simulaciones no cambian.
- El puerto PostgreSQL configurado por el usuario se conserva.
- Escudos, estadios, datos, snapshots y modelo activo no se reemplazan.

## Resultado esperado

Al instalar la fase, la aplicación conserva todas las vistas existentes. El
verificador debe reportar `passed` y los endpoints de escritura siguen
funcionando en desarrollo. En producción, el arranque se detiene si faltan los
secretos requeridos.

## Validación realizada

- 87 pruebas Python aprobadas.
- Compilación Angular de producción aprobada.
- 7 controles offline de lanzamiento aprobados.
- Contratos de calendario y predicciones conciliados.
- Sintaxis YAML de las tres composiciones validada.
- Sin cambios en salidas de modelos, predicciones o simulaciones.
