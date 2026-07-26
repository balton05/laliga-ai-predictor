# Fase 3 — Análisis exploratorio

## Alcance

El análisis utiliza los 3,800 partidos de LaLiga comprendidos entre 2016/17 y
2025/26. Las asociaciones entre variables y resultado se calculan únicamente
con el conjunto de entrenamiento (2016/17–2022/23). La temporada 2025/26
permanece bloqueada como prueba final y no debe utilizarse para seleccionar
variables, imputadores ni hiperparámetros.

## Hallazgos principales

### Resultados y localía

- Victoria local: 45.50 %.
- Empate: 26.21 %.
- Victoria visitante: 28.29 %.
- Promedio: 2.62 goles por partido.
- La temporada 2020/21 tuvo la menor proporción de triunfos locales (41.58 %)
  y la menor diferencia media de goles a favor del local (+0.23).
- La temporada 2025/26 tuvo la mayor proporción de triunfos locales (48.95 %),
  pero este dato se reporta solo de forma descriptiva por pertenecer a prueba.

La ventaja local no es una constante fija. El modelo debe conservar variables
de localía y permitir que su efecto cambie con el tiempo.

### Marcadores

Los marcadores más frecuentes fueron:

| Marcador | Partidos | Porcentaje |
|---|---:|---:|
| 1-1 | 487 | 12.82 % |
| 1-0 | 443 | 11.66 % |
| 2-1 | 362 | 9.53 % |
| 0-1 | 298 | 7.84 % |
| 0-0 | 282 | 7.42 % |

La concentración en marcadores bajos respalda probar Poisson y, más adelante,
Dixon-Coles para corregir específicamente 0-0, 1-0, 0-1 y 1-1.

### Equipos ascendidos

Se analizaron 27 temporadas-equipo de ascendidos:

- Puntos medios: 40.19.
- Mediana: 41 puntos.
- Supervivencia: 66.67 %.
- Descenso inmediato: 33.33 %.
- Diferencia de goles media: -17.74.

El ascenso no implica automáticamente descenso, pero sí una penalización clara
en diferencia de goles. `promoted`, la posición previa en Segunda y el ajuste
de Elo deben permanecer como contexto del modelo.

### Mercado y estrategia del favorito

- El favorito de las cuotas acertó el 53.74 % de los partidos.
- Apostar una unidad al favorito en todos los encuentros produjo -56.57
  unidades.
- ROI histórico: -1.49 %.

La precisión por sí sola no equivale a rentabilidad. Las cuotas son un baseline
predictivo fuerte, pero las estrategias de apuestas deben evaluarse por valor
esperado, yield y drawdown fuera de muestra.

Las probabilidades sin margen muestran calibración razonable en general. El
intervalo 60–70 % registró una frecuencia observada aproximadamente 6.7 puntos
porcentuales superior a la prevista. Este hallazgo deberá validarse en cada
ventana temporal antes de transformarse en una regla.

### Variables prepartido

En entrenamiento, las mayores asociaciones con el resultado 1X2 fueron:

1. Probabilidad de victoria visitante del mercado.
2. Probabilidad de victoria local del mercado.
3. Probabilidad local esperada por Elo.
4. Diferencia de Elo.
5. Diferencia de goles promedio en la temporada.
6. Ventaja en la posición de liga.
7. Diferencia de puntos por partido.
8. Diferencia de forma en 10 encuentros.

Esto confirma que el primer baseline debe comparar mercado, Elo y regresión
logística con forma reciente.

## Alertas para la Fase 4

### Multicolinealidad

Se detectaron 24 pares con correlación de Spearman absoluta igual o superior a
0.90. Algunos son equivalencias casi exactas:

- `elo_difference_pre` y `elo_expected_home`.
- `market_probability_home` y `market_probability_away`.
- Puntos por partido y tasa de victorias.
- Puntos por partido y posición de liga.

Para modelos lineales conviene conservar una variable representativa por
familia o aplicar regularización. Los árboles toleran mejor esta redundancia,
pero puede diluir la importancia interpretada.

### Datos faltantes

`home_segunda_position` y `away_segunda_position` tienen 94 % de valores
ausentes porque solo aplican a clubes ascendidos con datos disponibles de
Segunda. No son errores de recopilación. Se deben combinar con `promoted` y una
imputación realizada dentro del pipeline después de dividir temporalmente.

Los promedios acumulados faltan principalmente al inicio de cada temporada.
Los indicadores `history_ready_5`, `history_ready_10` y el número de partidos
previos permiten representar esa incertidumbre.

### Cambio en el margen de cuotas

`market_overround` presenta el mayor cambio estandarizado entre entrenamiento
y 2025/26. El promedio pasó del entorno de 4–5 % en la mayoría de temporadas a
6.46 % en 2025/26. Antes de emplearlo como predictor debe comprobarse si el
cambio proviene del bookmaker, del momento de captura o de la fuente.

Las probabilidades normalizadas sin margen son más comparables entre
temporadas y deben ser las variables de mercado principales.

## Decisiones para modelado

- Mantener la división temporal ya bloqueada.
- Usar imputación dentro de cada pipeline, nunca antes de separar los datos.
- Comparar modelos con y sin cuotas para medir cuánto aporta la información
  deportiva.
- Incluir un baseline de frecuencias, otro de mercado y otro de Elo.
- Usar Log Loss, Brier Score, Accuracy, Macro F1 y curvas de calibración.
- Evitar interpretar el conjunto de prueba hasta cerrar el modelo final.
- Investigar la estabilidad de `market_overround` antes de incluirlo.
- Reducir redundancia en regresión logística mediante selección por familias o
  regularización.

