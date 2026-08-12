# Historial de cambios

## 1.7.0 — Fase 17

- Publicación preparada para un repositorio público sin secretos.
- Imagen única de Render para Angular y FastAPI bajo el mismo origen.
- PostgreSQL persistente en Neon mediante una cadena de conexión secreta.
- Inicialización de datos únicamente cuando la base está vacía.
- Restauración del modelo champion desde PostgreSQL en cada arranque.
- Automatización de temporada con GitHub Actions en zona America/Lima.
- Verificador offline y comprobación del despliegue público.

## 1.6.0 — Fase 16

- Suite final de seguridad y preparación para publicación.
- Protección opcional de endpoints administrativos mediante API key.
- Validación estricta de configuración de producción.
- Encabezados HTTP defensivos, hosts permitidos y límite de solicitudes.
- API ejecutada como usuario sin privilegios dentro de Docker.
- Proxy `/api` de mismo origen y endurecimiento de Nginx.
- Composición Docker separada para producción.
- Flujo de integración continua para backend y frontend.
- Verificador reproducible de preparación para lanzamiento.
- Documentación de arquitectura, seguridad, pruebas y operación.

## 1.5.0 — Fase 15

- Registro de modelos, reentrenamiento controlado y comparación
  champion–challenger.

## 1.4.0 — Fase 14

- Historial inmutable y evaluación real de predicciones.

## 1.3.0 — Fase 13

- Actualización programada desde Football-Data.
