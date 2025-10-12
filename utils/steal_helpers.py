from typing import Tuple
from utils.bonus_calculator import apply_buff_multiplier


def calculate_wealth_factors(
    balance: int, wealth_factor_cap: int, extra_wealth_cap: int
) -> Tuple[float, float]:
    """Calculate wealth-based modifiers."""
    wealth_factor = min(balance / wealth_factor_cap, 1)
    extra_wealth_factor = min(balance / extra_wealth_cap, 1)
    return wealth_factor, extra_wealth_factor


def calculate_steal_success_rate(
    target_balance: int,
    thief_buffs: dict,
    target_buffs: dict,
    base_rate: float,
    wealth_multiplier: float,
    extra_wealth_multiplier: float,
    wealth_factor_cap: int,
    extra_wealth_cap: int,
) -> Tuple[float, float, float]:
    """Calculate steal success rate with all modifiers."""
    wealth_factor, extra_wealth_factor = calculate_wealth_factors(
        target_balance, wealth_factor_cap, extra_wealth_cap
    )
    base = (
        base_rate
        + wealth_multiplier * wealth_factor
        + extra_wealth_multiplier * extra_wealth_factor
    )

    buffed = apply_buff_multiplier(base, thief_buffs, "steal_success")
    final = apply_buff_multiplier(buffed, target_buffs, "steal_resistance")
    return base, buffed, final


def calculate_stolen_amount(
    target_balance: int,
    theft_tiers: list,
    theft_tier_weights: list,
    large_balance_threshold: int,
    large_balance_multiplier: float,
) -> int:
    """Calculate amount stolen on successful steal."""
    import random

    low, high = random.choices(theft_tiers, weights=theft_tier_weights, k=1)[0]
    percent = random.uniform(low, high)
    if target_balance > large_balance_threshold:
        percent *= large_balance_multiplier
    stolen = max(1, int(target_balance * percent))
    return min(stolen, target_balance)


def calculate_lost_amount(
    thief_balance: int, steal_amount_range: Tuple[float, float]
) -> int:
    """Calculate amount lost on failed steal."""
    import random

    lost = int(thief_balance * random.uniform(*steal_amount_range))
    return min(lost, thief_balance)
