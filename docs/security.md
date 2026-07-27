# Seguridad y configuración

## Modos

`LALIGA_ENVIRONMENT` admite:

- `development`: facilita el trabajo local y permite Swagger.
- `test`: aislado para pruebas automatizadas.
- `production`: exige clave administrativa y configuración explícita.

## Endpoints administrativos

Estas operaciones se protegen cuando `LALIGA_ADMIN_API_KEY` está definida:

- `POST /automation/run`
- `POST /update-matchday`
- `POST /models/retrain`
- `POST /models/{version}/promote`

La clave puede enviarse con uno de estos encabezados:

```text
X-API-Key: <clave>
Authorization: Bearer <clave>
```

Las consultas públicas de calendario, predicciones, rendimiento y modelos no
requieren clave.

## Crear secretos en PowerShell

```powershell
$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToBase64String($bytes)
```

Usa valores distintos para `POSTGRES_PASSWORD` y
`LALIGA_ADMIN_API_KEY`. No los escribas en el código ni los confirmes en Git.

## Producción

1. Copia `.env.production.example` como `.env.production`.
2. Sustituye todos los valores de ejemplo.
3. Restringe `LALIGA_ALLOWED_HOSTS` al dominio real.
4. Restringe `LALIGA_CORS_ORIGINS` al origen HTTPS real.
5. Valida la composición:

```powershell
docker compose `
  --env-file .env.production `
  -f docker-compose.production.yml `
  config --quiet
```

6. Inicia los servicios:

```powershell
docker compose `
  --env-file .env.production `
  -f docker-compose.production.yml `
  up -d --build
```

La composición de producción:

- No publica PostgreSQL.
- Exige secretos antes de iniciar.
- Desactiva Swagger y OpenAPI.
- Ejecuta la API como usuario sin privilegios.
- Elimina capacidades Linux innecesarias.
- Mantiene la base de datos en una red interna.

## Encabezados defensivos

FastAPI y Nginx añaden controles contra interpretación MIME, incrustación en
marcos, filtración de referencia y acceso a cámara, micrófono o ubicación.
Producción también habilita HSTS en la API.

## Alcance

La API key protege la administración de este proyecto personal. Para una
plataforma con múltiples usuarios se necesitarían cuentas, roles, rotación de
sesiones, revocación y auditoría por identidad.
