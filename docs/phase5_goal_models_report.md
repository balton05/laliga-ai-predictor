# Fase 5 — Modelos de goles Poisson y Dixon–Coles

## Objetivo

Esta fase modela el número de goles de cada equipo antes del partido. A partir
de las tasas esperadas se construye una matriz de marcadores de 0–0 a 10–10 y
se obtienen:

\[
P(\text{local}),\quad P(\text{empate}),\quad P(\text{visitante})
\]

También se generan goles esperados, marcador modal y los tres marcadores más
probables.

## Modelos

### Poisson independiente

Cada equipo tiene una fuerza de ataque y una vulnerabilidad defensiva. El
modelo incluye además un intercepto de liga y una ventaja de local:

\[
\log(\lambda_{local}) =
\mu + h + ataque_{local} + defensa_{visitante}
\]

\[
\log(\lambda_{visitante}) =
\mu + ataque_{visitante} + defensa_{local}
\]

### Dixon–Coles

Dixon–Coles parte de las mismas tasas de Poisson y añade un parámetro
\(\rho\) para corregir la frecuencia conjunta de 0–0, 1–0, 0–1 y 1–1.
Esta modificación busca representar mejor la dependencia de los marcadores
bajos.

Ambos modelos aplican regularización ligera a las fuerzas de los equipos.

## Protocolo temporal

La semivida de la ponderación temporal se seleccionó únicamente con validación
walk-forward:

| Pliegue | Entrenamiento | Evaluación |
|---|---|---|
| 1 | 2016/17–2022/23 | 2023/24 |
| 2 | 2016/17–2023/24 | 2024/25 |

Se compararon semividas de 365, 730 y 1,460 días, además de una versión sin
decaimiento. Los dos modelos seleccionaron 365 días. Después de cerrar esta
decisión, se reentrenaron con 2016/17–2024/25 y se evaluaron una sola vez en
2025/26.

## Resultados de validación

| Modelo | Log Loss | Brier | Accuracy | Macro F1 | MAE goles | Marcador exacto |
|---|---:|---:|---:|---:|---:|---:|
| Poisson | **0.9780** | 0.5818 | 52.50 % | 0.3894 | 0.8645 | **14.34 %** |
| Dixon–Coles | 0.9780 | **0.5818** | **52.76 %** | **0.3909** | **0.8645** | 13.68 % |

Poisson ganó por una diferencia mínima de Log Loss: 0.977951 frente a
0.978036. La corrección Dixon–Coles tampoco fue inútil: obtuvo una calibración
ligeramente mejor y un Macro F1 marginalmente superior.

## Prueba final 2025/26

| Modelo | Log Loss | Brier | Accuracy | Macro F1 | MAE goles | Marcador exacto |
|---|---:|---:|---:|---:|---:|---:|
| Poisson | **0.9844** | **0.5842** | 50.79 % | 0.3522 | **0.8171** | 15.79 % |
| Dixon–Coles | 0.9846 | 0.5843 | 50.79 % | 0.3522 | 0.8172 | **16.84 %** |

Dixon–Coles acertó más marcadores exactos, pero el criterio principal continúa
siendo Log Loss 1X2; por ello Poisson permanece como modelo de goles
seleccionado.

## Comparación con los baselines

| Modelo | Log Loss validación | Log Loss prueba |
|---|---:|---:|
| Mercado | **0.9512** | **0.9641** |
| Elo multinomial | 0.9675 | 0.9865 |
| Logística + mercado | 0.9779 | 0.9655 |
| Poisson | 0.9780 | 0.9844 |
| Dixon–Coles | 0.9780 | 0.9846 |
| Logística deportiva | 0.9941 | 0.9759 |

En validación, Poisson superó a la logística deportiva. Sin embargo, en la
prueba 2025/26 quedó 0.0086 por encima de ese baseline y 0.0203 por encima del
mercado. Por tanto, todavía no existe evidencia para reemplazar al mercado ni a
la regresión deportiva como modelo 1X2 principal.

El aporte de esta fase está en otro nivel: entrega una distribución completa de
goles y marcadores que los modelos multinomiales de la Fase 4 no producen.

## Ajuste de los ascendidos 2026/27

Racing, Deportivo y Málaga se inicializan usando sus tasas de goles de Segunda
y 12 cohortes históricas con datos completos antes y después del ascenso. Para
evitar sobreajuste con una muestra pequeña:

- Se usa como ancla la mediana de los ascendidos directos o por playoff.
- El rendimiento individual en Segunda modifica esa ancla con elasticidad 0.35.
- Los efectos latentes se reducen y limitan a ±0.45.
- La confianza se marca como baja.

| Equipo | GF inicial por partido | GC inicial por partido | Confianza |
|---|---:|---:|---|
| Racing de Santander | 1.185 | 1.992 | Baja |
| RC Deportivo | 1.058 | 1.777 | Baja |
| Málaga CF | 1.104 | 1.516 | Baja |

Estos valores no equivalen a resultados definitivos de Primera. Funcionan como
prior de pretemporada y deberán actualizarse con los partidos reales de
2026/27.

## Predicciones preliminares 2026/27

El modelo Poisson de producción fue reentrenado con todas las temporadas hasta
2025/26 y generó los 380 partidos del calendario. Cada fila contiene:

- Goles esperados local y visitante.
- Probabilidades local, empate y visitante.
- Marcador más probable y dos alternativas.
- Indicador de ajuste de ascendido.
- Nivel de confianza.
- Indicador de actualización dinámica obligatoria.

Las fechas actuales son referencias de jornada. Estas predicciones no incluyen
horarios definitivos, cuotas 2026/27, lesiones ni sanciones.

## Conclusión

La Fase 5 deja un modelo de goles reproducible y útil para simulación, pero no
supera los baselines 1X2 en la prueba final. Esto evita una conclusión
optimista incorrecta: obtener marcadores plausibles no implica automáticamente
mejorar la calidad probabilística del resultado.

La siguiente fase probará Random Forest y modelos de boosting, y después
evaluará un ensemble que combine señales deportivas, mercado y distribución de
goles.
