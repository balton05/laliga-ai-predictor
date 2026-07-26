from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import (
    FIXTURE_SOURCE,
    HISTORICAL_SOURCES,
    NUMERIC_MASTER_COLUMNS,
    PROCESSED_DIR,
    REPORTS_DIR,
    SOURCE_TO_MASTER,
    TEAM_ALIASES,
    TEAM_NAMES,
)


CORE_COLUMNS = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
ODDS_COLUMNS = ["B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA"]


def season_sort_key(season: str) -> int:
    return int(season.split("/")[0])


def read_football_data(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="cp1252")


def parse_football_dates(values: pd.Series, errors: str = "raise") -> pd.Series:
    text = values.astype("string").str.strip()
    parsed = pd.to_datetime(text, format="%d/%m/%Y", errors="coerce")
    missing = parsed.isna() & text.notna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            text.loc[missing],
            format="%d/%m/%y",
            errors="coerce",
        )
    if errors == "raise" and parsed.isna().any():
        invalid = text.loc[parsed.isna()].dropna().unique().tolist()
        raise ValueError(f"Invalid Football-Data dates: {invalid[:5]}")
    return parsed


def team_ids(values: pd.Series, source: str) -> pd.Series:
    cleaned = values.astype("string").str.strip()
    mapped = cleaned.map(TEAM_ALIASES)
    missing = sorted(cleaned[mapped.isna()].dropna().unique().tolist())
    if missing:
        raise ValueError(f"Unknown team names in {source}: {missing}")
    return mapped


def expected_result(df: pd.DataFrame) -> pd.Series:
    result = pd.Series("D", index=df.index, dtype="string")
    result.loc[df["FTHG"] > df["FTAG"]] = "H"
    result.loc[df["FTHG"] < df["FTAG"]] = "A"
    return result


def audit_sources() -> tuple[pd.DataFrame, pd.DataFrame]:
    records: list[dict] = []
    presence: dict[str, int] = {}

    for expected_division, season, path in HISTORICAL_SOURCES:
        df = read_football_data(path)
        for column in df.columns:
            presence[column] = presence.get(column, 0) + 1

        parsed_dates = parse_football_dates(df["Date"], errors="coerce")
        complete = df[CORE_COLUMNS].notna().all(axis=1)
        result_errors = int(
            (df.loc[complete, "FTR"].astype("string") != expected_result(df).loc[complete]).sum()
        )
        duplicate_count = int(df.duplicated(["Date", "HomeTeam", "AwayTeam"]).sum())
        actual_divisions = sorted(df["Div"].dropna().astype(str).unique().tolist())
        team_count = len(
            set(df["HomeTeam"].dropna().astype(str).str.strip())
            | set(df["AwayTeam"].dropna().astype(str).str.strip())
        )
        expected_rows = 380 if expected_division == "SP1" else 462
        expected_teams = 20 if expected_division == "SP1" else 22
        passed = (
            actual_divisions == [expected_division]
            and len(df) == expected_rows
            and team_count == expected_teams
            and int(parsed_dates.isna().sum()) == 0
            and duplicate_count == 0
            and result_errors == 0
            and int(df[CORE_COLUMNS].isna().sum().sum()) == 0
        )
        record = {
            "division": expected_division,
            "season": season,
            "source_file": path.relative_to(path.parents[3]).as_posix(),
            "rows": len(df),
            "columns": len(df.columns),
            "teams": team_count,
            "date_min": parsed_dates.min().date().isoformat(),
            "date_max": parsed_dates.max().date().isoformat(),
            "invalid_dates": int(parsed_dates.isna().sum()),
            "duplicates": duplicate_count,
            "result_errors": result_errors,
            "missing_core_values": int(df[CORE_COLUMNS].isna().sum().sum()),
            "actual_division_codes": "|".join(actual_divisions),
            "audit_status": "PASS" if passed else "FAIL",
        }
        for column in ODDS_COLUMNS:
            record[f"{column}_coverage"] = (
                round(float(df[column].notna().mean()), 4) if column in df.columns else 0.0
            )
        records.append(record)

    coverage = pd.DataFrame(
        [
            {
                "source_column": column,
                "files_present": count,
                "files_total": len(HISTORICAL_SOURCES),
                "coverage": count / len(HISTORICAL_SOURCES),
            }
            for column, count in sorted(presence.items())
        ]
    )
    return pd.DataFrame(records), coverage


def load_historical_matches() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for expected_division, season, path in HISTORICAL_SOURCES:
        raw = read_football_data(path)
        if set(raw["Div"].dropna().astype(str).unique()) != {expected_division}:
            raise ValueError(f"Unexpected division code in {path.name}")

        available = {source: target for source, target in SOURCE_TO_MASTER.items() if source in raw}
        df = raw[list(available)].rename(columns=available).copy()
        for target in SOURCE_TO_MASTER.values():
            if target not in df:
                df[target] = pd.NA

        df["season"] = season
        df["division"] = expected_division
        df["source_file"] = path.name
        df["date"] = parse_football_dates(df["date"], errors="raise")
        df["kickoff_time"] = df["kickoff_time"].astype("string")
        df["home_team_id"] = team_ids(df["home_team_raw"], path.name)
        df["away_team_id"] = team_ids(df["away_team_raw"], path.name)
        df["home_team"] = df["home_team_id"].map(TEAM_NAMES)
        df["away_team"] = df["away_team_id"].map(TEAM_NAMES)

        for column in NUMERIC_MASTER_COLUMNS:
            df[column] = pd.to_numeric(df[column], errors="coerce")

        expected = pd.Series("D", index=df.index, dtype="string")
        expected.loc[df["home_goals"] > df["away_goals"]] = "H"
        expected.loc[df["home_goals"] < df["away_goals"]] = "A"
        if not expected.equals(df["result"].astype("string")):
            raise ValueError(f"Result inconsistency found in {path.name}")

        df["match_id"] = (
            df["division"].str.lower()
            + "_"
            + df["season"].str.replace("/", "_", regex=False)
            + "_"
            + df["home_team_id"]
            + "_"
            + df["away_team_id"]
        )
        frames.append(df)

    result = pd.concat(frames, ignore_index=True)
    if result["match_id"].duplicated().any():
        duplicates = result.loc[result["match_id"].duplicated(), "match_id"].tolist()
        raise ValueError(f"Duplicate match identifiers: {duplicates[:5]}")

    preferred = [
        "match_id",
        "season",
        "division",
        "date",
        "kickoff_time",
        "home_team_id",
        "home_team",
        "away_team_id",
        "away_team",
        "home_goals",
        "away_goals",
        "result",
        "home_goals_ht",
        "away_goals_ht",
        "result_ht",
        "referee",
        "home_shots",
        "away_shots",
        "home_shots_on_target",
        "away_shots_on_target",
        "home_fouls",
        "away_fouls",
        "home_corners",
        "away_corners",
        "home_yellow_cards",
        "away_yellow_cards",
        "home_red_cards",
        "away_red_cards",
        "odds_b365_home",
        "odds_b365_draw",
        "odds_b365_away",
        "odds_avg_home",
        "odds_avg_draw",
        "odds_avg_away",
        "odds_max_home",
        "odds_max_draw",
        "odds_max_away",
        "source_file",
    ]
    return result[preferred].sort_values(["date", "division", "match_id"]).reset_index(drop=True)


def load_fixtures() -> pd.DataFrame:
    raw = pd.read_csv(FIXTURE_SOURCE, encoding="utf-8-sig")
    fixtures = pd.DataFrame(
        {
            "fixture_id": "laliga_" + raw["match_id_laliga"].astype(str),
            "season": "2026/27",
            "matchday": pd.to_numeric(raw["jornada"], errors="raise").astype(int),
            "reference_date": pd.to_datetime(
                raw["fecha_referencia_jornada"], errors="raise"
            ),
            "scheduled_date": pd.NaT,
            "kickoff_time": pd.NA,
            "home_team_id": team_ids(raw["equipo_local"], FIXTURE_SOURCE.name),
            "home_team_official": raw["equipo_local"].astype("string"),
            "away_team_id": team_ids(raw["equipo_visitante"], FIXTURE_SOURCE.name),
            "away_team_official": raw["equipo_visitante"].astype("string"),
            "status": "scheduled",
        }
    )
    fixtures["home_team"] = fixtures["home_team_id"].map(TEAM_NAMES)
    fixtures["away_team"] = fixtures["away_team_id"].map(TEAM_NAMES)

    teams = set(fixtures["home_team_id"]) | set(fixtures["away_team_id"])
    pair_counts = (
        fixtures.assign(pair=fixtures.apply(
            lambda row: "|".join(sorted([row["home_team_id"], row["away_team_id"]])), axis=1
        ))
        .groupby("pair")
        .size()
    )
    checks = {
        "rows": len(fixtures) == 380,
        "matchdays": fixtures["matchday"].nunique() == 38,
        "teams": len(teams) == 20,
        "unique_fixture_ids": fixtures["fixture_id"].is_unique,
        "ten_matches_per_matchday": fixtures.groupby("matchday").size().eq(10).all(),
        "two_matches_per_pair": pair_counts.eq(2).all() and len(pair_counts) == 190,
        "nineteen_home_matches": fixtures.groupby("home_team_id").size().eq(19).all(),
        "nineteen_away_matches": fixtures.groupby("away_team_id").size().eq(19).all(),
    }
    if not all(checks.values()):
        raise ValueError(f"Fixture validation failed: {checks}")

    columns = [
        "fixture_id",
        "season",
        "matchday",
        "reference_date",
        "scheduled_date",
        "kickoff_time",
        "home_team_id",
        "home_team",
        "home_team_official",
        "away_team_id",
        "away_team",
        "away_team_official",
        "status",
    ]
    return fixtures[columns].sort_values(["matchday", "fixture_id"]).reset_index(drop=True)


def league_table(matches: pd.DataFrame) -> pd.DataFrame:
    team_list = sorted(set(matches["home_team_id"]) | set(matches["away_team_id"]))
    table = {
        team: {
            "team_id": team,
            "team": TEAM_NAMES[team],
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "goals_for": 0,
            "goals_against": 0,
            "points": 0,
        }
        for team in team_list
    }

    for row in matches.itertuples(index=False):
        home = table[row.home_team_id]
        away = table[row.away_team_id]
        home["played"] += 1
        away["played"] += 1
        home["goals_for"] += int(row.home_goals)
        home["goals_against"] += int(row.away_goals)
        away["goals_for"] += int(row.away_goals)
        away["goals_against"] += int(row.home_goals)
        if row.result == "H":
            home["wins"] += 1
            away["losses"] += 1
            home["points"] += 3
        elif row.result == "A":
            away["wins"] += 1
            home["losses"] += 1
            away["points"] += 3
        else:
            home["draws"] += 1
            away["draws"] += 1
            home["points"] += 1
            away["points"] += 1

    result = pd.DataFrame(table.values())
    result["goal_difference"] = result["goals_for"] - result["goals_against"]
    result = result.sort_values(
        ["points", "goal_difference", "goals_for", "team_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    result["position"] = range(1, len(result) + 1)
    result["position_method"] = "points_goal_difference_goals_for_proxy"
    return result[
        [
            "position",
            "team_id",
            "team",
            "played",
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
            "goal_difference",
            "points",
            "position_method",
        ]
    ]


def team_set(matches: pd.DataFrame, division: str, season: str) -> set[str]:
    subset = matches[(matches["division"] == division) & (matches["season"] == season)]
    return set(subset["home_team_id"]) | set(subset["away_team_id"])


def stats_for_team(table: pd.DataFrame | None, team_id: str, prefix: str) -> dict:
    fields = [
        "position",
        "played",
        "wins",
        "draws",
        "losses",
        "goals_for",
        "goals_against",
        "goal_difference",
        "points",
    ]
    if table is None:
        return {f"{prefix}_{field}": pd.NA for field in fields}
    row = table.loc[table["team_id"] == team_id]
    if row.empty:
        return {f"{prefix}_{field}": pd.NA for field in fields}
    return {f"{prefix}_{field}": row.iloc[0][field] for field in fields}


def build_promotions(matches: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    primera_seasons = sorted(
        matches.loc[matches["division"] == "SP1", "season"].unique(),
        key=season_sort_key,
    )
    segunda_seasons = set(matches.loc[matches["division"] == "SP2", "season"].unique())
    primera_tables = {
        season: league_table(
            matches[(matches["division"] == "SP1") & (matches["season"] == season)]
        )
        for season in primera_seasons
    }
    segunda_tables = {
        season: league_table(
            matches[(matches["division"] == "SP2") & (matches["season"] == season)]
        )
        for season in segunda_seasons
    }
    fixture_teams = set(fixtures["home_team_id"]) | set(fixtures["away_team_id"])
    records: list[dict] = []

    for index in range(1, len(primera_seasons)):
        season = primera_seasons[index]
        prior_laliga_season = primera_seasons[index - 1]
        prior_segunda_season = prior_laliga_season
        arrivals = sorted(
            team_set(matches, "SP1", season)
            - team_set(matches, "SP1", prior_laliga_season)
        )
        if len(arrivals) != 3:
            raise ValueError(f"Expected three promoted teams in {season}, found {arrivals}")

        next_teams: set[str] | None = None
        if index + 1 < len(primera_seasons):
            next_teams = team_set(matches, "SP1", primera_seasons[index + 1])
        elif season == "2025/26":
            next_teams = fixture_teams

        second_table = segunda_tables.get(prior_segunda_season)
        for team_id in arrivals:
            record = {
                "team_id": team_id,
                "team": TEAM_NAMES[team_id],
                "segunda_season": prior_segunda_season,
                "laliga_season": season,
                "has_segunda_statistics": second_table is not None
                and team_id in set(second_table["team_id"]),
            }
            record.update(stats_for_team(second_table, team_id, "segunda"))
            record.update(stats_for_team(primera_tables[season], team_id, "laliga"))
            second_position = record["segunda_position"]
            record["promotion_type"] = (
                pd.NA
                if pd.isna(second_position)
                else ("direct" if int(second_position) <= 2 else "playoff")
            )
            record["relegated_after_first_season"] = (
                pd.NA if next_teams is None else team_id not in next_teams
            )
            record["identification_method"] = "new_team_vs_previous_laliga_season"
            records.append(record)

    arrivals_2026 = sorted(fixture_teams - team_set(matches, "SP1", "2025/26"))
    if len(arrivals_2026) != 3:
        raise ValueError(f"Expected three promoted teams in 2026/27, found {arrivals_2026}")
    second_table = segunda_tables["2025/26"]
    for team_id in arrivals_2026:
        record = {
            "team_id": team_id,
            "team": TEAM_NAMES[team_id],
            "segunda_season": "2025/26",
            "laliga_season": "2026/27",
            "has_segunda_statistics": team_id in set(second_table["team_id"]),
        }
        record.update(stats_for_team(second_table, team_id, "segunda"))
        record.update(stats_for_team(None, team_id, "laliga"))
        second_position = record["segunda_position"]
        record["promotion_type"] = (
            pd.NA
            if pd.isna(second_position)
            else ("direct" if int(second_position) <= 2 else "playoff")
        )
        record["relegated_after_first_season"] = pd.NA
        record["identification_method"] = "new_team_in_official_2026_27_fixture"
        records.append(record)

    result = pd.DataFrame(records)
    result = result.sort_values(
        ["laliga_season", "segunda_position", "team_id"],
        na_position="last",
    ).reset_index(drop=True)
    return result


def build_team_match_history(matches: pd.DataFrame) -> pd.DataFrame:
    common = ["match_id", "season", "division", "date"]
    home = matches[
        common
        + [
            "home_team_id",
            "away_team_id",
            "home_goals",
            "away_goals",
            "home_shots",
            "away_shots",
            "home_shots_on_target",
            "away_shots_on_target",
            "home_corners",
            "away_corners",
            "home_yellow_cards",
            "away_yellow_cards",
            "home_red_cards",
            "away_red_cards",
            "result",
        ]
    ].copy()
    home = home.rename(
        columns={
            "home_team_id": "team_id",
            "away_team_id": "opponent_id",
            "home_goals": "goals_for",
            "away_goals": "goals_against",
            "home_shots": "shots_for",
            "away_shots": "shots_against",
            "home_shots_on_target": "shots_on_target_for",
            "away_shots_on_target": "shots_on_target_against",
            "home_corners": "corners_for",
            "away_corners": "corners_against",
            "home_yellow_cards": "yellow_cards_for",
            "away_yellow_cards": "yellow_cards_against",
            "home_red_cards": "red_cards_for",
            "away_red_cards": "red_cards_against",
        }
    )
    home["venue"] = "home"
    home["team_result"] = home["result"].map({"H": "W", "D": "D", "A": "L"})

    away = matches[
        common
        + [
            "away_team_id",
            "home_team_id",
            "away_goals",
            "home_goals",
            "away_shots",
            "home_shots",
            "away_shots_on_target",
            "home_shots_on_target",
            "away_corners",
            "home_corners",
            "away_yellow_cards",
            "home_yellow_cards",
            "away_red_cards",
            "home_red_cards",
            "result",
        ]
    ].copy()
    away.columns = [
        *common,
        "team_id",
        "opponent_id",
        "goals_for",
        "goals_against",
        "shots_for",
        "shots_against",
        "shots_on_target_for",
        "shots_on_target_against",
        "corners_for",
        "corners_against",
        "yellow_cards_for",
        "yellow_cards_against",
        "red_cards_for",
        "red_cards_against",
        "result",
    ]
    away["venue"] = "away"
    away["team_result"] = away["result"].map({"H": "L", "D": "D", "A": "W"})

    history = pd.concat([home, away], ignore_index=True)
    history["team"] = history["team_id"].map(TEAM_NAMES)
    history["opponent"] = history["opponent_id"].map(TEAM_NAMES)
    history["points"] = history["team_result"].map({"W": 3, "D": 1, "L": 0})
    history = history.drop(columns="result")
    columns = [
        "match_id",
        "season",
        "division",
        "date",
        "team_id",
        "team",
        "opponent_id",
        "opponent",
        "venue",
        "team_result",
        "points",
        "goals_for",
        "goals_against",
        "shots_for",
        "shots_against",
        "shots_on_target_for",
        "shots_on_target_against",
        "corners_for",
        "corners_against",
        "yellow_cards_for",
        "yellow_cards_against",
        "red_cards_for",
        "red_cards_against",
    ]
    return history[columns].sort_values(["team_id", "date", "match_id"]).reset_index(drop=True)


def team_name_mapping() -> pd.DataFrame:
    aliases_by_id: dict[str, list[str]] = {team_id: [] for team_id in TEAM_NAMES}
    for alias, team_id in TEAM_ALIASES.items():
        aliases_by_id[team_id].append(alias)
    return pd.DataFrame(
        [
            {
                "team_id": team_id,
                "canonical_name": TEAM_NAMES[team_id],
                "known_aliases": " | ".join(sorted(aliases_by_id[team_id])),
            }
            for team_id in sorted(TEAM_NAMES)
        ]
    )


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def run_phase1() -> dict:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    audit, column_coverage = audit_sources()
    matches = load_historical_matches()
    fixtures = load_fixtures()
    promotions = build_promotions(matches, fixtures)
    team_history = build_team_match_history(matches)
    names = team_name_mapping()

    write_csv(audit, REPORTS_DIR / "data_audit.csv")
    write_csv(column_coverage, REPORTS_DIR / "column_coverage.csv")
    write_csv(matches, PROCESSED_DIR / "matches_master.csv")
    write_csv(fixtures, PROCESSED_DIR / "fixtures_2026_27.csv")
    write_csv(promotions, PROCESSED_DIR / "historical_promotions.csv")
    write_csv(
        promotions[promotions["laliga_season"] == "2026/27"],
        PROCESSED_DIR / "promoted_teams_2026_27.csv",
    )
    write_csv(team_history, PROCESSED_DIR / "team_match_history.csv")
    write_csv(names, PROCESSED_DIR / "team_name_mapping.csv")

    summary = {
        "audit_passed": bool(audit["audit_status"].eq("PASS").all()),
        "source_files": int(len(audit)),
        "laliga_matches": int((matches["division"] == "SP1").sum()),
        "segunda_matches": int((matches["division"] == "SP2").sum()),
        "historical_matches": int(len(matches)),
        "team_history_rows": int(len(team_history)),
        "fixtures_2026_27": int(len(fixtures)),
        "fixture_teams": int(
            len(set(fixtures["home_team_id"]) | set(fixtures["away_team_id"]))
        ),
        "promotion_records": int(len(promotions)),
        "promotions_with_segunda_stats": int(promotions["has_segunda_statistics"].sum()),
        "promoted_2026_27": promotions.loc[
            promotions["laliga_season"] == "2026/27", "team"
        ].tolist(),
        "outputs": {
            "matches_master": "data/processed/matches_master.csv",
            "team_match_history": "data/processed/team_match_history.csv",
            "fixtures": "data/processed/fixtures_2026_27.csv",
            "historical_promotions": "data/processed/historical_promotions.csv",
            "promoted_2026_27": "data/processed/promoted_teams_2026_27.csv",
            "team_name_mapping": "data/processed/team_name_mapping.csv",
            "data_audit": "reports/data_audit.csv",
            "column_coverage": "reports/column_coverage.csv",
        },
    }
    (REPORTS_DIR / "phase1_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
