"""External data-source adapters used by the operational pipeline."""

from .football_data import (
    FootballDataSnapshot,
    SourceDataError,
    SourceUnavailableError,
    fetch_football_data,
    parse_football_data,
)

__all__ = [
    "FootballDataSnapshot",
    "SourceDataError",
    "SourceUnavailableError",
    "fetch_football_data",
    "parse_football_data",
]
