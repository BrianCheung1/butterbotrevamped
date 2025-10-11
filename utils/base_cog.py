# utils/base_cog.py

import discord
from discord.ext import commands

from utils.balance_helper import validate_amount
from utils.formatting import format_number


class BaseGameCog(commands.Cog):
    """
    Abstract base class for all game/economy cogs.
    Handles common patterns like blackjack conflicts, balance validation, deferred responses.
    """

    def __init__(self, bot):
        self.bot = bot

    # ============ BLACKJACK CHECKS ============

    async def check_blackjack_conflict(
        self, user_id: int, interaction: discord.Interaction
    ) -> bool:
        """
        Check if user is in a Blackjack game.
        Returns True if conflict exists (and sends error message), False otherwise.

        Usage:
            if await self.check_blackjack_conflict(user_id, interaction):
                return
        """
        if user_id not in self.bot.active_blackjack_players:
            return False

        await interaction.response.send_message(
            "❌ You are in a Blackjack game! Please finish that first.",
            ephemeral=True,
        )
        return True

    # ============ BALANCE VALIDATION ============

    async def validate_balance(
        self,
        user_id: int,
        amount: int,
        interaction: discord.Interaction,
        deferred: bool = False,
    ) -> bool:
        """
        Validate that user has enough balance for the amount.
        Returns True if valid, False if not (sends error message).

        Args:
            user_id: Discord user ID
            amount: Amount to validate
            interaction: Discord interaction
            deferred: If True, uses edit_original_response; if False, uses response.send_message
        """
        balance = await self.bot.database.user_db.get_balance(user_id)
        error = validate_amount(amount, balance)

        if error:
            send_method = (
                interaction.edit_original_response
                if deferred
                else interaction.response.send_message
            )
            await send_method(content=error)
            return False

        return True

    async def get_balance(self, user_id: int) -> int:
        """Fetch user's current balance."""
        return await self.bot.database.user_db.get_balance(user_id)

    async def deduct_balance(self, user_id: int, amount: int) -> int:
        """Deduct amount from user's balance. Returns new balance."""
        return await self.bot.database.user_db.increment_balance(user_id, -amount)

    async def add_balance(self, user_id: int, amount: int) -> int:
        """Add amount to user's balance. Returns new balance."""
        return await self.bot.database.user_db.increment_balance(user_id, amount)

    # ============ GAME RESULT HELPERS ============

    def create_balance_embed(
        self,
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
        Create a standardized game result embed.

        Args:
            title: Embed title
            description: Main description
            prev_balance: Previous balance before game
            new_balance: Balance after game
            amount: Amount wagered
            color: Embed color
            footer_text: Footer text (for stats like wins/losses/ties)
            **extra_fields: Additional fields (name=value pairs)
        """
        embed = discord.Embed(title=title, description=description, color=color)
        embed.add_field(
            name="Bet Amount", value=f"${format_number(amount)}", inline=True
        )
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

    # ============ SELF-BOT CHECKS ============

    async def check_self_transaction(
        self, user_id: int, target_id: int, interaction: discord.Interaction
    ) -> bool:
        """
        Check if user is trying to transact with themselves.
        Returns True if conflict exists, False otherwise.
        """
        if user_id != target_id:
            return False

        await interaction.response.send_message(
            "❌ You can't perform this action on yourself!",
            ephemeral=True,
        )
        return True

    async def check_bot_target(
        self, user: discord.User, interaction: discord.Interaction
    ) -> bool:
        """
        Check if target is a bot.
        Returns True if target is bot, False otherwise.
        """
        if not user.bot:
            return False

        await interaction.response.send_message(
            "❌ You can't perform this action on bots!",
            ephemeral=True,
        )
        return True

    # ============ COMMON VALIDATIONS ============

    async def pre_game_checks(
        self,
        user_id: int,
        amount: int,
        interaction: discord.Interaction,
        check_blackjack: bool = True,
        deferred: bool = True,
    ) -> bool:
        """
        Run all pre-game validation checks in sequence.
        Returns True if all checks pass, False if any fail.

        Checks:
        - Blackjack conflict (optional)
        - Balance validation

        Usage:
            if not await self.pre_game_checks(user_id, amount, interaction):
                return
        """
        if check_blackjack:
            if await self.check_blackjack_conflict(user_id, interaction):
                return False

        if not await self.validate_balance(user_id, amount, interaction, deferred):
            return False

        return True

    # ============ LOGGING/UTILITY ============

    def log_transaction(
        self, user_id: int, action: str, amount: int, details: str = ""
    ):
        """Log a transaction for debugging/auditing."""
        self.bot.logger.info(
            f"[{action}] User {user_id} | Amount: ${format_number(amount)} | {details}"
        )

    async def notify_user(
        self, user_id: int, message: str, title: str = "Notification"
    ) -> bool:
        """
        Try to DM a user a notification.
        Returns True if successful, False otherwise.
        """
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            embed = discord.Embed(
                title=title, description=message, color=discord.Color.blue()
            )
            await user.send(embed=embed)
            return True
        except discord.Forbidden:
            self.bot.logger.warning(f"Cannot DM user {user_id}; DMs might be closed.")
            return False
        except Exception as e:
            self.bot.logger.error(f"Error notifying user {user_id}: {e}")
            return False
