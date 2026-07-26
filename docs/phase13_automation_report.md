# Fase 13 — Automatización y observabilidad

## Objetivo

Automatizar la actualización operativa de LaLiga 2026/27 sin duplicar la
lógica ya validada en las fases 9 y 10. El nuevo servicio consulta una fuente
externa, detecta cambios, ejecuta el pipeline dinámico, sincroniza PostgreSQL y
registra cada ejecución con sus pasos, duración y errores.

## Fuente inicial

- Fuente: Football-Data, Primera División de España (`SP1`).
- URL configurable:
  `https://www.football-data.co.uk/mmz4281/2627/SP1.csv`.
- Frecuencia predeterminada: cada 360 minutos (6 horas).
- Estado seguro antes de que se publique el archivo 2026/27:
  `source_unavailable`. Esta situación no modifica datos ni predicciones.

La fuente puede cambiarse mediante `LALIGA_FOOTBALL_DATA_URL` sin modificar
código.

## Flujo operativo

1. Cargar el calendario canónico de 380 partidos.
2. Descargar y validar el CSV de Football-Data.
3. Normalizar nombres y relacionar cada fila con su `fixture_id`.
4. Detectar únicamente resultados o cuotas nuevas.
5. Ejecutar variables prepartido, probabilidades 1X2 y 50,000 simulaciones.
6. Sincronizar PostgreSQL de forma transaccional.
7. Registrar la ejecución y todos sus pasos.

El pipeline es idempotente: un archivo con el mismo checksum o los mismos
valores no vuelve a procesarse.

## Protección de integridad

- Bloqueo local y `pg_advisory_lock` para impedir dos actualizaciones
  simultáneas entre la API y el scheduler.
- Un resultado confirmado no puede sobrescribirse con otro marcador.
- Los encuentros ajenos al calendario 2026/27 detienen la ejecución.
- Las cuotas deben contener el bloque completo `B365H`, `B365D`, `B365A`.
- Se conserva `allow_partial=True` para actualizaciones durante una jornada.
- Los clasificadores siguen congelados hasta 2025/26; solo se actualizan Elo,
  variables temporales y el modelo Poisson con resultados nuevos.
- Todas las características siguen siendo conocidas antes del encuentro.

## Estados del pipeline

| Estado | Significado |
|---|---|
| `running` | La ejecución está en curso. |
| `success` | Hubo cambios y se actualizaron predicciones y base de datos. |
| `no_changes` | La fuente fue válida, pero no contenía novedades. |
| `source_unavailable` | La fuente aún no existe o no se pudo consultar. |
| `failed` | Hubo un error de validación, modelado o persistencia. |

## Tablas nuevas

### `pipeline_runs`

Una fila por ejecución. Incluye disparador, fuente, checksum, cantidad de
filas, resultados/cuotas detectados y añadidos, versión del modelo, duración y
error.

### `pipeline_steps`

Detalle ordenado de cada paso:

- `load_calendar`
- `download_source`
- `detect_changes`
- `update_predictions_and_database`

## API de observabilidad

| Método | Endpoint | Uso |
|---|---|---|
| `GET` | `/automation/status` | Configuración y última ejecución. |
| `GET` | `/automation/runs?limit=20` | Historial de ejecuciones. |
| `GET` | `/automation/runs/{run_id}/steps` | Pasos de una ejecución. |
| `POST` | `/automation/run` | Ejecutar una revisión manual. |

## Configuración

| Variable | Predeterminado |
|---|---|
| `LALIGA_AUTOMATION_ENABLED` | `true` |
| `LALIGA_AUTOMATION_INTERVAL_MINUTES` | `360` |
| `LALIGA_FOOTBALL_DATA_URL` | URL `2627/SP1.csv` |
| `LALIGA_AUTOMATION_TIMEOUT_SECONDS` | `30` |
| `LALIGA_AUTOMATION_SIMULATIONS` | `50000` |
| `LALIGA_AUTOMATION_SEED` | `42` |

## Operación

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f automation
```

Consultar el estado:

```powershell
Invoke-RestMethod "http://localhost:8000/automation/status" |
  ConvertTo-Json -Depth 5
```

Forzar una revisión:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/automation/run" |
  ConvertTo-Json -Depth 5
```

## Validación

- 77 pruebas Python aprobadas.
- 5 pruebas específicas de la Fase 13.
- Compilación Angular de producción aprobada.
- El frontend conserva calendario, equipos, escudos y estadios de la Fase 12.
- El archivo de composición adicional no modifica el puerto público de
  PostgreSQL configurado por el usuario.
