import math


def format_number(n: int | float) -> str:
    def format_suffix(value, suffix):
        # Truncate to 1 decimal place
        truncated = math.floor(value * 10) / 10
        formatted = f"{truncated:.1f}".rstrip("0").rstrip(".")
        return f"{formatted}{suffix}"

    if n >= 1_000_000_000:
        return format_suffix(n / 1_000_000_000, "B")
    elif n >= 1_000_000:
        return format_suffix(n / 1_000_000, "M")
    elif n >= 1_000:
        return format_suffix(n / 1_000, "K")
    return str(n)


def clean_patchnotes(raw_changes: str) -> tuple[str, str]:
    """
    Cleans semicolon-separated patch notes.

    Returns:
        - String formatted for DB storage (semicolon-joined, capitalized)
        - String formatted for embed (bullet point list)
    """
    items = [
        item.strip().capitalize() for item in raw_changes.split(";") if item.strip()
    ]
    if not items:
        return "", ""
    db_formatted = ";".join(items)
    embed_formatted = "\n".join(f"- {item}" for item in items)
    return db_formatted, embed_formatted
