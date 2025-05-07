from datetime import datetime


def convert_to_datetime(date_str: str) -> datetime:
    """Convert ISO 8601 string to a datetime object."""
    date_str = date_str.rstrip("Z")  # Remove trailing Z

    # Try parsing with microseconds
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        # Fallback: parse without microseconds
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
