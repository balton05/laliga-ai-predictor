# Fase 8 — Simulación Monte Carlo de LaLiga 2026/27

## Objetivo

La Fase 8 transforma las probabilidades prepartido de los 380 encuentros en
una distribución de posibles clasificaciones finales. Se ejecutan **50,000
temporadas** con semilla fija para estimar campeón, Top 4, plazas europeas,
descenso, puntos y posición probable.

## Entradas

- Probabilidades 1X2 del ensemble deportivo de la Fase 7.
- Goles esperados local y visitante del modelo Poisson de la Fase 5.
- Calendario completo de 38 jornadas y 20 equipos.
- Ajuste conservador de Racing, Deportivo y Málaga ya incorporado en las
  predicciones de origen.

No se utilizan cuotas porque aún no están disponibles para la temporada
2026/27.

## Método de simulación

Para cada partido:

1. Se sortea local, empate o visitante con las probabilidades del ensemble.
2. Se genera un marcador desde la distribución Poisson, condicionado al
   resultado 1X2 sorteado.
3. Se asignan puntos, goles a favor, goles en contra y estadísticas del
   enfrentamiento directo.

Este diseño conserva las mejores probabilidades 1X2 disponibles y utiliza
Poisson para dar coherencia a los marcadores y desempates.

## Clasificación y desempates

La tabla se ordena por:

1. Puntos.
2. Puntos en la mini-liga de equipos empatados.
3. Diferencia de goles en esa mini-liga.
4. Diferencia de goles general.
5. Goles anotados.

El procedimiento aproxima el reglamento de LaLiga. No reproduce todas las
reaplicaciones excepcionales que podrían producirse en empates múltiples muy
específicos.

## Definición de zonas

- Campeón: posición 1.
- Top 4: posiciones 1–4.
- Top 6: posiciones 1–6.
- Europa: Top 7 como proxy de posición liguera.
- Descenso: posiciones 18–20.

La asignación europea final puede cambiar por campeones de Copa del Rey y por
plazas adicionales de rendimiento UEFA. Por ello, `europe_top7_probability`
debe interpretarse como probabilidad de terminar en una posición europea
probable, no como clasificación garantizada a un torneo específico.

## Incertidumbre y convergencia

Se comparan 1,000, 5,000, 10,000 y 25,000 simulaciones contra el resultado
final de 50,000. La entrega incluye el máximo cambio absoluto de las
probabilidades de campeón, Top 4, Top 7 y descenso, además del cambio en puntos
esperados.

## Limitación principal

Las 380 probabilidades usan una fotografía estática de pretemporada. No
incorporan fichajes posteriores, lesiones, sanciones, forma real ni cambios de
entrenador. El simulador debe actualizarse después de cada jornada con nuevos
resultados y probabilidades.

