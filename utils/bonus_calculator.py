from typing import Dict, Tuple


def calculate_value_bonuses(
    base_value: int,
    level: int = 0,
    level_multiplier: float = 0.05,
    tool_bonus_pct: float = 0.0,
    pet_bonus_pct: float = 0.0,
) -> Tuple[int, int, int, int]:
    """
    Calculate all value bonuses at once.

    Args:
        base_value: The base value before bonuses
        level: User level (for level-based bonus)
        level_multiplier: Multiplier per level (default 5% per level)
        tool_bonus_pct: Tool bonus as decimal (e.g., 0.2 = 20%)
        pet_bonus_pct: Pet bonus as decimal (e.g., 0.1 = 10%)

    Returns:
        Tuple of (level_bonus, tool_bonus, pet_bonus, total_value)

    Example:
        >>> calculate_value_bonuses(100, level=5, tool_bonus_pct=0.2)
        (25, 20, 0, 145)
    """
    level_bonus = int(base_value * (level * level_multiplier)) if level else 0
    tool_bonus = int(base_value * tool_bonus_pct)
    pet_bonus = int(base_value * pet_bonus_pct)
    total = base_value + level_bonus + tool_bonus + pet_bonus

    return level_bonus, tool_bonus, pet_bonus, total


def calculate_xp_bonuses(
    base_xp: int,
    buffs: dict,
    buff_key: str = "exp",
    pet_xp_pct: float = 0.0,
) -> Tuple[int, int, int]:
    """
    Calculate all XP bonuses at once.

    Args:
        base_xp: Base XP before bonuses
        buffs: Buffs dict from database
        buff_key: Which buff to check (default "exp")
        pet_xp_pct: Pet XP bonus as decimal

    Returns:
        Tuple of (buff_bonus_xp, pet_bonus_xp, total_xp)

    Example:
        >>> buffs = {"exp": {"multiplier": 1.5}}
        >>> calculate_xp_bonuses(10, buffs)
        (5, 0, 15)
    """
    buff = buffs.get(buff_key)
    multiplier = buff.get("multiplier", 1.0) if buff else 1.0
    xp_with_buffs = int(base_xp * multiplier)
    buff_bonus_xp = xp_with_buffs - base_xp
    pet_bonus_xp = int(xp_with_buffs * pet_xp_pct)
    total_xp = xp_with_buffs + pet_bonus_xp

    return buff_bonus_xp, pet_bonus_xp, total_xp


def calculate_percentage_bonus(
    base_amount: int,
    percentage: float,
) -> int:
    """
    Calculate a percentage bonus on an amount.

    Args:
        base_amount: Base amount
        percentage: Percentage as decimal (e.g., 0.2 = 20%)

    Returns:
        int: Bonus amount

    Example:
        >>> calculate_percentage_bonus(100, 0.2)
        20
    """
    return int(base_amount * percentage)


def apply_buff_multiplier(base_value: float, buffs: dict, buff_key: str) -> float:
    """
    Apply buff multiplier to a value.

    Args:
        base_value: The base value to apply buff to
        buffs: Buffs dict from database
        buff_key: Which buff to check (e.g., "exp", "steal_success", "steal_resistance")

    Returns:
        float: The value after buff multiplier applied

    Example:
        >>> buffs = {"exp": {"multiplier": 1.5}}
        >>> apply_buff_multiplier(100, buffs, "exp")
        150.0
    """
    buff = buffs.get(buff_key)
    if not buff:
        return base_value
    return base_value * buff.get("multiplier", 1.0)
