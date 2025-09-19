from typing import Optional

from utils.formatting import format_number


def validate_amount(amount: Optional[int], balance: int) -> Optional[str]:
    if balance <= 0:
        return "You have no balance available for this action."
    if amount is None or amount <= 0:
        return "Invalid amount. Please enter a value greater than 0."
    if amount > balance:
        return f"You don't have enough balance for this action. Current balance is ${format_number(balance)}."
    return None


def calculate_percentage_amount(balance: int, action: Optional[str]) -> Optional[int]:
    if action == "100%":
        return balance
    elif action == "75%":
        return (balance * 75) // 100
    elif action == "50%":
        return balance // 2
    elif action == "25%":
        return balance // 4
    return None
