from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POWERBI_ROOT = PROJECT_ROOT / "powerbi" / "LaLigaAIPredictor"
MODEL_DIR = POWERBI_ROOT / "LaLigaAIPredictor.SemanticModel"
REPORT_DIR = POWERBI_ROOT / "LaLigaAIPredictor.Report"
DEFINITION_DIR = REPORT_DIR / "definition"
PAGE_DIR = DEFINITION_DIR / "pages"
THEME_NAME = "LaLigaAI_20260723.json"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def object_id(seed: str, length: int = 20) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:length]


def column(table: str, name: str) -> dict:
    return {
        "Column": {
            "Expression": {"SourceRef": {"Entity": table}},
            "Property": name,
        }
    }


def measure(table: str, name: str) -> dict:
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Entity": table}},
            "Property": name,
        }
    }


def projection(field: dict, table: str, name: str) -> dict:
    return {
        "field": field,
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": name,
    }


def text_box(seed: str, text: str, x: int, y: int, width: int, height: int,
             font_size: int = 24, color: str = "#F8FAFC") -> dict:
    name = object_id(seed)
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "report/definition/visualContainer/2.9.0/schema.json"
        ),
        "name": name,
        "position": {
            "x": x,
            "y": y,
            "z": 1000,
            "height": height,
            "width": width,
            "tabOrder": 1000,
        },
        "visual": {
            "visualType": "textbox",
            "objects": {
                "general": [
                    {
                        "properties": {
                            "paragraphs": [
                                {
                                    "textRuns": [
                                        {
                                            "value": text,
                                            "textStyle": {
                                                "fontFamily": "Segoe UI Semibold",
                                                "fontSize": f"{font_size}px",
                                                "color": color,
                                            },
                                        }
                                    ],
                                    "horizontalTextAlignment": "left",
                                }
                            ]
                        }
                    }
                ]
            },
            "visualContainerObjects": {
                "background": [
                    {
                        "properties": {
                            "show": {
                                "expr": {"Literal": {"Value": "false"}}
                            }
                        }
                    }
                ],
                "border": [
                    {
                        "properties": {
                            "show": {
                                "expr": {"Literal": {"Value": "false"}}
                            }
                        }
                    }
                ],
                "padding": [
                    {
                        "properties": {
                            side: {"expr": {"Literal": {"Value": "0D"}}}
                            for side in ["top", "bottom", "left", "right"]
                        }
                    }
                ],
            },
        },
    }


def card(seed: str, measures: list[tuple[str, str]], x: int, y: int,
         width: int, height: int = 128) -> dict:
    name = object_id(seed)
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "report/definition/visualContainer/2.9.0/schema.json"
        ),
        "name": name,
        "position": {
            "x": x,
            "y": y,
            "z": 2000,
            "height": height,
            "width": width,
            "tabOrder": 2000,
        },
        "visual": {
            "visualType": "cardVisual",
            "query": {
                "queryState": {
                    "Data": {
                        "projections": [
                            projection(measure(table, metric), table, metric)
                            for table, metric in measures
                        ]
                    }
                }
            },
            "objects": {
                "outline": [
                    {
                        "properties": {
                            "show": {
                                "expr": {"Literal": {"Value": "false"}}
                            }
                        },
                        "selector": {"id": "default"},
                    }
                ]
            },
        },
    }


def slicer(seed: str, table: str, field: str, label: str, x: int, y: int,
           width: int = 216, height: int = 80) -> dict:
    name = object_id(seed)
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "report/definition/visualContainer/2.9.0/schema.json"
        ),
        "name": name,
        "position": {
            "x": x,
            "y": y,
            "z": 3000,
            "height": height,
            "width": width,
            "tabOrder": 3000,
        },
        "visual": {
            "visualType": "slicer",
            "query": {
                "queryState": {
                    "Values": {
                        "projections": [
                            projection(column(table, field), table, field)
                        ]
                    }
                }
            },
            "objects": {
                "data": [
                    {
                        "properties": {
                            "mode": {
                                "expr": {
                                    "Literal": {"Value": "'Dropdown'"}
                                }
                            }
                        }
                    }
                ],
                "header": [
                    {
                        "properties": {
                            "show": {
                                "expr": {"Literal": {"Value": "true"}}
                            },
                            "text": {
                                "expr": {
                                    "Literal": {"Value": f"'{label}'"}
                                }
                            },
                        }
                    }
                ],
            },
            "visualContainerObjects": {
                "padding": [
                    {
                        "properties": {
                            side: {"expr": {"Literal": {"Value": "8D"}}}
                            for side in ["top", "bottom", "left", "right"]
                        }
                    }
                ]
            },
        },
    }


def table_visual(seed: str, fields: list[tuple[str, str, str]], x: int,
                 y: int, width: int, height: int) -> dict:
    name = object_id(seed)
    projections = []
    for kind, table, field in fields:
        field_expr = measure(table, field) if kind == "measure" else column(
            table, field
        )
        projections.append(projection(field_expr, table, field))
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "report/definition/visualContainer/2.9.0/schema.json"
        ),
        "name": name,
        "position": {
            "x": x,
            "y": y,
            "z": 4000,
            "height": height,
            "width": width,
            "tabOrder": 4000,
        },
        "visual": {
            "visualType": "tableEx",
            "query": {"queryState": {"Values": {"projections": projections}}},
            "objects": {
                "columnHeaders": [
                    {
                        "properties": {
                            "columnAdjustment": {
                                "expr": {
                                    "Literal": {"Value": "'growToFit'"}
                                }
                            },
                            "autoSizeColumnWidth": {
                                "expr": {"Literal": {"Value": "true"}}
                            },
                        }
                    }
                ]
            },
        },
    }


def chart(seed: str, visual_type: str, category: tuple[str, str],
          values: list[tuple[str, str]], x: int, y: int, width: int,
          height: int) -> dict:
    name = object_id(seed)
    category_table, category_field = category
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/"
            "report/definition/visualContainer/2.9.0/schema.json"
        ),
        "name": name,
        "position": {
            "x": x,
            "y": y,
            "z": 5000,
            "height": height,
            "width": width,
            "tabOrder": 5000,
        },
        "visual": {
            "visualType": visual_type,
            "query": {
                "queryState": {
                    "Category": {
                        "projections": [
                            {
                                **projection(
                                    column(category_table, category_field),
                                    category_table,
                                    category_field,
                                ),
                                "active": True,
                            }
                        ]
                    },
                    "Y": {
                        "projections": [
                            projection(measure(table, metric), table, metric)
                            for table, metric in values
                        ]
                    },
                }
            },
        },
    }


def page(seed: str, display_name: str, visuals: list[dict]) -> str:
    page_name = object_id(f"page:{seed}")
    write_json(
        PAGE_DIR / page_name / "page.json",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/page/2.1.0/schema.json"
            ),
            "name": page_name,
            "displayName": display_name,
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
        },
    )
    for visual in visuals:
        write_json(
            PAGE_DIR
            / page_name
            / "visuals"
            / visual["name"]
            / "visual.json",
            visual,
        )
    return page_name


def model_column(name: str, source: str, dtype: str = "string",
                 format_string: str | None = None) -> dict:
    payload = {
        "name": name,
        "dataType": dtype,
        "sourceColumn": source,
        "summarizeBy": "none",
    }
    if format_string:
        payload["formatString"] = format_string
    return payload


def model_measure(name: str, expression: str,
                  format_string: str | None = None,
                  folder: str | None = None) -> dict:
    payload = {"name": name, "expression": expression}
    if format_string:
        payload["formatString"] = format_string
    if folder:
        payload["displayFolder"] = folder
    return payload


def imported_table(name: str, view: str, columns: list[dict],
                   measures: list[dict] | None = None) -> dict:
    payload = {
        "name": name,
        "columns": columns,
        "partitions": [
            {
                "name": name,
                "mode": "import",
                "source": {
                    "type": "m",
                    "expression": [
                        "let",
                        "    Source = PostgreSQL.Database(",
                        "        pPostgresServer,",
                        "        pPostgresDatabase,",
                        f'        [Query="SELECT * FROM {view}"]',
                        "    )",
                        "in",
                        "    Source",
                    ],
                },
            }
        ],
    }
    if measures:
        payload["measures"] = measures
    return payload


def build_model() -> None:
    percentage = "0.0%"
    decimal = "0.0"
    integer = "0"
    tables = [
        imported_table(
            "Dim Equipo",
            "bi_dim_team",
            [
                model_column("Equipo ID", "team_id"),
                model_column("Equipo", "team"),
                model_column("Recién ascendido", "is_promoted", "boolean"),
            ],
        ),
        imported_table(
            "Dim Jornada",
            "bi_dim_matchday",
            [
                model_column("Jornada", "matchday", "int64", integer),
                model_column("Etiqueta jornada", "matchday_label"),
                model_column("Tramo temporada", "season_stage"),
            ],
        ),
        imported_table(
            "Dim Posición",
            "bi_dim_position",
            [
                model_column("Posición", "position", "int64", integer),
                model_column("Zona", "position_zone"),
            ],
        ),
        imported_table(
            "Partidos",
            "bi_fact_matches",
            [
                model_column("Fixture ID", "fixture_id"),
                model_column("Temporada", "season"),
                model_column("Jornada", "matchday", "int64", integer),
                model_column("Fecha referencia", "reference_date", "dateTime",
                             "Short Date"),
                model_column("Fecha programada", "scheduled_date", "dateTime",
                             "General Date"),
                model_column("Local ID", "home_team_id"),
                model_column("Local", "home_team"),
                model_column("Visitante ID", "away_team_id"),
                model_column("Visitante", "away_team"),
                model_column("Partido", "match_label"),
                model_column("Estado", "status"),
                model_column("Jugado", "is_played", "boolean"),
                model_column("Goles local", "home_goals", "int64", integer),
                model_column("Goles visitante", "away_goals", "int64", integer),
                model_column("Resultado real", "actual_result_label"),
                model_column("Modelo", "model"),
                model_column("Probabilidad local", "probability_home", "double",
                             percentage),
                model_column("Probabilidad empate", "probability_draw", "double",
                             percentage),
                model_column("Probabilidad visitante", "probability_away",
                             "double", percentage),
                model_column("Pronóstico", "predicted_result_label"),
                model_column("Confianza", "confidence"),
                model_column("Goles esperados local", "expected_home_goals",
                             "double", decimal),
                model_column("Goles esperados visitante",
                             "expected_away_goals", "double", decimal),
                model_column("Marcador previsto", "predicted_score"),
                model_column("Cuotas disponibles", "market_odds_available",
                             "boolean"),
                model_column("Predicción correcta", "prediction_correct",
                             "boolean"),
                model_column("Update ID", "update_id"),
            ],
            [
                model_measure(
                    "Total partidos",
                    "COUNTROWS('Partidos')",
                    integer,
                    "Operación",
                ),
                model_measure(
                    "Partidos jugados",
                    "CALCULATE(COUNTROWS('Partidos'), 'Partidos'[Jugado] = TRUE())",
                    integer,
                    "Operación",
                ),
                model_measure(
                    "Partidos pendientes",
                    "[Total partidos] - [Partidos jugados]",
                    integer,
                    "Operación",
                ),
                model_measure(
                    "Próxima jornada",
                    "MINX(FILTER('Partidos', 'Partidos'[Jugado] = FALSE()), "
                    "'Partidos'[Jornada])",
                    integer,
                    "Operación",
                ),
                model_measure(
                    "Precisión del pronóstico",
                    "DIVIDE(CALCULATE(COUNTROWS('Partidos'), "
                    "'Partidos'[Predicción correcta] = TRUE()), "
                    "[Partidos jugados])",
                    percentage,
                    "Calidad",
                ),
                model_measure(
                    "Promedio de goles",
                    "DIVIDE(SUM('Partidos'[Goles local]) + "
                    "SUM('Partidos'[Goles visitante]), [Partidos jugados])",
                    decimal,
                    "Resultados",
                ),
                model_measure(
                    "Probabilidad Local",
                    "AVERAGE('Partidos'[Probabilidad local])",
                    percentage,
                    "Predicción",
                ),
                model_measure(
                    "Probabilidad Empate",
                    "AVERAGE('Partidos'[Probabilidad empate])",
                    percentage,
                    "Predicción",
                ),
                model_measure(
                    "Probabilidad Visitante",
                    "AVERAGE('Partidos'[Probabilidad visitante])",
                    percentage,
                    "Predicción",
                ),
                model_measure(
                    "Victorias locales esperadas",
                    "SUM('Partidos'[Probabilidad local])",
                    decimal,
                    "Predicción",
                ),
                model_measure(
                    "Empates esperados",
                    "SUM('Partidos'[Probabilidad empate])",
                    decimal,
                    "Predicción",
                ),
                model_measure(
                    "Victorias visitantes esperadas",
                    "SUM('Partidos'[Probabilidad visitante])",
                    decimal,
                    "Predicción",
                ),
                model_measure(
                    "Partidos con mercado",
                    "CALCULATE(COUNTROWS('Partidos'), "
                    "'Partidos'[Cuotas disponibles] = TRUE())",
                    integer,
                    "Mercado",
                ),
            ],
        ),
        imported_table(
            "Equipo-Partido",
            "bi_fact_team_matches",
            [
                model_column("Fixture ID", "fixture_id"),
                model_column("Temporada", "season"),
                model_column("Jornada", "matchday", "int64", integer),
                model_column("Fecha", "reference_date", "dateTime", "Short Date"),
                model_column("Equipo ID", "team_id"),
                model_column("Equipo", "team"),
                model_column("Rival ID", "opponent_id"),
                model_column("Rival", "opponent"),
                model_column("Condición", "venue"),
                model_column("Estado", "status"),
                model_column("Jugado", "is_played", "boolean"),
                model_column("Goles a favor", "goals_for", "int64", integer),
                model_column("Goles en contra", "goals_against", "int64", integer),
                model_column("Resultado", "team_result"),
                model_column("Probabilidad victoria", "win_probability",
                             "double", percentage),
                model_column("Probabilidad empate", "draw_probability",
                             "double", percentage),
                model_column("Probabilidad derrota", "loss_probability",
                             "double", percentage),
                model_column("xG a favor", "expected_goals_for", "double",
                             decimal),
                model_column("xG en contra", "expected_goals_against", "double",
                             decimal),
                model_column("Update ID", "update_id"),
            ],
        ),
        imported_table(
            "Clasificación",
            "bi_current_standings",
            [
                model_column("Equipo ID", "team_id"),
                model_column("Equipo", "team"),
                model_column("PJ", "played", "int64", integer),
                model_column("PG", "wins", "int64", integer),
                model_column("PE", "draws", "int64", integer),
                model_column("PP", "losses", "int64", integer),
                model_column("GF", "goals_for", "int64", integer),
                model_column("GC", "goals_against", "int64", integer),
                model_column("DG", "goal_difference", "int64", integer),
                model_column("Puntos", "points", "int64", integer),
                model_column("Posición actual", "position", "int64", integer),
                model_column("PPG", "ppg", "double", decimal),
                model_column("Update ID", "update_id"),
            ],
            [
                model_measure("Puntos actuales", "MAX('Clasificación'[Puntos])",
                              integer, "Equipo"),
                model_measure(
                    "Posición actual equipo",
                    "MIN('Clasificación'[Posición actual])",
                    integer,
                    "Equipo",
                ),
            ],
        ),
        imported_table(
            "Simulación",
            "bi_simulation_summary",
            [
                model_column("Equipo ID", "team_id"),
                model_column("Equipo", "team"),
                model_column("Simulaciones", "simulations", "int64", "#,0"),
                model_column("Puntos esperados", "expected_points", "double",
                             decimal),
                model_column("Mediana puntos", "median_points", "double",
                             decimal),
                model_column("Puntos P05", "points_p05", "double", decimal),
                model_column("Puntos P95", "points_p95", "double", decimal),
                model_column("Posición esperada", "expected_position", "double",
                             decimal),
                model_column("Mediana posición", "median_position", "double",
                             decimal),
                model_column("Probabilidad campeón", "champion_probability",
                             "double", percentage),
                model_column("Probabilidad Top 4", "top4_probability", "double",
                             percentage),
                model_column("Probabilidad Top 6", "top6_probability", "double",
                             percentage),
                model_column("Probabilidad Europa", "europe_top7_probability",
                             "double", percentage),
                model_column("Probabilidad descenso", "relegation_probability",
                             "double", percentage),
                model_column("Probabilidad último", "last_place_probability",
                             "double", percentage),
                model_column("Update ID", "update_id"),
            ],
            [
                model_measure("Número de simulaciones",
                              "MAX('Simulación'[Simulaciones])", "#,0",
                              "Operación"),
                model_measure("Puntos esperados equipo",
                              "MAX('Simulación'[Puntos esperados])", decimal,
                              "Equipo"),
                model_measure("Posición esperada equipo",
                              "MIN('Simulación'[Posición esperada])", decimal,
                              "Equipo"),
                model_measure("P Campeón",
                              "MAX('Simulación'[Probabilidad campeón])",
                              percentage, "Zonas"),
                model_measure("P Top 4",
                              "MAX('Simulación'[Probabilidad Top 4])",
                              percentage, "Zonas"),
                model_measure("P Europa",
                              "MAX('Simulación'[Probabilidad Europa])",
                              percentage, "Zonas"),
                model_measure("P Descenso",
                              "MAX('Simulación'[Probabilidad descenso])",
                              percentage, "Zonas"),
                model_measure(
                    "Favorito al título",
                    "CONCATENATEX(TOPN(1, ALL('Simulación'), "
                    "'Simulación'[Probabilidad campeón], DESC, "
                    "'Simulación'[Equipo], ASC), 'Simulación'[Equipo], \"\")",
                    None,
                    "Resumen",
                ),
                model_measure(
                    "Mayor riesgo de descenso",
                    "CONCATENATEX(TOPN(1, ALL('Simulación'), "
                    "'Simulación'[Probabilidad descenso], DESC, "
                    "'Simulación'[Equipo], ASC), 'Simulación'[Equipo], \"\")",
                    None,
                    "Resumen",
                ),
            ],
        ),
        imported_table(
            "Probabilidad Posición",
            "bi_position_probabilities",
            [
                model_column("Equipo ID", "team_id"),
                model_column("Posición", "position", "int64", integer),
                model_column("Probabilidad", "probability", "double",
                             percentage),
                model_column("Update ID", "update_id"),
            ],
        ),
        imported_table(
            "Actualizaciones",
            "bi_update_status",
            [
                model_column("Update ID", "update_id"),
                model_column("Creado UTC", "created_at_utc", "dateTime",
                             "General Date"),
                model_column("Fecha snapshot", "snapshot_date", "dateTime",
                             "Short Date"),
                model_column("Partidos completados", "completed_matches",
                             "int64", integer),
                model_column("Jornadas completadas", "completed_matchdays",
                             "int64", integer),
                model_column("Partidos restantes", "remaining_matches",
                             "int64", integer),
                model_column("Próxima jornada", "next_matchday", "int64",
                             integer),
                model_column("Predicciones mercado", "market_predictions",
                             "int64", integer),
                model_column("Predicciones deportivas", "sports_predictions",
                             "int64", integer),
                model_column("Simulaciones", "simulations", "int64", "#,0"),
                model_column("Semilla", "seed", "int64", integer),
                model_column("Calidad superada", "quality_passed", "boolean"),
                model_column("Modo pipeline", "pipeline_mode"),
            ],
            [
                model_measure(
                    "Última actualización",
                    "CONCATENATEX(TOPN(1, 'Actualizaciones', "
                    "'Actualizaciones'[Creado UTC], DESC), "
                    "'Actualizaciones'[Update ID], \"\")",
                    None,
                    "Auditoría",
                ),
                model_measure(
                    "Calidad actual",
                    "IF(MAX('Actualizaciones'[Calidad superada]), "
                    "\"Correcta\", \"Revisar\")",
                    None,
                    "Auditoría",
                ),
                model_measure(
                    "Jornadas cerradas",
                    "MAX('Actualizaciones'[Jornadas completadas])",
                    integer,
                    "Auditoría",
                ),
                model_measure(
                    "Predicciones con mercado",
                    "MAX('Actualizaciones'[Predicciones mercado])",
                    integer,
                    "Auditoría",
                ),
            ],
        ),
        {
            "name": "Estado API",
            "columns": [
                model_column("Estado", "status"),
                model_column("Base de datos", "database"),
                model_column("Temporada", "season"),
                model_column("Update ID", "latest_update_id"),
                model_column("Fixtures", "fixtures", "int64", integer),
                model_column("Predicciones", "predictions", "int64", integer),
                model_column("Partidos completados", "completed_matches",
                             "int64", integer),
                model_column("Simulaciones", "simulations", "int64", "#,0"),
            ],
            "measures": [
                model_measure(
                    "Estado de la API",
                    "SELECTEDVALUE('Estado API'[Estado], \"Sin conexión\")",
                    None,
                    "Sistema",
                )
            ],
            "partitions": [
                {
                    "name": "Estado API",
                    "mode": "import",
                    "source": {
                        "type": "m",
                        "expression": [
                            "let",
                            "    Response = Json.Document(",
                            "        Web.Contents(pApiBaseUrl, "
                            '[RelativePath="health"])',
                            "    ),",
                            "    Source = Table.FromRecords({Response})",
                            "in",
                            "    Source",
                        ],
                    },
                }
            ],
        },
    ]
    relationships = [
        {
            "name": object_id("rel:jornada-partidos", 32),
            "fromTable": "Partidos",
            "fromColumn": "Jornada",
            "toTable": "Dim Jornada",
            "toColumn": "Jornada",
        },
        {
            "name": object_id("rel:equipo-equipo-partido", 32),
            "fromTable": "Equipo-Partido",
            "fromColumn": "Equipo ID",
            "toTable": "Dim Equipo",
            "toColumn": "Equipo ID",
        },
        {
            "name": object_id("rel:equipo-clasificacion", 32),
            "fromTable": "Clasificación",
            "fromColumn": "Equipo ID",
            "toTable": "Dim Equipo",
            "toColumn": "Equipo ID",
        },
        {
            "name": object_id("rel:equipo-simulacion", 32),
            "fromTable": "Simulación",
            "fromColumn": "Equipo ID",
            "toTable": "Dim Equipo",
            "toColumn": "Equipo ID",
        },
        {
            "name": object_id("rel:equipo-posicion", 32),
            "fromTable": "Probabilidad Posición",
            "fromColumn": "Equipo ID",
            "toTable": "Dim Equipo",
            "toColumn": "Equipo ID",
        },
        {
            "name": object_id("rel:posicion-probabilidad", 32),
            "fromTable": "Probabilidad Posición",
            "fromColumn": "Posición",
            "toTable": "Dim Posición",
            "toColumn": "Posición",
        },
    ]
    model = {
        "name": "LaLigaAIPredictor",
        "compatibilityLevel": 1600,
        "model": {
            "culture": "es-ES",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "es-ES",
            "dataAccessOptions": {
                "legacyRedirects": True,
                "returnErrorValuesAsNull": True,
            },
            "expressions": [
                {
                    "name": "pPostgresServer",
                    "kind": "m",
                    "expression": '"localhost:5432"',
                },
                {
                    "name": "pPostgresDatabase",
                    "kind": "m",
                    "expression": '"laliga_predictor"',
                },
                {
                    "name": "pApiBaseUrl",
                    "kind": "m",
                    "expression": '"http://localhost:8000"',
                },
            ],
            "tables": tables,
            "relationships": relationships,
            "annotations": [
                {
                    "name": "PBI_QueryOrder",
                    "value": json.dumps([table["name"] for table in tables]),
                }
            ],
        },
    }
    write_json(MODEL_DIR / "model.bim", model)
    write_json(
        MODEL_DIR / "definition.pbism",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "semanticModel/definitionProperties/1.0.0/schema.json"
            ),
            "version": "4.2",
            "settings": {"qnaEnabled": True},
        },
    )
    write_json(
        MODEL_DIR / ".platform",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/"
                "gitIntegration/platformProperties/2.0.0/schema.json"
            ),
            "metadata": {
                "type": "SemanticModel",
                "displayName": "LaLiga AI Predictor",
            },
            "config": {
                "version": "2.0",
                "logicalId": "d3822c11-8588-4f18-b8fd-32e54879c0af",
            },
        },
    )


def build_report() -> dict:
    pages: list[str] = []
    pages.append(
        page(
            "resumen",
            "Resumen",
            [
                text_box("resumen-title", "LaLiga AI Predictor · 2026/27",
                         24, 16, 850, 44),
                text_box("resumen-sub", "Panorama de pretemporada y estado del modelo",
                         24, 54, 850, 24, 13, "#94A3B8"),
                card(
                    "resumen-kpis",
                    [
                        ("Partidos", "Partidos jugados"),
                        ("Partidos", "Partidos pendientes"),
                        ("Partidos", "Próxima jornada"),
                        ("Simulación", "Número de simulaciones"),
                    ],
                    24, 92, 1232, 132,
                ),
                text_box("resumen-champ-label", "Probabilidad de campeón",
                         24, 236, 590, 30, 17),
                chart(
                    "resumen-champion",
                    "clusteredBarChart",
                    ("Simulación", "Equipo"),
                    [("Simulación", "P Campeón")],
                    24, 270, 596, 418,
                ),
                text_box("resumen-rel-label", "Riesgo de descenso",
                         648, 236, 590, 30, 17),
                chart(
                    "resumen-relegation",
                    "clusteredBarChart",
                    ("Simulación", "Equipo"),
                    [("Simulación", "P Descenso")],
                    648, 270, 608, 418,
                ),
            ],
        )
    )
    pages.append(
        page(
            "jornada",
            "Próxima jornada",
            [
                text_box("jornada-title", "Pronósticos por jornada",
                         24, 16, 800, 44),
                slicer("jornada-slicer", "Dim Jornada", "Jornada",
                       "Jornada", 1032, 8, 224, 80),
                card(
                    "jornada-kpis",
                    [
                        ("Partidos", "Victorias locales esperadas"),
                        ("Partidos", "Empates esperados"),
                        ("Partidos", "Victorias visitantes esperadas"),
                        ("Partidos", "Partidos con mercado"),
                    ],
                    24, 88, 1232, 132,
                ),
                chart(
                    "jornada-chart",
                    "clusteredColumnChart",
                    ("Partidos", "Partido"),
                    [
                        ("Partidos", "Probabilidad Local"),
                        ("Partidos", "Probabilidad Empate"),
                        ("Partidos", "Probabilidad Visitante"),
                    ],
                    24, 236, 600, 452,
                ),
                table_visual(
                    "jornada-table",
                    [
                        ("column", "Partidos", "Partido"),
                        ("column", "Partidos", "Pronóstico"),
                        ("column", "Partidos", "Marcador previsto"),
                        ("column", "Partidos", "Confianza"),
                        ("column", "Partidos", "Probabilidad local"),
                        ("column", "Partidos", "Probabilidad empate"),
                        ("column", "Partidos", "Probabilidad visitante"),
                    ],
                    648, 236, 608, 452,
                ),
            ],
        )
    )
    pages.append(
        page(
            "simulacion",
            "Simulación",
            [
                text_box("sim-title", "Simulación Monte Carlo",
                         24, 16, 800, 44),
                card(
                    "sim-kpis",
                    [
                        ("Simulación", "Favorito al título"),
                        ("Simulación", "Mayor riesgo de descenso"),
                        ("Simulación", "Número de simulaciones"),
                    ],
                    24, 80, 1232, 132,
                ),
                chart(
                    "sim-zones",
                    "clusteredBarChart",
                    ("Simulación", "Equipo"),
                    [
                        ("Simulación", "P Campeón"),
                        ("Simulación", "P Top 4"),
                        ("Simulación", "P Europa"),
                        ("Simulación", "P Descenso"),
                    ],
                    24, 228, 760, 460,
                ),
                table_visual(
                    "sim-table",
                    [
                        ("column", "Simulación", "Equipo"),
                        ("column", "Simulación", "Puntos esperados"),
                        ("column", "Simulación", "Puntos P05"),
                        ("column", "Simulación", "Puntos P95"),
                        ("column", "Simulación", "Posición esperada"),
                        ("column", "Simulación", "Probabilidad campeón"),
                        ("column", "Simulación", "Probabilidad descenso"),
                    ],
                    808, 228, 448, 460,
                ),
            ],
        )
    )
    pages.append(
        page(
            "clasificacion",
            "Clasificación",
            [
                text_box("table-title", "Clasificación actual y puntos esperados",
                         24, 16, 900, 44),
                table_visual(
                    "standing-table",
                    [
                        ("column", "Clasificación", "Posición actual"),
                        ("column", "Clasificación", "Equipo"),
                        ("column", "Clasificación", "PJ"),
                        ("column", "Clasificación", "PG"),
                        ("column", "Clasificación", "PE"),
                        ("column", "Clasificación", "PP"),
                        ("column", "Clasificación", "GF"),
                        ("column", "Clasificación", "GC"),
                        ("column", "Clasificación", "DG"),
                        ("column", "Clasificación", "Puntos"),
                    ],
                    24, 84, 610, 604,
                ),
                chart(
                    "points-chart",
                    "clusteredBarChart",
                    ("Simulación", "Equipo"),
                    [("Simulación", "Puntos esperados equipo")],
                    658, 84, 598, 604,
                ),
            ],
        )
    )
    pages.append(
        page(
            "equipo",
            "Explorador de equipos",
            [
                text_box("team-title", "Explorador de equipos",
                         24, 16, 800, 44),
                slicer("team-slicer", "Dim Equipo", "Equipo",
                       "Equipo", 976, 8, 280, 80),
                card(
                    "team-kpis",
                    [
                        ("Clasificación", "Puntos actuales"),
                        ("Simulación", "Puntos esperados equipo"),
                        ("Simulación", "Posición esperada equipo"),
                        ("Simulación", "P Descenso"),
                    ],
                    24, 88, 1232, 132,
                ),
                table_visual(
                    "team-matches",
                    [
                        ("column", "Equipo-Partido", "Jornada"),
                        ("column", "Equipo-Partido", "Condición"),
                        ("column", "Equipo-Partido", "Rival"),
                        ("column", "Equipo-Partido", "Estado"),
                        ("column", "Equipo-Partido", "Probabilidad victoria"),
                        ("column", "Equipo-Partido", "Probabilidad empate"),
                        ("column", "Equipo-Partido", "Probabilidad derrota"),
                        ("column", "Equipo-Partido", "xG a favor"),
                        ("column", "Equipo-Partido", "xG en contra"),
                    ],
                    24, 236, 1232, 452,
                ),
            ],
        )
    )
    pages.append(
        page(
            "calidad",
            "Calidad y actualización",
            [
                text_box("quality-title", "Calidad, API y trazabilidad",
                         24, 16, 900, 44),
                card(
                    "quality-kpis",
                    [
                        ("Estado API", "Estado de la API"),
                        ("Actualizaciones", "Última actualización"),
                        ("Actualizaciones", "Calidad actual"),
                        ("Actualizaciones", "Predicciones con mercado"),
                    ],
                    24, 88, 1232, 132,
                ),
                table_visual(
                    "updates-table",
                    [
                        ("column", "Actualizaciones", "Update ID"),
                        ("column", "Actualizaciones", "Creado UTC"),
                        ("column", "Actualizaciones", "Partidos completados"),
                        ("column", "Actualizaciones", "Jornadas completadas"),
                        ("column", "Actualizaciones", "Partidos restantes"),
                        ("column", "Actualizaciones", "Predicciones mercado"),
                        ("column", "Actualizaciones", "Calidad superada"),
                        ("column", "Actualizaciones", "Modo pipeline"),
                    ],
                    24, 236, 1232, 452,
                ),
            ],
        )
    )
    write_json(
        DEFINITION_DIR / "version.json",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/versionMetadata/1.0.0/schema.json"
            ),
            "version": "2.0.0",
        },
    )
    write_json(
        PAGE_DIR / "pages.json",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.0.0/schema.json"
            ),
            "pageOrder": pages,
            "activePageName": pages[0],
        },
    )
    write_json(
        DEFINITION_DIR / "report.json",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/report/3.1.0/schema.json"
            ),
            "themeCollection": {
                "customTheme": {
                    "name": THEME_NAME,
                    "reportVersionAtImport": {
                        "visual": "2.9.0",
                        "report": "3.1.0",
                        "page": "2.1.0",
                    },
                    "type": "RegisteredResources",
                }
            },
            "resourcePackages": [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [
                        {
                            "name": THEME_NAME,
                            "path": THEME_NAME,
                            "type": "CustomTheme",
                        }
                    ],
                }
            ],
            "settings": {
                "useStylableVisualContainerHeader": True,
                "defaultFilterActionIsDataFilter": True,
                "defaultDrillFilterOtherVisuals": True,
                "allowChangeFilterTypes": True,
                "allowInlineExploration": True,
                "useEnhancedTooltips": True,
            },
        },
    )
    write_json(
        REPORT_DIR / "definition.pbir",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definitionProperties/2.0.0/schema.json"
            ),
            "version": "4.0",
            "datasetReference": {
                "byPath": {"path": "../LaLigaAIPredictor.SemanticModel"}
            },
        },
    )
    write_json(
        REPORT_DIR / ".platform",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/"
                "gitIntegration/platformProperties/2.0.0/schema.json"
            ),
            "metadata": {
                "type": "Report",
                "displayName": "LaLiga AI Predictor",
            },
            "config": {
                "version": "2.0",
                "logicalId": "525d2bd0-3e92-47a8-b499-7859f312233d",
            },
        },
    )
    write_json(
        POWERBI_ROOT / "LaLigaAIPredictor.pbip",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/pbip/"
                "pbipProperties/1.0.0/schema.json"
            ),
            "version": "1.0",
            "artifacts": [
                {
                    "report": {
                        "path": "LaLigaAIPredictor.Report"
                    }
                }
            ],
            "settings": {"enableAutoRecovery": True},
        },
    )
    (POWERBI_ROOT / ".gitignore").write_text(
        "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n",
        encoding="utf-8",
    )
    return {"pages": len(pages)}


def build_theme() -> None:
    theme = {
        "name": THEME_NAME,
        "dataColors": [
            "#38BDF8",
            "#FBBF24",
            "#F97316",
            "#22C55E",
            "#A78BFA",
            "#F43F5E",
            "#14B8A6",
            "#E879F9",
        ],
        "background": "#0F172A",
        "foreground": "#F8FAFC",
        "tableAccent": "#38BDF8",
        "good": "#22C55E",
        "neutral": "#FBBF24",
        "bad": "#F43F5E",
        "textClasses": {
            "title": {
                "fontFace": "Segoe UI Semibold",
                "fontSize": 16,
                "color": "#F8FAFC",
            },
            "callout": {
                "fontFace": "Segoe UI Semibold",
                "fontSize": 24,
                "color": "#F8FAFC",
            },
            "label": {
                "fontFace": "Segoe UI",
                "fontSize": 10,
                "color": "#CBD5E1",
            },
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [
                        {
                            "show": True,
                            "color": {"solid": {"color": "#172033"}},
                            "transparency": 0,
                        }
                    ],
                    "border": [
                        {
                            "show": True,
                            "color": {"solid": {"color": "#334155"}},
                            "radius": 8,
                        }
                    ],
                    "visualHeader": [{"show": False}],
                    "padding": [
                        {"top": 8, "bottom": 8, "left": 8, "right": 8}
                    ],
                }
            },
            "tableEx": {
                "*": {
                    "columnHeaders": [
                        {
                            "autoSizeColumnWidth": True,
                            "columnAdjustment": "growToFit",
                            "backColor": {"solid": {"color": "#1E293B"}},
                            "fontColor": {"solid": {"color": "#F8FAFC"}},
                        }
                    ],
                    "values": [
                        {
                            "backColorPrimary": {
                                "solid": {"color": "#172033"}
                            },
                            "backColorSecondary": {
                                "solid": {"color": "#1E293B"}
                            },
                            "fontColorPrimary": {
                                "solid": {"color": "#E2E8F0"}
                            },
                            "fontColorSecondary": {
                                "solid": {"color": "#E2E8F0"}
                            },
                        }
                    ],
                }
            },
        },
    }
    write_json(
        REPORT_DIR / "StaticResources" / "RegisteredResources" / THEME_NAME,
        theme,
    )
    write_json(PROJECT_ROOT / "powerbi" / "theme" / "LaLigaAI.json", theme)


def build_preview_data() -> dict:
    predictions = pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "current_predictions_2026_27.csv"
    )
    simulation = pd.read_csv(
        PROJECT_ROOT / "reports" / "dynamic_season_simulation_summary.csv"
    )
    positions = pd.read_csv(
        PROJECT_ROOT / "reports" / "dynamic_position_distribution.csv"
    )
    next_matches = predictions.loc[
        predictions["matchday"].eq(predictions["matchday"].min()),
        [
            "matchday",
            "home_team",
            "away_team",
            "probability_home",
            "probability_draw",
            "probability_away",
            "predicted_score",
            "confidence",
        ],
    ].copy()
    out = PROJECT_ROOT / "powerbi" / "preview_data"
    out.mkdir(parents=True, exist_ok=True)
    next_matches.to_csv(
        out / "next_matchday.csv", index=False, encoding="utf-8-sig"
    )
    simulation.to_csv(
        out / "simulation_summary.csv", index=False, encoding="utf-8-sig"
    )
    positions.to_csv(
        out / "position_distribution.csv", index=False, encoding="utf-8-sig"
    )
    return {
        "fixtures": len(predictions),
        "next_matchday_matches": len(next_matches),
        "teams": len(simulation),
        "champion_sum": float(simulation["champion_probability"].sum()),
        "top4_sum": float(simulation["top4_probability"].sum()),
        "top7_sum": float(simulation["europe_top7_probability"].sum()),
        "relegation_sum": float(simulation["relegation_probability"].sum()),
    }


def run_phase11() -> dict:
    build_model()
    build_theme()
    report_info = build_report()
    data_info = build_preview_data()
    views_sql = (
        PROJECT_ROOT / "database" / "002_powerbi_views.sql"
    ).read_text(encoding="utf-8")
    analytical_view_count = views_sql.count("CREATE OR REPLACE VIEW ")
    checks = [
        ("fixtures_380", data_info["fixtures"] == 380, data_info["fixtures"]),
        ("next_matchday_10", data_info["next_matchday_matches"] == 10,
         data_info["next_matchday_matches"]),
        ("teams_20", data_info["teams"] == 20, data_info["teams"]),
        ("champion_sum_1", np.isclose(data_info["champion_sum"], 1.0),
         data_info["champion_sum"]),
        ("top4_sum_4", np.isclose(data_info["top4_sum"], 4.0),
         data_info["top4_sum"]),
        ("top7_sum_7", np.isclose(data_info["top7_sum"], 7.0),
         data_info["top7_sum"]),
        ("relegation_sum_3", np.isclose(data_info["relegation_sum"], 3.0),
         data_info["relegation_sum"]),
        ("report_pages_6", report_info["pages"] == 6, report_info["pages"]),
        (
            "powerbi_views_9",
            analytical_view_count == 9,
            analytical_view_count,
        ),
        (
            "pbip_entrypoint_present",
            (POWERBI_ROOT / "LaLigaAIPredictor.pbip").exists(),
            True,
        ),
        (
            "semantic_model_present",
            (MODEL_DIR / "model.bim").exists(),
            True,
        ),
        (
            "theme_present",
            (REPORT_DIR / "StaticResources" / "RegisteredResources"
             / THEME_NAME).exists(),
            True,
        ),
    ]
    quality = pd.DataFrame(
        [
            {"check": name, "passed": bool(passed), "value": value}
            for name, passed, value in checks
        ]
    )
    if not quality["passed"].all():
        failed = quality.loc[~quality["passed"], "check"].tolist()
        raise AssertionError(f"Phase 11 checks failed: {failed}")
    reports = PROJECT_ROOT / "reports"
    quality.to_csv(
        reports / "phase11_quality_checks.csv",
        index=False,
        encoding="utf-8-sig",
    )
    summary = {
        "phase": 11,
        "bi_tool": "Power BI Desktop",
        "project_format": "PBIP + PBIR + TMSL",
        "storage_mode": "Import",
        "production_source": "PostgreSQL analytical views",
        "api_source": "FastAPI /health",
        "semantic_tables": 10,
        "relationships": 6,
        "measures": 29,
        "report_pages": report_info["pages"],
        "fixtures": data_info["fixtures"],
        "teams": data_info["teams"],
        "quality_checks": len(quality),
        "quality_passed": True,
    }
    write_json(reports / "phase11_summary.json", summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(run_phase11(), ensure_ascii=False, indent=2))
