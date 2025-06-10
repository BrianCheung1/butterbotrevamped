from datetime import datetime, timezone
from constants.valorant_config import RANK_ORDER


def convert_to_datetime(date_str: str) -> datetime:
    """Convert ISO 8601 string to a UTC-aware datetime object."""
    date_str = date_str.rstrip("Z")  # Remove trailing Z if present

    # Try parsing with microseconds
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")

    return dt.replace(tzinfo=timezone.utc)


def get_rank_value(rank_name: str) -> int:
    return RANK_ORDER.get(rank_name.lower(), -1)


def parse_season(season_code: str):
    try:
        episode = int(season_code[1 : season_code.index("a")])
        act = int(season_code[season_code.index("a") + 1 :])
        return (episode, act)
    except Exception:
        return (0, 0)
