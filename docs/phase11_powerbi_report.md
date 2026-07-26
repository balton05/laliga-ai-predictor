# Fase 11 — Dashboard interactivo en Power BI

## Objetivo

Convertir el estado operativo de la Fase 10 en un producto de análisis para
explorar calendario, probabilidades 1X2, clasificación, simulaciones Monte
Carlo y calidad de las actualizaciones. El dashboard no recalcula modelos:
consume el estado validado de PostgreSQL y consulta la salud de FastAPI.

## Entregable

El proyecto está en:

`powerbi/LaLigaAIPredictor/LaLigaAIPredictor.pbip`

Se entrega en formato Power BI Desktop Project:

- PBIR para el reporte, con una definición JSON independiente por visual.
- TMSL (`model.bim`) para el modelo semántico.
- Tema visual registrado.
- Parámetros para PostgreSQL y FastAPI.
- Fuentes en modo Import por defecto.

## Arquitectura

1. La Fase 9 actualiza resultados, predicciones y Monte Carlo.
2. La Fase 10 sincroniza el estado validado en PostgreSQL.
3. Nueve vistas `bi_*` forman un contrato analítico estable.
4. Power Query importa las vistas y consulta `GET /health`.
5. El modelo semántico aplica relaciones, formatos y medidas DAX.
6. El reporte presenta seis páginas interactivas.

PostgreSQL es la fuente principal. FastAPI se usa para mostrar el estado del
servicio; los endpoints JSON quedan disponibles como alternativa de consumo.

## Páginas

| Página | Propósito |
|---|---|
| Resumen | KPIs, favoritos al título, riesgo de descenso y estado general |
| Próxima jornada | Diez partidos, probabilidades 1X2, goles esperados y confianza |
| Simulación | Campeón, Top 4, Top 7, descenso y rango de puntos |
| Clasificación | Tabla actual, puntos, goles y posición |
| Explorador de equipos | Filtro por club, calendario y distribución de posiciones |
| Calidad y actualización | `update_id`, fuente del modelo, API y controles operativos |

## Modelo semántico

- 10 tablas.
- 6 relaciones de una dimensión hacia hechos.
- 29 medidas DAX.
- 26 visuales.
- Modo Import.

Las dimensiones de equipo, jornada y posición filtran las tablas de partidos,
clasificación y simulación. Los partidos se conservan tanto en perspectiva del
fixture como en perspectiva equipo-partido para que el filtro de club funcione
sin relaciones ambiguas.

## Preparación de PostgreSQL

Al iniciar FastAPI contra PostgreSQL, la aplicación instala automáticamente las
vistas de `database/002_powerbi_views.sql`. También se pueden crear durante la
inicialización:

```powershell
.venv\Scripts\python.exe scripts\init_database.py
```

La cuenta usada por Power BI necesita `CONNECT` sobre la base y `SELECT` sobre
las vistas `bi_*`. No necesita permisos de escritura.

## Abrir y actualizar

1. Ejecutar `docker compose up --build`.
2. Comprobar `http://localhost:8000/health`.
3. Abrir `powerbi/LaLigaAIPredictor/LaLigaAIPredictor.pbip` con Power BI
   Desktop.
4. Revisar los parámetros:
   - `pPostgresServer`: `localhost:5432`
   - `pPostgresDatabase`: `laliga_predictor`
   - `pApiBaseUrl`: `http://localhost:8000`
5. En la primera actualización, seleccionar autenticación de base de datos:
   usuario `laliga` y la contraseña definida en `.env`.
6. Pulsar **Actualizar**.

El servidor acepta el formato `host:puerto` utilizado por
`PostgreSQL.Database`. Si PostgreSQL está en otro equipo, cambia únicamente los
parámetros; no es necesario editar consultas ni visuales.

## Publicación y actualización programada

Para publicar en Power BI Service:

- Publicar el reporte desde Desktop.
- Configurar las credenciales de PostgreSQL.
- Si PostgreSQL o FastAPI no son accesibles desde la nube, instalar un gateway
  de datos local y asociar ambas fuentes.
- Programar la actualización después de ejecutar el flujo de la Fase 9.

Import es el modo recomendado por el tamaño actual: 380 fixtures, 20 equipos y
una distribución de 400 posiciones. Si se exige consulta casi en tiempo real,
las particiones PostgreSQL pueden cambiarse a DirectQuery, asumiendo mayor
dependencia del rendimiento de la base.

## Controles

- Las probabilidades 1X2 suman 1 por partido.
- Hay 380 fixtures y 20 equipos.
- La siguiente jornada contiene 10 partidos.
- Las probabilidades agregadas concilian 1 campeón, 4 Top 4, 7 Top 7 y
  3 descensos.
- PBIR fue validado sin errores ni advertencias.
- El modelo TMSL carga 10 tablas, 29 medidas y 6 relaciones.
- Los datos de pretemporada coinciden con las Fases 9 y 10.

## Reproducibilidad

Para regenerar los artefactos PBIP, las vistas previas y los controles:

```powershell
.venv\Scripts\python.exe scripts\build_phase11.py
```

Los parámetros no contienen contraseñas. Las credenciales permanecen en el
almacén seguro de Power BI Desktop o del gateway.
