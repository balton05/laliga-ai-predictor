# Fase 9 — Actualización dinámica por jornada

## Objetivo

La Fase 9 convierte el proyecto de pretemporada en un sistema operativo. Cada
ejecución incorpora los resultados confirmados de LaLiga 2026/27, recalcula el
estado previo de los equipos, actualiza las probabilidades de los partidos
pendientes y vuelve a simular la temporada completa.

## Entradas

### Resultados

El archivo `data/incoming/results_2026_27.csv` usa `fixture_id` como clave. Los
goles y la fecha son obligatorios por partido; tiros, tiros a puerta, córners y
tarjetas pueden dejarse vacíos. El pipeline deriva el 1X2 y valida que:

- el partido exista en el calendario oficial;
- no haya identificadores duplicados;
- los goles sean enteros no negativos;
- una actualización normal contenga los diez partidos de cada jornada incluida.

La opción `--allow-partial` existe para seguimiento en vivo, pero el flujo
recomendado es actualizar después de cerrar la jornada.

### Cuotas

`data/incoming/odds_2026_27.csv` admite varios snapshots por partido. Se utiliza
el registro más reciente según `captured_at`. Las cuotas se convierten en
probabilidades implícitas y se normalizan para retirar el margen.

## Flujo reproducible

```text
Resultados confirmados
        ↓
Validación y conciliación con fixture_id
        ↓
Historial dinámico + tabla + Elo + forma 5/10
        ↓
Features de los partidos pendientes
        ↓
Random Forest + Logística + Poisson
        ↓
Ensemble deportivo o ensemble con mercado por partido
        ↓
50,000 simulaciones con resultados ya jugados fijados
        ↓
Dashboard, controles y snapshot inmutable
```

## Política de modelos

- Random Forest y regresión logística permanecen congelados con entrenamiento
  hasta 2025/26. Esto evita cambiar el modelo sin una validación formal.
- Sus entradas sí se actualizan: forma, rendimiento de temporada, local/visita,
  clasificación, descanso y Elo.
- Poisson se reentrena cuando existen resultados de 2026/27. Para Racing,
  Deportivo y Málaga, el prior de Segunda se reduce gradualmente durante sus
  primeros diez partidos.
- El ensemble con mercado se usa solamente en partidos con las tres cuotas
  actuales. Los demás mantienen el ensemble deportivo.

## Simulación

Los partidos completados se incorporan como hechos fijos. Solo los encuentros
pendientes se sortean con las probabilidades actualizadas. El marcador se
genera con Poisson condicionado al 1X2 y la tabla conserva el criterio de
mini-liga entre equipos empatados.

## Auditoría y recuperación

Cada ejecución crea un `update_id` determinista a partir de los resultados y
cuotas normalizados. Las salidas se guardan en `snapshots/<update_id>/` con un
manifiesto que contiene hashes SHA-256. Repetir exactamente la misma entrada
produce el mismo identificador y no duplica el historial lógico.

## Ejecución en Windows

```powershell
.venv\Scripts\python.exe scripts\update_season.py
```

Para una actualización parcial:

```powershell
.venv\Scripts\python.exe scripts\update_season.py --allow-partial
```

## Salidas principales

| Archivo | Contenido |
|---|---|
| `current_results_2026_27.csv` | Resultados confirmados normalizados |
| `current_team_state_2026_27.csv` | Forma, Elo y estado por equipo |
| `current_fixture_features_2026_27.csv` | Variables de partidos pendientes |
| `current_predictions_2026_27.csv` | Probabilidades dinámicas 1X2 |
| `current_table_2026_27.csv` | Clasificación con resultados reales |
| `dynamic_season_simulation_summary.csv` | Probabilidades y puntos finales |
| `dynamic_preseason_comparison.csv` | Cambios frente a la Fase 8 |
| `phase9_update_log.csv` | Historial de ejecuciones |
| `phase9_quality_checks.csv` | Controles automáticos |
| `laliga_phase9_dashboard.xlsx` | Panel operativo de actualización |
