# Fase 7 — Calibración y ensembles

## Objetivo

La Fase 7 combina las probabilidades de mercado, Random Forest, regresión
logística y Poisson. El objetivo principal continúa siendo minimizar el
**Log Loss**, porque la salida del proyecto debe ser una distribución
probabilística 1X2 y no únicamente una clase.

Se mantienen dos productos separados:

- **Ensemble deportivo:** no utiliza cuotas y puede producir las predicciones
  preliminares de LaLiga 2026/27.
- **Ensemble con mercado:** utiliza probabilidades implícitas normalizadas y
  solo debe ejecutarse cuando existan cuotas actuales del partido.

## Protocolo temporal

La calibración y los pesos se seleccionaron exclusivamente con predicciones
walk-forward de:

| Pliegue | Entrenamiento | Evaluación |
|---|---|---|
| 1 | 2016/17–2022/23 | 2023/24 |
| 2 | 2016/17–2023/24 | 2024/25 |

La temporada 2025/26 se abrió una sola vez después de congelar temperaturas y
pesos. No intervino en ninguna decisión.

## Calibración

Cada componente usa calibración por temperatura:

\[
p'_k =
\frac{\exp(\log(p_k)/T)}
{\sum_j \exp(\log(p_j)/T)}
\]

El parámetro \(T\) se limita al intervalo 0.60–1.80. Es un calibrador de una
sola variable, elegido para reducir el riesgo de sobreajuste con 760 partidos
de validación.

## Selección de pesos

Los ensembles son mezclas lineales:

\[
p_{\text{ensemble}} = \sum_m w_m p'_m
\]

con \(w_m \ge 0\), \(\sum_m w_m=1\) y pasos de 0.05. Se evaluaron 2,002
combinaciones.

### Ensemble deportivo

| Componente | Peso |
|---|---:|
| Random Forest deportivo | 55 % |
| Regresión logística deportiva | 10 % |
| Poisson | 35 % |

### Ensemble con mercado

| Componente | Peso |
|---|---:|
| Mercado normalizado | 90 % |
| Random Forest con mercado | 5 % |
| Regresión logística con mercado | 5 % |
| Poisson | 0 % |

El peso cero de Poisson en el ensemble de mercado es un resultado de la
selección, no una exclusión previa.

## Resultados

| Modelo | Validación Log Loss | Prueba 2025/26 Log Loss |
|---|---:|---:|
| Ensemble con mercado | 0.9460 | 0.9588 |
| Mercado sin margen | 0.9512 | 0.9641 |
| Ensemble deportivo | 0.9642 | 0.9672 |
| Random Forest deportivo | 0.9703 | 0.9711 |
| Regresión logística deportiva | 0.9941 | 0.9759 |
| Poisson | 0.9780 | 0.9844 |

El ensemble con mercado mejora 0.0053 puntos de Log Loss frente al mercado en
2025/26. El ensemble deportivo mejora 0.0039 frente a Random Forest deportivo.
En ambos casos el intervalo bootstrap del cambio incluye cero; por tanto, son
mejoras observadas, pero aún no evidencia concluyente de superioridad.

## Predicciones 2026/27

Se generaron 380 predicciones preliminares usando exclusivamente el ensemble
deportivo:

- Victorias locales esperadas: 177.1.
- Empates esperados: 104.3.
- Victorias visitantes esperadas: 98.6.

Estas cantidades son sumas de probabilidades, no conteos de la clase más
probable. Las predicciones usan una fotografía estática de pretemporada y deben
actualizarse después de cada jornada.

## Decisión para la Fase 8

- Usar `ensemble_sports` como fuente probabilística inicial para simular
  LaLiga 2026/27 mientras no existan cuotas.
- Usar `ensemble_market` como pronóstico principal cuando haya cuotas actuales.
- Conservar Poisson para generar marcadores y goles esperados en la simulación.
- Mantener ambos ensembles bajo seguimiento; una temporada adicional permitirá
  evaluar si las pequeñas mejoras son persistentes.
