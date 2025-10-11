from datetime import datetime, timezone
from typing import Tuple

import discord
from constants.valorant_config import RANK_ORDER
from discord.app_commands import Choice
from logger import setup_logger

logger = setup_logger("Butterbot")


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
    """Get numeric value for rank comparison."""
    return RANK_ORDER.get(rank_name.lower(), -1)


def parse_season(season_code: str):
    """Parse season code (e.g., 'e8a3') into (episode, act) tuple."""
    roman_map = {
        "I": 1,
        "II": 2,
        "III": 3,
        "IV": 4,
        "V": 5,
        "VI": 6,
        "VII": 7,
        "VIII": 8,
        "IX": 9,
        "X": 10,
    }

    try:
        episode = int(season_code[1 : season_code.index("a")])
        act_part = season_code[season_code.index("a") + 1 :]

        try:
            act = int(act_part)
        except ValueError:
            act = roman_map.get(act_part.upper(), 0)

        return (episode, act)
    except Exception:
        return (0, 0)


def parse_player_rank(current_data: dict) -> Tuple[str, int, int]:
    """
    Parse player rank information from current MMR data.


    Args:
        current_data: Current player data dict from API

    Returns:
        Tuple of (rank_name, current_rr, games_needed)

    Raises:
        ValueError: If current_data is invalid or missing required fields
    """
    if not current_data:
        raise ValueError("current_data cannot be None or empty")

    games_needed = current_data.get("games_needed_for_rating", 0)

    if games_needed > 0:
        return "Unrated", 0, games_needed

    try:
        rank = current_data.get("tier", {}).get("name", "Unknown")
        rr = current_data.get("rr", 0)

        if rank == "Unknown":
            logger.warning("Could not determine rank from current data")

        return rank, rr, 0
    except (KeyError, TypeError) as e:
        logger.warning(f"Error parsing player rank: {e}")
        raise ValueError(f"Invalid current_data structure: {e}")


async def load_cached_players_from_db(db):
    """
    Load cached players from the database on bot startup.


    Args:
        db: Database manager instance

    Returns:
        Dict mapping (name, tag) -> {rank, elo, ...}
    """
    mmr_data = await db.get_all_player_mmr()
    logger.info(f"Loaded {len(mmr_data)} Valorant players from DB.")

    # Return as dict with tuple keys for batch_set()
    return {
        (d["name"], d["tag"]): {
            "rank": d["rank"],
            "elo": d["elo"],
        }
        for d in mmr_data
    }


async def name_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for player names from cached player list."""
    bot = interaction.client

    # Use thread-safe cache manager
    if not hasattr(bot, "valorant_players"):
        return []

    try:
        all_players = await bot.valorant_players.get_all()

        if not all_players:
            return []

        unique_names = sorted(
            set(
                name
                for name, tag in all_players.keys()
                if name.lower().startswith(current.lower())
            )
        )
        return [Choice(name=n, value=n) for n in unique_names[:25]]
    except Exception as e:
        logger.warning(f"Error in name_autocomplete: {e}")
        return []


async def tag_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for player tags based on selected name."""
    bot = interaction.client
    name = interaction.namespace.name  # what user selected for "name"

    # Use thread-safe cache manager
    if not hasattr(bot, "valorant_players") or not name:
        return []

    try:
        all_players = await bot.valorant_players.get_all()

        if not all_players:
            return []

        filtered_tags = sorted(
            {
                tag
                for n, tag in all_players.keys()
                if n.lower() == name.lower() and tag.lower().startswith(current.lower())
            }
        )
        return [Choice(name=t, value=t) for t in filtered_tags[:25]]
    except Exception as e:
        logger.warning(f"Error in tag_autocomplete: {e}")
        return []
