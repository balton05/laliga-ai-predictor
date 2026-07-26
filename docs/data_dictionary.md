# Diccionario de datos · Fase 1

## `matches_master.csv`

Una fila representa un partido histórico de Primera o Segunda.

| Campo | Descripción |
|---|---|
| `match_id` | Identificador reproducible del partido |
| `season` | Temporada en formato `YYYY/YY` |
| `division` | `SP1` para Primera y `SP2` para Segunda |
| `date` | Fecha real del partido |
| `kickoff_time` | Hora disponible en Football-Data |
| `home_team_id`, `away_team_id` | Identificadores normalizados |
| `home_team`, `away_team` | Nombres canónicos |
| `home_goals`, `away_goals` | Goles al final del partido |
| `result` | `H`, `D` o `A` |
| `*_ht` | Resultado y goles al descanso |
| `home_*`, `away_*` | Tiros, tiros a puerta, faltas, córners y tarjetas |
| `odds_b365_*` | Cuotas 1X2 de Bet365 |
| `odds_avg_*` | Cuotas promedio del mercado |
| `odds_max_*` | Cuotas máximas del mercado |
| `source_file` | CSV histórico de origen |

## `team_match_history.csv`

Una fila representa la actuación de un equipo en un partido. Cada encuentro del
dataset maestro produce dos filas.

| Campo | Descripción |
|---|---|
| `team_id`, `opponent_id` | Equipo y rival |
| `venue` | `home` o `away` |
| `team_result` | `W`, `D` o `L` desde la perspectiva del equipo |
| `points` | 3, 1 o 0 |
| `*_for`, `*_against` | Estadísticas a favor y en contra |

Esta tabla será la base para calcular variables móviles con desplazamiento de
una observación antes de cada partido.

## `fixtures_2026_27.csv`

Una fila representa un partido del calendario oficial de LaLiga 2026/27.

| Campo | Descripción |
|---|---|
| `fixture_id` | Identificador de LaLiga con prefijo |
| `matchday` | Jornada 1–38 |
| `reference_date` | Fecha general de referencia de la jornada |
| `scheduled_date` | Fecha definitiva; todavía vacía |
| `kickoff_time` | Hora definitiva; todavía vacía |
| `home_team_id`, `away_team_id` | Identificadores normalizados |
| `*_official` | Nombre publicado en el calendario |
| `status` | Estado inicial `scheduled` |

`reference_date` no debe utilizarse todavía para calcular descanso exacto.

## `historical_promotions.csv`

Contiene 30 registros: tres ascendidos por temporada de llegada desde 2017/18
hasta 2026/27.

| Grupo | Campos |
|---|---|
| Identificación | `team_id`, `team`, `segunda_season`, `laliga_season` |
| Segunda | `segunda_position`, partidos, W-D-L, GF, GC, DG y puntos |
| Primera | `laliga_position`, partidos, W-D-L, GF, GC, DG y puntos |
| Ascenso | `promotion_type`, `has_segunda_statistics` |
| Supervivencia | `relegated_after_first_season` |

Las estadísticas completas de Segunda están disponibles para 15 registros:
las cohortes que llegaron a LaLiga entre 2022/23 y 2026/27.

## `team_name_mapping.csv`

Relaciona un `team_id` estable con el nombre canónico y todos los alias
encontrados en Football-Data y en el calendario oficial.

## Informes de calidad

- `reports/data_audit.csv`: control de filas, equipos, fechas, duplicados,
  resultados y cobertura de cuotas por archivo.
- `reports/column_coverage.csv`: número de archivos en los que aparece cada
  columna de origen.
- `reports/phase1_summary.json`: totales y rutas de salida de la ejecución.
