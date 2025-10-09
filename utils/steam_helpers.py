import re
from typing import Optional

import discord
import requests
from discord import app_commands


def extract_app_id(steam_link: str) -> str:
    match = re.search(r"store\.steampowered\.com/app/(\d+)", steam_link)
    if match:
        return match.group(1)
    raise ValueError("Invalid Steam link: Could not extract AppID")


def fetch_steam_app_details(app_id: str) -> dict:
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get(app_id, {}).get("success"):
        return data[app_id]["data"]
    else:
        raise ValueError(f"Steam API: No data for AppID {app_id}")


def fetch_steam_review_summary(app_id: str) -> str:
    url = f"https://store.steampowered.com/appreviews/{app_id}?json=1"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data.get("success") == 1:
        desc = data.get("query_summary", {}).get("review_score_desc")
        total = data.get("query_summary", {}).get("total_reviews")
        if desc and total:
            return f"{desc} ({total:,})"
    return "N/A"


def clean_notes(notes: Optional[str]) -> str:
    if not notes:
        return "No Notes"

    parts = [note.strip() for note in notes.split(";") if note.strip()]
    if not parts:
        return "No Notes"

    formatted = "\n".join(f"- {note}" for note in parts)
    return formatted


async def game_title_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Autocomplete Steam game titles from DB."""
    games = await interaction.client.database.steam_games_db.get_all_games()
    titles = [g["title"] for g in games if "title" in g]

    if current:
        titles = [t for t in titles if current.lower() in t.lower()]

    return [app_commands.Choice(name=title, value=title) for title in titles[:25]]
