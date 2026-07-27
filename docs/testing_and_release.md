# Pruebas y preparación para lanzamiento

## Validación local

Desde la raíz del proyecto:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\verify_release.py --offline

cd frontend
npm ci
npm run build
```

## Validación con Docker iniciado

```powershell
cd "D:\Josue\DATASETS\laliga-ai-predictor"

.venv\Scripts\python.exe scripts\verify_release.py `
  --api-url "http://localhost:8000"

docker compose config --quiet
docker compose ps
```

El reporte se guarda en:

```text
reports/phase16_release_check.json
```

## Contratos comprobados

- 380 partidos únicos y jornadas entre 1 y 38.
- Partidos terminados más predicciones pendientes igual a 380, con
  probabilidades válidas que suman uno.
- Documentación y archivos de publicación presentes.
- Secretos obligatorios en la composición de producción.
- Usuario no root y healthcheck en la imagen de API.
- Proxy web del mismo origen y encabezados defensivos.
- API conectada, registro de modelos activo y cabeceras HTTP en vivo.

## Integración continua

`.github/workflows/ci.yml` ejecuta dos trabajos:

| Trabajo | Comprobaciones |
|---|---|
| Backend | Instalación Python, `pytest` y verificador offline |
| Frontend | Instalación reproducible con `npm ci` y compilación Angular |

El flujo usa permisos de solo lectura sobre el repositorio y tiempos máximos
por trabajo.

## Criterio de aprobación

Una versión está lista para la Fase 17 cuando:

- Todas las pruebas Python pasan.
- Angular compila en modo producción.
- El verificador de lanzamiento termina con `status: passed`.
- Docker Compose valida sin errores.
- No existen secretos ni archivos `.env` dentro del commit.
- El README, seguridad, arquitectura y operación coinciden con el código.
