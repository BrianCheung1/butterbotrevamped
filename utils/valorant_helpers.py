from datetime import datetime, timezone
from constants.valorant_config import RANK_ORDER
from typing import Optional
import aiohttp
import os
from logger import setup_logger

logger = setup_logger("Butterbot")


VAL_KEY = os.getenv("VAL_KEY")


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


async def load_cached_players_from_db(db):
    """Load cached players from the database"""
    mmr_data = await db.get_all_player_mmr()
    logger.info(f"Loaded {len(mmr_data)} Valorant players from DB.")
    return {(d["name"], d["tag"]): d for d in mmr_data}


async def fetch_val_api(url: str, name: str, tag: str) -> Optional[dict]:
    """Handles API requests to HenrikDev API asynchronously using aiohttp."""
    if not VAL_KEY:
        logger.error("VAL_KEY is not set in environment variables.")
        return None

    headers = {"Authorization": VAL_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    logger.info(
                        f"Successfully fetched data for {name}#{tag} from URL: {url}"
                    )
                    return await response.json()
                else:
                    logger.warning(
                        f"Failed to fetch data for {name}#{tag} from URL: {url} - HTTP Status: {response.status}"
                    )
    except Exception as e:
        logger.error(
            f"Exception while fetching data for {name}#{tag} from URL: {url} - Error: {e}"
        )
    return None
