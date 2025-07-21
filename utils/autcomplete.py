from typing import List

from discord import app_commands
from discord.ext import commands


async def patch_number_autocomplete(
    interaction: commands.Context,
    current: str,
) -> List[app_commands.Choice[int]]:
    entries = await interaction.client.database.patch_notes_db.get_all_patch_notes()
    entries.sort(key=lambda e: e["timestamp"], reverse=True)

    choices = []
    for i, entry in enumerate(entries):
        display_number = len(entries) - i
        snippet = entry["changes"][:50].strip().replace("\n", " ")
        label = f"Patch #{display_number} - {snippet}"
        choices.append(app_commands.Choice(name=label, value=display_number))

    if current:
        current_lower = current.lower()
        choices = [c for c in choices if current_lower in c.name.lower()]

    return choices[:25]


async def reminder_index_autocomplete(
    interaction: commands.Context,
    current: str,
) -> List[app_commands.Choice[int]]:
    reminders = await interaction.client.database.reminders_db.get_user_reminders(
        interaction.user.id
    )
    if not reminders:
        return []

    choices = []
    for i, reminder in enumerate(reminders, start=1):
        label = reminder[1].replace("\n", " ").strip()
        max_length = 80
        if len(label) > max_length:
            label = label[: max_length - 3] + "..."
        label = f"#{i}: {label}"
        choices.append(app_commands.Choice(name=label, value=i))

    if current:
        current_lower = current.lower()
        choices = [c for c in choices if current_lower in c.name.lower()]

    return choices[:25]
