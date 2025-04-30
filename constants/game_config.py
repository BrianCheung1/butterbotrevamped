from enum import Enum


class GameEventType(Enum):
    """Enum for different types of games."""

    BLACKJACK = "blackjacks"
    SLOT = "slots"
    ROLL = "rolls"
