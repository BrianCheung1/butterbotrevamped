import datetime
from enum import Enum

STEAL_COOLDOWN = datetime.timedelta(hours=1)
STOLEN_FROM_COOLDOWN = datetime.timedelta(hours=3)
MIN_BALANCE_TO_STEAL = 100_000
BASE_SUCCESS_RATE = 0.5
STEAL_AMOUNT_RANGE = (0.1, 0.2)

WEALTH_FACTOR_CAP = 500_000
WEALTH_MULTIPLIER = 0.25
EXTRA_WEALTH_CAP = 10_000_000
EXTRA_WEALTH_MULTIPLIER = 0.1

LARGE_BALANCE_THRESHOLD = 1_000_000
LARGE_BALANCE_MULTIPLIER = 0.1


class TheftTier(Enum):
    COMMON = (0.05, 0.075, 85)
    UNCOMMON = (0.075, 0.10, 10)
    RARE = (0.10, 0.15, 4)
    SUPER_RARE = (0.15, 0.20, 1)


THEFT_TIERS = [
    (TheftTier.COMMON.value[0], TheftTier.COMMON.value[1]),
    (TheftTier.UNCOMMON.value[0], TheftTier.UNCOMMON.value[1]),
    (TheftTier.RARE.value[0], TheftTier.RARE.value[1]),
    (TheftTier.SUPER_RARE.value[0], TheftTier.SUPER_RARE.value[1]),
]

THEFT_TIER_WEIGHTS = [
    TheftTier.COMMON.value[2],
    TheftTier.UNCOMMON.value[2],
    TheftTier.RARE.value[2],
    TheftTier.SUPER_RARE.value[2],
]


class StealEventType(Enum):
    """Steal event types for stats tracking."""

    STEAL_SUCCESS = "steal_success"
    STEAL_FAIL = "steal_fail"
    VICTIM_SUCCESS = "victim_success"
    VICTIM_FAIL = "victim_fail"
