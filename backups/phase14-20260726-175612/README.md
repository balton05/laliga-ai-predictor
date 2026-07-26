# LaLiga AI Predictor 2026/27

Proyecto de Ciencia de Datos para predecir resultados 1X2, modelar goles,
simular la temporada 2026/27 y evaluar probabilidades frente al mercado.

## Estado actual

La Fase 1 implementa:

- Auditoría de 10 temporadas de LaLiga y 5 de Segunda.
- Exclusión del CSV incorrecto de Segunda 2023/24.
- Normalización de fechas, divisiones y nombres de equipos.
- Dataset maestro con una fila por partido.
- Historial largo con una fila por equipo y partido.
- Identificación automática de ascendidos históricos.
- Estadísticas previas de Segunda para las cohortes disponibles.
- Normalización y validación de los 380 partidos del calendario 2026/27.

La Fase 2 implementa:

- Variables móviles de 5 y 10 partidos con desplazamiento temporal.
- Rendimiento acumulado de la temporada antes de cada encuentro.
- Rendimiento específico como local y visitante.
- Posición de liga al inicio del día del partido.
- Días de descanso usando únicamente fechas históricas reales.
- Elo previo con ventaja de local y regresión entre temporadas.
- Contexto de ascenso desde Segunda.
- Probabilidades implícitas de las cuotas, corregidas por margen.
- Diferencias local–visitante.
- División temporal fija para entrenamiento, validación y prueba.
- Estado inicial de los 20 equipos para LaLiga 2026/27.
- Pruebas de invariancia contra fuga de información.

La Fase 3 implementa:

- Distribución histórica de resultados, goles y ventaja local.
- Análisis de marcadores frecuentes.
- Rendimiento de 27 temporadas-equipo de ascendidos.
- Calibración de las probabilidades del mercado.
- Backtesting descriptivo de apostar siempre al favorito.
- Ausencia de datos por variable y conjunto temporal.
- Asociación de variables con el 1X2 usando solo entrenamiento.
- Detección de cambios de distribución y multicolinealidad.
- Siete visualizaciones reproducibles.
- Dashboard Excel para revisar los principales resultados.

La Fase 4 implementa:

- Baseline de frecuencia histórica.
- Probabilidades de mercado normalizadas sin margen.
- Conversión de Elo a probabilidades 1X2 mediante regresión multinomial.
- Regresión logística deportiva con 72 variables.
- Regresión logística con 75 variables deportivas y de mercado.
- Selección de regularización mediante validación walk-forward.
- Evaluación final única en la temporada 2025/26.
- Log Loss, Brier Score, Accuracy, Macro F1 y calibración.
- Pipelines reproducibles de evaluación y producción.

La Fase 5 implementa:

- Poisson independiente con fuerzas de ataque, defensa y ventaja local.
- Corrección Dixon–Coles para marcadores bajos.
- Ponderación temporal con semivida seleccionada mediante walk-forward.
- Distribuciones de marcadores de 0–0 a 10–10.
- Conversión a probabilidades 1X2, goles esperados y tres marcadores probables.
- Comparación directa con mercado, Elo y regresiones de la Fase 4.
- Ajuste conservador para Racing, Deportivo y Málaga usando Segunda y
  cohortes históricas de ascendidos.
- Predicciones preliminares de los 380 partidos de 2026/27.
- Modelos reproducibles de evaluación y producción.

La Fase 6 implementa:

- Random Forest deportivo y con probabilidades de mercado.
- HistGradientBoosting deportivo y con probabilidades de mercado.
- 64 configuraciones evaluadas mediante validación walk-forward.
- Suavizado de probabilidades seleccionado sin utilizar 2025/26.
- Evaluación final única en 2025/26.
- Intervalos bootstrap pareados frente a los baselines.
- Importancia por permutación calculada sobre validación 2024/25.
- Modelos de evaluación y producción serializados.
- 380 predicciones avanzadas preliminares para 2026/27.

La Fase 7 implementa:

- Calibración por temperatura de seis componentes.
- Ensemble deportivo sin cuotas y ensemble con mercado.
- Selección de pesos mediante validación walk-forward.
- Comparaciones bootstrap pareadas frente a las referencias.
- 380 probabilidades preliminares del ensemble deportivo para 2026/27.

La Fase 8 implementa:

- 50,000 simulaciones Monte Carlo de la temporada completa.
- Resultados 1X2 sorteados con el ensemble deportivo.
- Marcadores Poisson condicionados al resultado sorteado.
- Desempate mediante mini-liga entre equipos igualados a puntos.
- Probabilidades de campeón, Top 4, Top 6, Top 7 y descenso.
- Distribución completa de posiciones y puntos P05–P95.
- Diagnóstico de convergencia y dashboard Excel.

La Fase 9 implementa:

- Plantillas canónicas para resultados y cuotas 1X2 de 2026/27.
- Validación contra los 380 `fixture_id` del calendario oficial.
- Actualización por jornada de forma 5/10, local/visita, tabla, descanso y Elo.
- Random Forest y logística congelados; Poisson reentrenado con resultados nuevos.
- Selección automática por partido entre ensemble deportivo y ensemble con mercado.
- Simulación de 50,000 temporadas con los resultados jugados fijados.
- Historial de ejecuciones, `update_id` determinista y snapshots con SHA-256.
- Dashboard operativo para próxima jornada, tabla y cambios frente a pretemporada.

La Fase 10 implementa:

- API REST con FastAPI y documentación automática OpenAPI/Swagger.
- Persistencia PostgreSQL para calendario, resultados, cuotas, predicciones,
  tabla, simulaciones, posiciones e historial de actualizaciones.
- Sincronización transaccional desde los resultados validados de la Fase 9.
- Endpoints de consulta con filtros por jornada, equipo, estado y modelo.
- Endpoint controlado para actualizar una jornada sin sobrescribir resultados
  confirmados.
- Docker Compose para ejecutar API y PostgreSQL con un solo comando.
- Esquema SQL, colección Postman y pruebas de integración con SQLite.
- Dependencia de scikit-learn fijada a la familia 1.8 para conservar la
  compatibilidad de los modelos serializados.

La Fase 11 implementa:

- Proyecto Power BI Desktop en formato PBIP/PBIR.
- Nueve vistas analíticas PostgreSQL con contrato estable.
- Modelo semántico con 10 tablas, 6 relaciones y 29 medidas DAX.
- Seis páginas interactivas y 26 visuales.
- Filtros por equipo y jornada.
- Consumo principal de PostgreSQL y estado operativo desde FastAPI.
- Tema visual, parámetros de conexión y modo Import.
- Controles de conciliación y validación estructural oficial de PBIR.

La Fase 12 implementa:

- Aplicación web responsive con Angular 20.
- Cinco vistas: resumen, pronósticos, calendario, clasificación y simulación.
- Consumo de FastAPI con fallback explícito a la fotografía de pretemporada.
- Filtros por jornada y equipo sobre los 380 encuentros.
- Probabilidades 1X2, marcador esperado, xG y nivel de confianza.
- Proyecciones Monte Carlo de campeón, Top 4, Top 7 y descenso.
- CORS configurable y servicio web incorporado a Docker Compose.
- Diseño coherente con el tema visual de Power BI de la Fase 11.

## Estructura

```text
data/
  raw/
    laliga/
    segunda/
    fixtures/
  processed/
notebooks/
reports/
scripts/
src/laliga_predictor/
  api/
frontend/
database/
tests/
```

El esquema de cada salida está documentado en
`docs/data_dictionary.md`.

## Instalación en Windows

Desde PowerShell, dentro de la carpeta del proyecto:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

No es obligatorio activar el entorno virtual. Esto evita el error de
`ExecutionPolicy` que puede aparecer al ejecutar `Activate.ps1`.

## Construir los datasets de la Fase 1

```powershell
.venv\Scripts\python.exe scripts\build_phase1.py
```

## Construir los datasets de la Fase 2

```powershell
.venv\Scripts\python.exe scripts\build_phase2.py
```

El script reconstruye primero la Fase 1 para garantizar que todas las variables
se calculen desde los CSV originales válidos.

## Construir el análisis de la Fase 3

```powershell
.venv\Scripts\python.exe scripts\build_phase3.py
```

El informe interpretado se encuentra en `docs/phase3_eda_report.md` y el
notebook reproducible en `notebooks/03_exploratory_analysis.ipynb`.

## Entrenar los baselines de la Fase 4

```powershell
.venv\Scripts\python.exe scripts\build_phase4.py
```

El informe está en `docs/phase4_baseline_report.md` y el notebook reproducible
en `notebooks/04_baseline_models.ipynb`.

## Entrenar los modelos de goles de la Fase 5

```powershell
.venv\Scripts\python.exe scripts\build_phase5.py
```

El informe está en `docs/phase5_goal_models_report.md` y el notebook reproducible
en `notebooks/05_goal_models.ipynb`.

## Entrenar los modelos avanzados de la Fase 6

```powershell
.venv\Scripts\python.exe scripts\build_phase6.py
```

El informe está en `docs/phase6_advanced_models_report.md` y el notebook
reproducible en `notebooks/06_advanced_models.ipynb`.

## Calibrar y combinar modelos en la Fase 7

```powershell
.venv\Scripts\python.exe scripts\build_phase7.py
```

El informe está en `docs/phase7_ensemble_report.md` y el notebook reproducible
en `notebooks/07_calibration_ensembles.ipynb`.

## Simular la temporada en la Fase 8

```powershell
.venv\Scripts\python.exe scripts\build_phase8.py
```

El informe está en `docs/phase8_monte_carlo_report.md` y el notebook
reproducible en `notebooks/08_monte_carlo_simulation.ipynb`.

## Actualizar la temporada en la Fase 9

Primero completa los archivos:

- `data/incoming/results_2026_27.csv`
- `data/incoming/odds_2026_27.csv`

Después ejecuta:

```powershell
.venv\Scripts\python.exe scripts\update_season.py
```

Los resultados deben cargarse por jornada completa. Para un seguimiento antes
de que terminen los diez partidos:

```powershell
.venv\Scripts\python.exe scripts\update_season.py --allow-partial
```

El informe está en `docs/phase9_dynamic_updates_report.md` y el notebook
reproducible en `notebooks/09_dynamic_updates.ipynb`.

## Ejecutar la API y PostgreSQL — Fase 10

La forma recomendada es Docker Compose:

```powershell
docker compose up --build
```

Servicios disponibles:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Estado: `http://localhost:8000/health`

Para ejecutar la API localmente contra un PostgreSQL existente:

```powershell
Copy-Item .env.example .env
.venv\Scripts\python.exe scripts\init_database.py
.venv\Scripts\python.exe scripts\serve_api.py
```

El informe técnico está en `docs/phase10_api_postgresql_report.md` y la
colección de consultas en `docs/laliga_phase10.postman_collection.json`.

## Abrir el dashboard de Power BI — Fase 11

Con Docker Compose ya iniciado, abre:

```text
powerbi/LaLigaAIPredictor/LaLigaAIPredictor.pbip
```

Después configura las credenciales de PostgreSQL y pulsa **Actualizar**. El
proyecto usa `localhost:5432`, la base `laliga_predictor` y
`http://localhost:8000` como valores predeterminados.

Para reconstruir el proyecto y sus controles:

```powershell
.venv\Scripts\python.exe scripts\build_phase11.py
```

La guía completa está en `docs/phase11_powerbi_report.md`.

## Ejecutar las comprobaciones

```powershell
.venv\Scripts\python.exe -m pytest
```

## Salidas principales

| Archivo | Contenido |
|---|---|
| `data/processed/matches_master.csv` | Partidos históricos normalizados |
| `data/processed/team_match_history.csv` | Una fila por equipo y partido |
| `data/processed/fixtures_2026_27.csv` | Calendario futuro normalizado |
| `data/processed/historical_promotions.csv` | 30 registros de ascenso |
| `data/processed/promoted_teams_2026_27.csv` | Racing, Deportivo y Málaga |
| `data/processed/team_name_mapping.csv` | IDs, nombres y alias |
| `reports/data_audit.csv` | Auditoría por archivo |
| `reports/column_coverage.csv` | Cobertura de columnas |
| `reports/phase1_summary.json` | Resumen de ejecución |

## Salidas principales de la Fase 2

| Archivo | Contenido |
|---|---|
| `data/processed/laliga_model_dataset.csv` | Dataset recomendado con 76 variables para el primer modelo |
| `data/processed/laliga_match_features.csv` | Tabla completa de candidatos para 3,800 partidos de Primera |
| `data/processed/all_match_features.csv` | Variables para 6,110 partidos de Primera y Segunda |
| `data/processed/team_pre_match_features.csv` | Perspectiva prepartido de cada equipo |
| `data/processed/team_preseason_state_2026_27.csv` | Estado inicial de los 20 equipos |
| `data/processed/fixtures_2026_27_preseason_features.csv` | Calendario unido al estado estático de pretemporada |
| `reports/feature_manifest.csv` | Rol, grupo, tipo y cobertura de cada columna |
| `reports/phase2_quality_checks.csv` | Comprobaciones automáticas de calidad |
| `reports/phase2_summary.json` | Resumen de la Fase 2 |

## Salidas principales de la Fase 3

| Archivo | Contenido |
|---|---|
| `reports/eda_season_summary.csv` | Resultados, goles, localía y mercado por temporada |
| `reports/eda_common_scorelines.csv` | Frecuencia histórica de marcadores |
| `reports/eda_promoted_performance.csv` | Rendimiento de los ascendidos en Primera |
| `reports/eda_market_calibration.csv` | Calibración de probabilidades por split |
| `reports/eda_favorite_strategy.csv` | Backtesting de apostar siempre al favorito |
| `reports/eda_feature_associations_train.csv` | Asociación de variables usando solo entrenamiento |
| `reports/eda_feature_drift.csv` | Cambios de distribución frente a entrenamiento |
| `reports/eda_high_correlation_pairs.csv` | Pares con correlación absoluta ≥ 0.90 |
| `reports/figures/` | Siete gráficos en PNG |
| `reports/laliga_phase3_dashboard.xlsx` | Dashboard Excel con tablas, fórmulas y gráficos |
| `reports/phase3_quality_checks.csv` | Nueve controles automáticos |
| `reports/phase3_summary.json` | Resumen de la Fase 3 |

## Salidas principales de la Fase 4

| Archivo | Contenido |
|---|---|
| `reports/model_metrics.csv` | Comparación de los cinco modelos |
| `reports/model_candidate_validation.csv` | Selección temporal de regularización |
| `reports/model_predictions_validation.csv` | Predicciones walk-forward |
| `reports/model_predictions_test.csv` | Predicciones finales 2025/26 |
| `reports/model_calibration.csv` | Calibración por clase y modelo |
| `reports/model_confusion.csv` | Matrices de confusión en formato largo |
| `reports/logistic_coefficients.csv` | Coeficientes estandarizados |
| `reports/phase4_fitted_models.joblib` | Pipelines usados en la prueba final |
| `reports/phase4_production_models.joblib` | Pipelines reentrenados hasta 2025/26 |
| `reports/laliga_phase4_dashboard.xlsx` | Dashboard de comparación |
| `reports/phase4_quality_checks.csv` | Controles automáticos |
| `reports/phase4_summary.json` | Resumen de la Fase 4 |

## Salidas principales de la Fase 5

| Archivo | Contenido |
|---|---|
| `reports/goal_model_candidate_validation.csv` | Selección temporal de semivida |
| `reports/goal_model_metrics.csv` | Métricas 1X2 y de goles |
| `reports/phase5_model_comparison.csv` | Poisson y Dixon–Coles frente a baselines |
| `reports/goal_model_predictions_validation.csv` | Predicciones walk-forward |
| `reports/goal_model_predictions_test.csv` | Predicciones finales 2025/26 |
| `reports/goal_model_team_strengths.csv` | Fuerza ofensiva y vulnerabilidad defensiva |
| `reports/promoted_strength_adjustment.csv` | Inicialización de los tres ascendidos |
| `data/processed/fixtures_2026_27_goal_predictions.csv` | 380 predicciones preliminares |
| `reports/phase5_fitted_models.joblib` | Modelos usados en la prueba final |
| `reports/phase5_production_models.joblib` | Modelos reentrenados hasta 2025/26 |
| `reports/laliga_phase5_dashboard.xlsx` | Dashboard de modelos de goles |
| `reports/phase5_quality_checks.csv` | Controles automáticos |
| `reports/phase5_summary.json` | Resumen de la Fase 5 |

## Salidas principales de la Fase 6

| Archivo | Contenido |
|---|---|
| `reports/advanced_model_candidate_validation.csv` | Búsqueda temporal de 64 configuraciones |
| `reports/advanced_model_metrics.csv` | Métricas de los cuatro modelos avanzados |
| `reports/phase6_model_comparison.csv` | Comparación con mercado, logística y Poisson |
| `reports/advanced_model_bootstrap_comparison.csv` | Intervalos pareados de mejora |
| `reports/advanced_model_feature_importance.csv` | Importancia por permutación |
| `reports/advanced_model_predictions_validation.csv` | Predicciones walk-forward |
| `reports/advanced_model_predictions_test.csv` | Predicciones finales 2025/26 |
| `data/processed/fixtures_2026_27_advanced_predictions.csv` | 380 predicciones preliminares |
| `reports/phase6_fitted_models.joblib` | Modelos usados en la prueba |
| `reports/phase6_production_models.joblib` | Modelos reentrenados hasta 2025/26 |
| `reports/laliga_phase6_dashboard.xlsx` | Dashboard de modelos avanzados |
| `reports/phase6_quality_checks.csv` | Controles automáticos |
| `reports/phase6_summary.json` | Resumen de la Fase 6 |

## Salidas principales de la Fase 7

| Archivo | Contenido |
|---|---|
| `reports/ensemble_component_calibration.csv` | Temperaturas y efecto de calibración |
| `reports/ensemble_weight_candidates.csv` | Rejilla de 2,002 combinaciones de pesos |
| `reports/ensemble_predictions_validation.csv` | Predicciones de los ensembles en validación |
| `reports/ensemble_predictions_test.csv` | Predicciones finales 2025/26 |
| `reports/ensemble_metrics.csv` | Comparación con los modelos componentes |
| `reports/ensemble_calibration.csv` | Calibración por clase y decil |
| `reports/ensemble_bootstrap_comparison.csv` | Incertidumbre de las mejoras |
| `reports/phase7_production_ensemble.joblib` | Ensemble deportivo listo para producción |
| `data/processed/fixtures_2026_27_ensemble_predictions.csv` | 380 probabilidades preliminares |
| `reports/laliga_phase7_dashboard.xlsx` | Dashboard de calibración y ensembles |
| `reports/phase7_quality_checks.csv` | Controles automáticos |
| `reports/phase7_summary.json` | Resumen de la Fase 7 |

## Salidas principales de la Fase 8

| Archivo | Contenido |
|---|---|
| `data/processed/fixtures_2026_27_simulation_inputs.csv` | Probabilidades y goles esperados usados por el simulador |
| `reports/season_simulation_summary.csv` | Puntos, posición y probabilidades por equipo |
| `reports/season_position_distribution.csv` | Probabilidad de cada equipo en cada posición |
| `reports/simulation_convergence.csv` | Estabilidad por número de simulaciones |
| `reports/figures/27_*.png`–`30_*.png` | Gráficos principales de la simulación |
| `reports/laliga_phase8_dashboard.xlsx` | Dashboard de Monte Carlo |
| `reports/phase8_quality_checks.csv` | 22 controles automáticos |
| `reports/phase8_summary.json` | Resumen de la Fase 8 |

## Salidas principales de las Fases 9 y 10

| Archivo | Contenido |
|---|---|
| `data/incoming/results_2026_27.csv` | Entrada canónica de resultados |
| `data/incoming/odds_2026_27.csv` | Historial de capturas de cuotas |
| `data/processed/current_predictions_2026_27.csv` | Pronósticos dinámicos pendientes |
| `reports/current_table_2026_27.csv` | Tabla actual |
| `reports/dynamic_season_simulation_summary.csv` | Monte Carlo actualizado |
| `reports/phase9_update_log.csv` | Historial reproducible por `update_id` |
| `snapshots/` | Archivos y hashes de cada actualización |
| `database/001_initial_schema.sql` | Esquema PostgreSQL documentado |
| `docker-compose.yml` | API y PostgreSQL |
| `reports/phase10_quality_checks.csv` | Controles de la API |
| `reports/phase10_summary.json` | Resumen de la Fase 10 |

## Salidas principales de la Fase 11

| Archivo | Contenido |
|---|---|
| `powerbi/LaLigaAIPredictor/LaLigaAIPredictor.pbip` | Punto de entrada del proyecto Power BI |
| `powerbi/LaLigaAIPredictor/LaLigaAIPredictor.SemanticModel/model.bim` | Modelo semántico, Power Query y DAX |
| `powerbi/LaLigaAIPredictor/LaLigaAIPredictor.Report/` | Seis páginas PBIR y 26 visuales |
| `database/002_powerbi_views.sql` | Nueve vistas analíticas PostgreSQL |
| `powerbi/preview_data/` | Datos compactos para auditar el dashboard |
| `reports/phase11_pbir_validation.json` | Validación estructural del reporte |
| `reports/phase11_quality_checks.csv` | Controles de conciliación |
| `reports/phase11_summary.json` | Resumen de la Fase 11 |

## Precauciones metodológicas

- `reference_date` es la fecha general de la jornada, no el horario definitivo.
- La posición reconstruida usa puntos, diferencia de goles y goles anotados.
  LaLiga utiliza desempates adicionales; esta posición funciona como proxy.
- Los playoffs de ascenso no aparecen en los CSV de liga regular. El tipo de
  ascenso se infiere al cruzar la posición regular con los equipos de la
  temporada siguiente.
- Las estadísticas posteriores al partido no se usarán directamente como
  variables predictoras. En la Fase 2 se calcularán con `shift(1)` para evitar
  fuga de información.
- `fixtures_2026_27_preseason_features.csv` es una fotografía estática. Para
  predecir jornadas posteriores deberá actualizarse con los resultados reales
  o simulados de los partidos anteriores.
- `segunda_position` está vacío para clubes no ascendidos. Debe imputarse dentro
  de un pipeline de modelado junto al indicador `promoted`, nunca usando todo el
  dataset antes de separar entrenamiento y prueba.
- Las asociaciones de la Fase 3 se calculan únicamente con entrenamiento.
- Los análisis descriptivos pueden mostrar 2025/26, pero no deben usarse para
  tomar decisiones sobre el modelo.
- `market_overround` cambió de distribución en 2025/26. Las probabilidades sin
  margen son más comparables entre temporadas.
- La selección de la Fase 4 utiliza únicamente 2023/24 y 2024/25 en un esquema
  walk-forward. 2025/26 se evalúa una sola vez después de cerrar el modelo.
- Las predicciones 2026/27 de la Fase 5 son una fotografía de pretemporada. Los
  equipos ascendidos tienen confianza baja y todos los parámetros deberán
  actualizarse después de cada jornada.
- La ligera mejora de Random Forest mercado en 2025/26 no es estadísticamente
  concluyente: el intervalo bootstrap del cambio de Log Loss incluye cero.
- Las predicciones avanzadas 2026/27 usan el modelo deportivo porque aún no
  existen cuotas para los 380 partidos.
- La calibración y los pesos de la Fase 7 se seleccionan únicamente con
  2023/24–2024/25. Las mejoras observadas en 2025/26 no son estadísticamente
  concluyentes y deben confirmarse con más temporadas.
- La Fase 8 usa el Top 7 como proxy de plaza europea. La Copa del Rey y las
  plazas adicionales por rendimiento UEFA pueden modificar la asignación real.
- Los desempates simulan una mini-liga entre equipos empatados, pero no todas
  las reaplicaciones excepcionales del reglamento en empates múltiples.
- Las 50,000 temporadas usan una fotografía estática de pretemporada. El
  simulador deberá actualizarse con los resultados y estados posteriores a
  cada jornada.

## División temporal bloqueada

| Uso | Temporadas | Partidos |
|---|---|---:|
| Entrenamiento | 2016/17–2022/23 | 2,660 |
| Validación | 2023/24–2024/25 | 760 |
| Prueba final | 2025/26 | 380 |

La temporada 2025/26 no debe utilizarse para seleccionar variables,
hiperparámetros ni métodos de imputación.

## Próxima fase

La Fase 12 construirá la aplicación web en Angular, consumiendo los endpoints
de FastAPI y reutilizando el lenguaje visual y las métricas de Power BI.
