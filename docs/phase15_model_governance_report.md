# Fase 15 — Versionado y reentrenamiento controlado

## Objetivo

Convertir el modelo de producción en un activo gobernado: cada versión queda
identificada, sus métricas son auditables y ningún challenger sustituye al
campeón sin superar puertas estadísticas y recibir una confirmación explícita.

## Campeón inicial

- Versión: `ensemble-v1-trained-through-2025-26`.
- Entrenamiento histórico: 2016/17–2025/26.
- Selección de parámetros: validación walk-forward.
- Prueba final bloqueada: 2025/26.
- Componentes deportivos: Random Forest, regresión logística y Poisson.
- La huella SHA-256 del artefacto se conserva en `model_versions`.

## Reentrenamiento durante 2026/27

El núcleo clasificatorio no se modifica después de cada jornada. La primera
adaptación en vivo es una recalibración por temperatura del ensemble, porque
puede entrenarse con las probabilidades prepartido inmutables de la Fase 14 y
no requiere reconstruir variables usando información posterior al encuentro.

El proceso solo se habilita al alcanzar:

- 80 partidos evaluados.
- 8 jornadas distintas.

La muestra se ordena cronológicamente y se divide:

- 70% inicial para seleccionar la temperatura.
- 30% final para comparar champion y challenger fuera de muestra.

## Puertas de promoción

Un challenger queda elegible únicamente cuando:

1. Reduce el Log Loss del campeón al menos 0.002.
2. Su Brier Score no empeora más de 0.002.
3. Se evaluó sobre el bloque temporal posterior.
4. Conserva versión, parámetros, métricas, muestra y modelo padre.

La promoción nunca es automática. El endpoint exige `confirm: true`, archiva
la versión anterior y actualiza atómicamente `models/active_model.json`. El
nuevo calibrador se usa desde la siguiente ejecución del pipeline, antes de
las 50,000 simulaciones.

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| GET | `/models/status` | Campeón y progreso hacia el reentrenamiento |
| GET | `/models` | Registro completo de versiones |
| GET | `/models/training-runs` | Historial auditable de ejecuciones |
| POST | `/models/retrain` | Crear y evaluar un challenger |
| POST | `/models/{version}/promote` | Promoción manual confirmada |

## Estados esperados

- `not_ready`: todavía no hay evidencia suficiente.
- `candidate_ready`: el challenger superó las puertas.
- `rejected`: se entrenó, pero no mejora de forma suficiente.
- `active`: versión usada por el pipeline.
- `archived`: campeón anterior conservado para trazabilidad.

## Integridad metodológica

- Solo se usan predicciones registradas antes del partido.
- No existe partición aleatoria.
- El challenger no modifica predicciones, simulaciones ni historial mientras
  permanece en sombra.
- Las versiones anteriores no se eliminan.
- Cada snapshot futuro registra la versión activa que lo generó.
