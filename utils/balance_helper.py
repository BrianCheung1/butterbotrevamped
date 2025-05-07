from typing import Optional


def validate_amount(amount: Optional[int], balance: int) -> Optional[str]:
    if amount is None or amount <= 0:
        return "Invalid amount"
    if amount > balance:
        return f"You don't have enough balance to roll this amount. Current balance is ${format_number(balance)}."
    return None
