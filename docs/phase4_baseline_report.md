# Fase 4 — Baselines y regresión logística multinomial

## Objetivo

Esta fase establece el punto de comparación mínimo para los modelos posteriores.
Todos los métodos generan tres probabilidades antes del partido:

\[
P(\text{local}),\quad P(\text{empate}),\quad P(\text{visitante})
\]

Se comparan cinco versiones:

1. `historical_frequency`: frecuencia de H/D/A observada en el pasado.
2. `market`: probabilidades promedio de las cuotas, normalizadas sin margen.
3. `elo_multinomial`: diferencia de Elo transformada en probabilidades 1X2.
4. `logistic_sports`: regresión logística con 72 variables deportivas.
5. `logistic_market`: regresión logística con las variables deportivas y las
   tres probabilidades del mercado.

`market_overround` no entra en las regresiones porque la Fase 3 detectó un
cambio fuerte de distribución en 2025/26.

## Protocolo temporal

La validación es walk-forward:

| Pliegue | Entrenamiento | Evaluación |
|---|---|---|
| 1 | 2016/17–2022/23 | 2023/24 |
| 2 | 2016/17–2023/24 | 2024/25 |

Los valores de regularización `C = 0.05, 0.20, 1.00 y 5.00` se compararon
exclusivamente con estos pliegues. En ambas regresiones se seleccionó
`C = 0.05`.

Después de cerrar la selección, los modelos se reentrenaron con
2016/17–2024/25 y se evaluaron una sola vez en 2025/26. La imputación, los
indicadores de ausencia y el escalado se ajustaron dentro de cada pipeline.

## Resultados de validación

| Modelo | Log Loss | Brier | Accuracy | Macro F1 | ECE |
|---|---:|---:|---:|---:|---:|
| Mercado | **0.9512** | **0.5641** | **55.26 %** | 0.4154 | 0.0245 |
| Elo multinomial | 0.9675 | 0.5754 | 54.21 % | 0.4041 | **0.0141** |
| Logística + mercado | 0.9779 | 0.5795 | 53.29 % | **0.4310** | 0.0376 |
| Logística deportiva | 0.9941 | 0.5884 | 53.16 % | 0.4158 | 0.0263 |
| Frecuencia histórica | 1.0730 | 0.6489 | 44.21 % | 0.2044 | 0.0072 |

El baseline campeón es el mercado porque obtuvo el menor Log Loss, que es el
criterio principal acordado. Elo quedó segundo y muestra que la fuerza relativa
de los equipos contiene una señal útil incluso sin cuotas.

## Prueba final 2025/26

| Modelo | Log Loss | Brier | Accuracy | Macro F1 | ECE |
|---|---:|---:|---:|---:|---:|
| Mercado | **0.9641** | **0.5715** | **54.47 %** | 0.3837 | 0.0201 |
| Logística + mercado | 0.9655 | 0.5724 | 54.21 % | **0.4349** | 0.0296 |
| Logística deportiva | 0.9759 | 0.5765 | 53.16 % | 0.4101 | 0.0350 |
| Elo multinomial | 0.9865 | 0.5826 | 52.63 % | 0.3666 | **0.0148** |
| Frecuencia histórica | 1.0493 | 0.6321 | 48.95 % | 0.2191 | 0.0255 |

La prueba confirma el orden principal: el mercado conserva la mejor calidad
probabilística. La diferencia frente a `logistic_market` es pequeña en Log
Loss, pero la logística obtiene un Macro F1 claramente mayor. Esto significa
que reparte mejor las predicciones entre las tres clases, aunque sus
probabilidades todavía no superan a las cuotas.

## Interpretación

- Las cuotas constituyen un baseline difícil de superar y deberán permanecer
  como referencia, no como garantía de rentabilidad.
- La logística deportiva alcanza un Log Loss de 0.9759 sin utilizar cuotas.
  Esta será la referencia correcta para medir modelos deportivos posteriores.
- El modelo de Elo es competitivo pese a utilizar una sola familia de
  información.
- El empate continúa siendo la clase más difícil. Por ello Accuracy y Macro F1
  cuentan una historia diferente; no debe seleccionarse un modelo usando solo
  aciertos.
- La regularización más fuerte (`C = 0.05`) fue preferida en ambas regresiones,
  coherente con la multicolinealidad observada en la Fase 3.
- En la logística con mercado, las probabilidades local y visitante del mercado
  son los coeficientes dominantes. Entre las variables deportivas destacan la
  tasa de victoria previa, la posición, la forma y la producción ofensiva.

## Artefactos generados

- Métricas de validación y prueba.
- Predicciones por partido para los cinco modelos.
- Curvas/tablas de calibración.
- Matrices de confusión.
- Coeficientes de ambas regresiones.
- Pipelines de evaluación entrenados hasta 2024/25.
- Pipelines de producción reentrenados hasta 2025/26.
- Cinco visualizaciones y controles automáticos de calidad.

## Conclusión

La Fase 4 deja dos referencias claras:

- **Baseline global:** mercado sin margen, Log Loss 0.9641 en prueba.
- **Baseline puramente deportivo:** regresión logística, Log Loss 0.9759.

Un modelo posterior solo debe considerarse una mejora real si supera estas
referencias fuera de muestra y conserva una calibración razonable. El siguiente
paso es modelar goles con Poisson y Dixon-Coles, convertir sus distribuciones de
marcadores a probabilidades 1X2 y compararlas con estos mismos baselines.

