import datetime
from datetime import timezone

import discord


def get_cooldown_response(
    last_time_str: str, cooldown: datetime.timedelta, prefix: str
) -> str | None:
    last_time = datetime.datetime.fromisoformat(last_time_str).replace(
        tzinfo=timezone.utc
    )
    now = datetime.datetime.now(timezone.utc)
    time_diff = now - last_time

    if time_diff < cooldown:
        next_available_time = last_time + cooldown
        relative = discord.utils.format_dt(next_available_time, style="R")
        absolute = discord.utils.format_dt(next_available_time, style="F")
        return f"{prefix} {relative} ({absolute})."
    return None
