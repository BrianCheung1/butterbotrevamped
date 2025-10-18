import discord

from utils.formatting import format_number


def build_bank_embed(
    user: discord.User, bank_stats: dict, bank_balance: int
) -> discord.Embed:
    """
    Build a bank balance embed.

    Args:
        user: Discord user object
        bank_stats: Dict containing bank_cap and bank_level
        bank_balance: Current bank balance

    Returns:
        discord.Embed with bank information
    """
    return discord.Embed(
        title=f"{user.name}'s Bank Balance",
        description=(
            f"🏦 Bank Balance: ${format_number(bank_balance)}\n"
            f"🏦 Bank Capacity: ${format_number(bank_stats['bank_cap'])}\n"
            f"🏦 Bank Level: {bank_stats['bank_level']}"
        ),
        color=discord.Color.blue(),
    )


def build_transaction_embed(
    action: str, amount: int, new_bank: int, new_wallet: int
) -> discord.Embed:
    """
    Build a transaction (deposit/withdraw) embed.

    Args:
        action: Action type (e.g., "Deposit", "Withdrawal")
        amount: Amount transacted
        new_bank: Bank balance after transaction
        new_wallet: Wallet balance after transaction

    Returns:
        discord.Embed with transaction details
    """
    return discord.Embed(
        title=f"{action} Successful",
        description=(
            f"{action}ed ${format_number(amount)}.\n"
            f"🏦 Bank: ${format_number(new_bank)}\n"
            f"💰 Wallet: ${format_number(new_wallet)}"
        ),
        color=discord.Color.green(),
    )
