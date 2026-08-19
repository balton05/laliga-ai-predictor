from __future__ import annotations

import hashlib
import io
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from laliga_predictor.dynamic import ODDS_COLUMNS, RESULT_COLUMNS


class SourceUnavailableError(RuntimeError):
    """Raised when the configured external source cannot be downloaded yet."""


class SourceDataError(ValueError):
    """Raised when downloaded rows cannot be reconciled with the calendar."""


TEAM_ALIASES = {
    "alaves": "alaves",
    "ath bilbao": "athletic_bilbao",
    "athletic bilbao": "athletic_bilbao",
    "athletic club": "athletic_bilbao",
    "ath madrid": "atletico_madrid",
    "atletico madrid": "atletico_madrid",
    "barcelona": "barcelona",
    "fc barcelona": "barcelona",
    "betis": "betis",
    "real betis": "betis",
    "celta": "celta",
    "celta vigo": "celta",
    "deportivo": "deportivo",
    "la coruna": "deportivo",
    "deportivo la coruna": "deportivo",
    "dep a coruna": "deportivo",
    "elche": "elche",
    "espanol": "espanyol",
    "espanyol": "espanyol",
    "getafe": "getafe",
    "levante": "levante",
    "malaga": "malaga",
    "osasuna": "osasuna",
    "racing santander": "racing_santander",
    "santander": "racing_santander",
    "real madrid": "real_madrid",
    "sociedad": "real_sociedad",
    "real sociedad": "real_sociedad",
    "sevilla": "sevilla",
    "valencia": "valencia",
    "vallecano": "vallecano",
    "rayo vallecano": "vallecano",
    "villarreal": "villarreal",
}

STAT_COLUMNS = {
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HC": "home_corners",
    "AC": "away_corners",
    "HY": "home_yellow_cards",
    "AY": "away_yellow_cards",
    "HR": "home_red_cards",
    "AR": "away_red_cards",
}


@dataclass(frozen=True)
class FootballDataSnapshot:
    source_url: str
    checksum: str
    fetched_at_utc: datetime
    source_modified_at_utc: datetime | None
    rows_downloaded: int
    results: pd.DataFrame
    odds: pd.DataFrame


def _normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(
        text.casefold()
        .replace(".", " ")
        .replace("-", " ")
        .replace("_", " ")
        .split()
    )


def _team_lookup(fixtures: pd.DataFrame) -> dict[str, str]:
    lookup = dict(TEAM_ALIASES)
    for side in ("home", "away"):
        for row in fixtures[
            [f"{side}_team_id", f"{side}_team", f"{side}_team_official"]
        ].drop_duplicates().itertuples(index=False):
            team_id, display, official = row
            lookup[_normalize_name(team_id)] = str(team_id)
            lookup[_normalize_name(display)] = str(team_id)
            lookup[_normalize_name(official)] = str(team_id)
    return lookup


def _parse_date(value: object) -> pd.Timestamp:
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise SourceDataError(f"Invalid Football-Data date: {value!r}")
    return pd.Timestamp(parsed).normalize()


def _number(row: pd.Series, source: str) -> float | None:
    if source not in row or pd.isna(row[source]) or str(row[source]).strip() == "":
        return None
    value = pd.to_numeric(row[source], errors="coerce")
    return None if pd.isna(value) else float(value)


def parse_football_data(
    content: bytes,
    fixtures: pd.DataFrame,
    source_url: str,
    fetched_at_utc: datetime | None = None,
    source_modified_at_utc: datetime | None = None,
) -> FootballDataSnapshot:
    """Convert a Football-Data SP1 CSV into the project's canonical inputs."""
    fetched_at = fetched_at_utc or datetime.now(timezone.utc)
    checksum = hashlib.sha256(content).hexdigest()
    try:
        frame = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
    except UnicodeDecodeError:
        frame = pd.read_csv(io.BytesIO(content), encoding="cp1252")
    required = {"HomeTeam", "AwayTeam"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SourceDataError(
            f"Football-Data CSV is missing columns: {missing}"
        )

    fixtures = fixtures.copy()
    pair_lookup = {
        (str(row.home_team_id), str(row.away_team_id)): row
        for row in fixtures.itertuples(index=False)
    }
    names = _team_lookup(fixtures)
    result_rows: list[dict] = []
    odds_rows: list[dict] = []
    unmatched: list[str] = []
    capture_time = source_modified_at_utc or fetched_at
    if capture_time.tzinfo is None:
        capture_time = capture_time.replace(tzinfo=timezone.utc)

    for row_number, row in frame.iterrows():
        has_result = _number(row, "FTHG") is not None and _number(row, "FTAG") is not None
        has_odds = all(
            _number(row, column) is not None
            for column in ("B365H", "B365D", "B365A")
        )
        if not has_result and not has_odds:
            continue

        home_key = _normalize_name(row["HomeTeam"])
        away_key = _normalize_name(row["AwayTeam"])
        home_id = names.get(home_key)
        away_id = names.get(away_key)
        fixture = pair_lookup.get((home_id, away_id)) if home_id and away_id else None
        if fixture is None:
            unmatched.append(
                f"row {row_number + 2}: {row['HomeTeam']} vs {row['AwayTeam']}"
            )
            continue

        if has_result:
            played_date = (
                _parse_date(row["Date"])
                if "Date" in frame.columns
                else pd.Timestamp(fixture.reference_date)
            )
            result = {
                "fixture_id": str(fixture.fixture_id),
                "date": played_date.date().isoformat(),
                "home_goals": int(_number(row, "FTHG") or 0),
                "away_goals": int(_number(row, "FTAG") or 0),
            }
            for source, target in STAT_COLUMNS.items():
                result[target] = _number(row, source)
            result_rows.append(result)

        if has_odds:
            odds = {
                "fixture_id": str(fixture.fixture_id),
                "captured_at": capture_time.isoformat(),
                "odds_b365_home": _number(row, "B365H"),
                "odds_b365_draw": _number(row, "B365D"),
                "odds_b365_away": _number(row, "B365A"),
            }
            if all(float(odds[column]) > 1.0 for column in ODDS_COLUMNS[2:]):
                odds_rows.append(odds)

    if unmatched:
        sample = "; ".join(unmatched[:5])
        raise SourceDataError(
            "Football-Data contains relevant matches that do not match the "
            f"2026/27 calendar: {sample}"
        )

    results = pd.DataFrame(result_rows, columns=RESULT_COLUMNS)
    odds = pd.DataFrame(odds_rows, columns=ODDS_COLUMNS)
    return FootballDataSnapshot(
        source_url=source_url,
        checksum=checksum,
        fetched_at_utc=fetched_at,
        source_modified_at_utc=source_modified_at_utc,
        rows_downloaded=len(frame),
        results=results,
        odds=odds,
    )


def fetch_football_data(
    url: str,
    fixtures: pd.DataFrame,
    timeout_seconds: int = 30,
    opener: Callable[..., object] = urlopen,
) -> FootballDataSnapshot:
    request = Request(
        url,
        headers={
            "User-Agent": "LaLiga-AI-Predictor/1.1 (+portfolio project)",
            "Accept": "text/csv,text/plain,*/*",
        },
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            content = response.read()
            modified_header = response.headers.get("Last-Modified")
    except HTTPError as exc:
        if exc.code in {403, 404, 429}:
            raise SourceUnavailableError(
                f"Football-Data returned HTTP {exc.code}; the 2026/27 file "
                "may not be published yet."
            ) from exc
        raise SourceUnavailableError(
            f"Football-Data returned HTTP {exc.code}."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceUnavailableError(
            f"Football-Data could not be reached: {exc}"
        ) from exc
    if not content:
        raise SourceUnavailableError("Football-Data returned an empty file.")
    modified = (
        parsedate_to_datetime(modified_header)
        if modified_header
        else None
    )
    return parse_football_data(
        content,
        fixtures=fixtures,
        source_url=url,
        fetched_at_utc=datetime.now(timezone.utc),
        source_modified_at_utc=modified,
    )
