# Fase 14 — Historial inmutable y evaluación real

## Objetivo

Conservar la predicción disponible antes de cada partido y medirla contra el
resultado real sin sobrescribir versiones ni utilizar información posterior.

## Persistencia

### `prediction_snapshots`

Registro append-only de cada versión:

- partido, jornada y fecha;
- probabilidades 1X2 y pronóstico;
- marcador y goles esperados;
- versión del modelo y `update_id`;
- probabilidades/cuotas de mercado disponibles;
- fecha UTC de captura;
- indicador `is_pre_match`.

La combinación partido + actualización + versión del modelo es única. Una
ejecución repetida no duplica capturas.

### `prediction_evaluations`

Un único registro por partido finalizado, asociado a la última captura válida
anterior al encuentro:

- resultado y marcador real;
- acierto 1X2;
- Log Loss multiclase;
- Brier Score multiclase;
- métricas equivalentes del mercado cuando existen cuotas;
- fecha y versión exacta del pronóstico evaluado.

Si un resultado no tiene una captura prepartido válida, permanece pendiente.
El sistema no genera métricas retrospectivas con probabilidades posteriores.

## Automatización

En cada sincronización:

1. Se conserva el estado de predicciones anterior.
2. Se actualizan resultados, cuotas, variables y probabilidades.
3. Se guardan nuevas versiones solo para partidos aún no jugados.
4. Se evalúan los resultados nuevos con la última captura prepartido.

## API

- `GET /performance/summary`
- `GET /performance/history`
- `GET /performance/by-matchday`
- `GET /performance/confusion`
- `GET /performance/calibration`

`/performance/history` permite filtrar por `matchday`, `team`, `limit` y
`offset`.

## Frontend

La ruta `/rendimiento` muestra:

- partidos evaluados;
- Accuracy, Log Loss y Brier Score;
- comparación con cuotas;
- rendimiento por jornada;
- matriz de confusión;
- calibración;
- historial por partido.

Antes del comienzo de LaLiga, la vista comunica que el sistema está preparado
y no presenta métricas simuladas como si fueran resultados reales.

## Validación

- Capturas idempotentes.
- Versiones anteriores preservadas.
- Selección de la última captura prepartido.
- Evaluación única por encuentro.
- Endpoints listos con base vacía.
- 79 pruebas de regresión aprobadas.
- Compilación Angular de producción aprobada.
