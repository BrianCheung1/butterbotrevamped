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


def build_balance_change_embed(
    title: str,
    description: str,
    prev_balance: int,
    new_balance: int,
    amount: int,
    color: discord.Color = discord.Color.green(),
    footer_text: str = None,
    **extra_fields,
) -> discord.Embed:
    """
    Build a standardized balance change embed (for games, rewards, etc.).

    Args:
        title: Embed title
        description: Main description
        prev_balance: Previous balance
        new_balance: New balance after action
        amount: Amount involved in action
        color: Embed color (default green)
        footer_text: Optional footer text (e.g., stats)
        **extra_fields: Additional fields to add (name=value pairs)

    Returns:
        discord.Embed with formatted balance information
    """
    embed = discord.Embed(title=title, description=description, color=color)

    embed.add_field(name="Amount", value=f"${format_number(amount)}", inline=True)
    embed.add_field(
        name="Previous Balance",
        value=f"${format_number(prev_balance)}",
        inline=True,
    )
    embed.add_field(
        name="Current Balance",
        value=f"${format_number(new_balance)}",
        inline=True,
    )

    for field_name, field_value in extra_fields.items():
        embed.add_field(name=field_name, value=field_value, inline=False)

    if footer_text:
        embed.set_footer(text=footer_text)

    return embed
