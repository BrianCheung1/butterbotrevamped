from enum import Enum


class GameEventType(Enum):
    """Enum for different types of games."""

    BLACKJACK = "blackjacks"
    SLOTS = "slots"
    ROLL = "rolls"
