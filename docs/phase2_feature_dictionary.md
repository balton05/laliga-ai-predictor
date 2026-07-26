# Diccionario y metodología · Fase 2

## Objetivo

La Fase 2 convierte las estadísticas posteriores a cada partido en variables
históricas disponibles antes del siguiente encuentro. La unidad principal es
una fila por partido.

## Datasets

### `laliga_model_dataset.csv`

Dataset recomendado para la primera ronda de modelado:

- 3,800 partidos de Primera División.
- 10 temporadas entre 2016/17 y 2025/26.
- 76 variables predictoras.
- 10 columnas de identificación, objetivo y partición temporal.

La tabla completa `laliga_match_features.csv` conserva 206 candidatos para
experimentos posteriores. No se recomienda introducirlos todos de inmediato:
la selección inicial más pequeña reduce redundancia y riesgo de sobreajuste.

### `team_pre_match_features.csv`

Contiene dos filas por partido, una desde la perspectiva del local y otra desde
la perspectiva del visitante. Es la tabla auditable de la cual se construyen
las columnas `home_*` y `away_*`.

### `team_preseason_state_2026_27.csv`

Fotografía de los 20 participantes antes de iniciar LaLiga 2026/27. Racing,
Deportivo y Málaga conservan su forma reciente de Segunda, pero también llevan:

- `promoted = 1`;
- `previous_division = SP2`;
- posición y estadísticas de Segunda;
- Elo regularizado hacia el nivel de Primera;
- tipo de ascenso directo o playoff.

### `fixtures_2026_27_preseason_features.csv`

Une el calendario oficial con el estado inicial de los equipos. Es una
fotografía estática apta para una simulación de pretemporada. No representa el
estado que tendrán los clubes en jornadas posteriores.

## Grupos de variables

| Grupo | Ejemplos | Regla temporal |
|---|---|---|
| Forma reciente | `form_ppg_5`, `form_goals_for_avg_10` | Últimos 5 o 10 partidos anteriores |
| Local/visitante | `venue_ppg_5`, `venue_win_rate_5` | Últimos 5 en la localía correspondiente |
| Temporada | `season_ppg_pre`, `season_goals_for_avg_pre` | Acumulado antes del partido |
| Clasificación | `league_position_pre` | Tabla al comenzar el día |
| Descanso | `days_rest` | Diferencia con la fecha del partido anterior |
| Elo | `home_elo_pre`, `elo_difference_pre` | Rating antes de actualizar con el resultado |
| Mercado | `market_probability_*` | Cuotas prepartido sin margen |
| Ascenso | `promoted`, `segunda_position` | Contexto conocido antes de la temporada |
| Diferencias | `form_ppg_5_difference` | Valor local menos valor visitante |

## Objetivo

| Campo | Significado |
|---|---|
| `target_ftr` | `H`: local, `D`: empate, `A`: visitante |
| `target_class` | `H = 0`, `D = 1`, `A = 2` |

Estas columnas no son predictoras.

## Prevención de fuga de información

1. Cada promedio móvil desplaza una observación antes de calcularse.
2. Goles, tiros, córners y tarjetas del partido actual no aparecen como
   predictores directos.
3. Los acumulados se calculan antes de sumar el encuentro actual.
4. El Elo se registra antes de aplicar la actualización del resultado.
5. Los partidos de una misma fecha actualizan la tabla juntos, evitando que el
   orden arbitrario del CSV altere la posición previa.
6. La temporada 2025/26 permanece bloqueada como prueba final.
7. Las imputaciones y el escalado deberán ajustarse solo con entrenamiento.

La prueba `test_current_match_statistics_do_not_change_its_features` modifica
el resultado y las estadísticas de un partido y comprueba que sus propias
variables prepartido permanezcan idénticas.

## Elo inicial

Parámetros de la primera versión:

| Parámetro | Valor |
|---|---:|
| Base Primera | 1500 |
| Base Segunda | 1350 |
| Factor K | 20 |
| Ventaja local | 60 puntos |
| Regresión entre temporadas | 25 % |

Estos valores son supuestos iniciales. En el modelado se comparará su desempeño
fuera de muestra y podrán ajustarse usando únicamente entrenamiento y
validación.

## Cuotas y margen

Primero se utilizan cuotas promedio cuando las tres están disponibles; en caso
contrario, se usan las tres cuotas Bet365. Para cada resultado:

\[
p_i^{raw}=\frac{1}{cuota_i}
\]

\[
overround=\sum_i p_i^{raw}
\]

\[
p_i=\frac{p_i^{raw}}{overround}
\]

Las tres probabilidades finales suman 1.

## Valores faltantes esperados

- Las primeras observaciones de cada equipo no tienen cinco o diez antecedentes.
- Los acumulados de temporada están vacíos antes del primer partido.
- `segunda_position` solo tiene sentido para ascendidos.
- Los días de descanso pueden faltar cuando no existe un partido anterior.

No deben rellenarse directamente en el CSV. La imputación formará parte del
pipeline del modelo para evitar contaminación entre periodos.
