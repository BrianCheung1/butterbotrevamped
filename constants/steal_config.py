from enum import Enum, auto


class StealEventType(Enum):
    STEAL_SUCCESS = auto()  # The stealer succeeded
    STEAL_FAIL = auto()  # The stealer failed
    VICTIM_SUCCESS = auto()  # Victim lost money to a successful steal
    VICTIM_FAIL = auto()  # Victim gained money from failed steal
