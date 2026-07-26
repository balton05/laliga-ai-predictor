# Fase 6 — Random Forest y boosting para el resultado 1X2

## Objetivo

La Fase 6 evalúa si modelos no lineales pueden mejorar las probabilidades 1X2
de las fases anteriores. Se mantienen dos variantes:

- **Deportiva:** 72 variables prepartido, sin cuotas.
- **Mercado:** las 72 variables deportivas más las tres probabilidades de
  mercado normalizadas.

No se utilizaron estadísticas del partido que se está prediciendo. Todas las
variables históricas proceden de cálculos desplazados con `shift(1)`.

## Protocolo temporal

La búsqueda de hiperparámetros utilizó exclusivamente:

| Pliegue | Entrenamiento | Evaluación |
|---|---|---|
| 1 | 2016/17–2022/23 | 2023/24 |
| 2 | 2016/17–2023/24 | 2024/25 |

Después de cerrar la configuración se entrenó hasta 2024/25 y se abrió una sola
vez la prueba final 2025/26. Finalmente, los modelos de producción se
reentrenaron hasta 2025/26.

## Modelos y búsqueda

Se probaron:

- Random Forest con 400 árboles, distintas profundidades, mínimos por hoja,
  selección de variables y ponderación de clases.
- HistGradientBoosting con distintas tasas de aprendizaje, número de hojas,
  regularización L2 y número de iteraciones.
- Suavizado opcional hacia la frecuencia histórica de clases con pesos de
  0 %, 5 %, 10 % o 20 %, seleccionado solo en validación.

La búsqueda contiene 64 configuraciones combinadas: 16 por cada una de las
cuatro variantes.

## Configuraciones seleccionadas

| Modelo | Configuración | Suavizado |
|---|---|---:|
| Random Forest deportivo | profundidad 6, hoja mínima 10, `sqrt` | 0 % |
| Random Forest mercado | profundidad 6, hoja mínima 10, `sqrt` | 0 % |
| Boosting deportivo | LR 0.03, 250 iteraciones, 7 hojas, L2=1 | 10 % |
| Boosting mercado | LR 0.03, 250 iteraciones, 7 hojas, L2=1 | 5 % |

## Resultados

### Validación walk-forward

| Modelo | Log Loss | Accuracy | Macro F1 |
|---|---:|---:|---:|
| Mercado sin margen | 0.9512 | 55.26 % | 0.4154 |
| Random Forest mercado | 0.9558 | 54.74 % | 0.4098 |
| Boosting mercado | 0.9690 | 55.00 % | 0.4672 |
| Random Forest deportivo | 0.9703 | 54.47 % | 0.4093 |
| Boosting deportivo | 0.9847 | 53.16 % | 0.4374 |
| Logística deportiva | 0.9941 | 53.16 % | 0.4158 |

El mercado conserva el mejor Log Loss de validación. Boosting logra un Macro
F1 más alto, lo que indica mejor equilibrio entre local, empate y visitante,
pero sus probabilidades son menos precisas que las del mercado.

### Prueba final 2025/26

| Modelo | Log Loss | Accuracy | Macro F1 | ECE |
|---|---:|---:|---:|---:|
| Random Forest mercado | 0.9635 | 53.95 % | 0.3868 | 0.0176 |
| Mercado sin margen | 0.9641 | 54.47 % | 0.3837 | 0.0201 |
| Logística mercado | 0.9655 | 54.21 % | 0.4349 | 0.0296 |
| Random Forest deportivo | 0.9711 | 53.16 % | 0.3797 | 0.0175 |
| Logística deportiva | 0.9759 | 53.16 % | 0.4101 | 0.0350 |
| Boosting mercado | 0.9801 | 53.95 % | 0.4595 | 0.0339 |
| Boosting deportivo | 0.9829 | 52.63 % | 0.4446 | 0.0231 |
| Poisson | 0.9844 | 50.79 % | 0.3522 | 0.0313 |

Random Forest mercado supera al mercado por 0.00064 de Log Loss en la prueba,
pero el intervalo bootstrap del cambio es `[-0.0126, 0.0112]`. Random Forest
deportivo mejora a la logística deportiva por 0.00477, con intervalo
`[-0.0286, 0.0182]`. Ambos intervalos incluyen cero: son mejoras observadas,
no evidencia concluyente de superioridad.

## Variables más influyentes

En los modelos con mercado, las tres probabilidades normalizadas son las señales
dominantes. En los modelos deportivos predominan:

- Diferencia de Elo.
- Probabilidad local derivada de Elo.
- Elo previo de ambos equipos.
- Diferencia de goles acumulada.
- Posición previa.
- Diferencia reciente de tiros a puerta.

La importancia se calculó mediante permutación sobre 2024/25, no sobre la prueba
final.

## Predicciones preliminares 2026/27

Las 380 predicciones avanzadas usan Random Forest deportivo, porque todavía no
existen cuotas para toda la temporada. Son una fotografía estática de
pretemporada:

- No incorporan cuotas actuales.
- No incorporan resultados de jornadas anteriores.
- Los partidos con Racing, Deportivo o Málaga se marcan con confianza baja.
- Todas las filas tienen `requires_dynamic_update = True`.

Ningún empate aparece como la clase de mayor probabilidad en esta fotografía,
pero el modelo asigna en conjunto 111.6 “partidos esperados” al empate al sumar
sus probabilidades. La simulación deberá muestrear las tres probabilidades, no
contar únicamente la clase con mayor valor.

Después de cada jornada será necesario recalcular forma, Elo, posición y
estadísticas acumuladas antes de volver a predecir.

## Conclusión

Random Forest es el mejor modelo avanzado de esta fase. Mejora numéricamente los
dos baselines logísticos en 2025/26 y queda prácticamente empatado con el
mercado. Boosting reconoce mejor los empates y eleva el Macro F1, pero todavía
no produce el mejor Log Loss.

La siguiente fase debe construir ensembles definidos exclusivamente en
validación, calibrar sus probabilidades y comprobar si la combinación de
mercado, Random Forest, logística y Poisson ofrece una mejora más estable.
