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

