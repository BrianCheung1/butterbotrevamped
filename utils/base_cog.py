import discord
from discord.ext import commands
from utils.balance_helper import validate_amount
from utils.formatting import format_number
from logger import setup_logger
from typing import Tuple

logger = setup_logger("BaseGameCog")


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
        balance: int = None,
    ) -> bool:
        """
        Validate that user has enough balance for the amount.

        Args:
            balance: If provided, skips DB call. If None, fetches from DB.
        """
        if balance is None:
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

    async def validate_bank_action_params(
        self,
        amount: int,
        action: str,
        interaction: discord.Interaction,
        deferred: bool = True,
    ) -> bool:
        """
        Validate that exactly one of amount or action is provided for bank operations.

        Checks:
        - At least one of amount or action is provided
        - Not both amount and action are provided

        Args:
            amount: Optional specific amount
            action: Optional percentage action (100%, 75%, 50%, 25%)
            interaction: Discord interaction
            deferred: Whether response is already deferred

        Returns:
            bool: True if valid, False otherwise (error message sent)

        Usage:
            if not await self.validate_bank_action_params(amount, action, interaction):
                return
        """
        if not action and not amount:
            send_method = (
                interaction.edit_original_response
                if deferred
                else interaction.response.send_message
            )
            await send_method(
                content="You must specify an amount or choose a deposit/withdrawal option.",
            )
            return False

        if amount and action:
            send_method = (
                interaction.edit_original_response
                if deferred
                else interaction.response.send_message
            )
            await send_method(
                content="You can only choose one option: amount or action."
            )
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

    async def transfer_balance(
        self,
        from_user_id: int,
        to_user_id: int,
        amount: int,
        log_action: str = "TRANSFER",
    ) -> Tuple[int, int]:
        """
        Transfer balance from one user to another.

        Returns:
            (from_user_new_balance, to_user_new_balance)
        """
        from_balance = await self.deduct_balance(from_user_id, amount)
        to_balance = await self.add_balance(to_user_id, amount)

        self.log_transaction(from_user_id, log_action, amount, f"To: {to_user_id}")

        return from_balance, to_balance

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
            footer_text: Footer text (for stats)
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

    # ============ UNIFIED GAMBLING COMMAND HANDLER ============

    async def run_gambling_command(
        self,
        interaction: discord.Interaction,
        amount: int,
        action: str,
        game_func,
        game_name: str = "Game",
        balance: int = None,
    ) -> None:
        """
        Unified handler for gambling commands (roll, slots, etc.).

        Handles:
        - Parameter validation (amount vs action)
        - Balance fetching & validation
        - Deferred response
        - Game execution

        Args:
            interaction: Discord interaction
            amount: Optional specific bet amount
            action: Optional percentage action (100%, 75%, 50%, 25%)
            game_func: Async function(bot, user_id, amount, prev_balance)
                        that executes the game and returns GameResult
            game_name: Game name for error messages
            balance: Optional pre-fetched balance (avoids extra DB call)

        Usage in a command:
            await self.run_gambling_command(
                interaction, amount, action,
                game_func=perform_roll,
                game_name="Roll"
            )
        """
        from utils.balance_helper import calculate_percentage_amount

        user_id = interaction.user.id

        # Check blackjack conflict BEFORE deferring
        if await self.check_blackjack_conflict(user_id, interaction):
            return

        await interaction.response.defer()

        # Validate parameters
        if not action and not amount:
            await interaction.edit_original_response(
                content=f"You must specify an amount or choose a {game_name.lower()} option.",
            )
            return

        if amount and action:
            await interaction.edit_original_response(
                content="You can only choose one option: amount or action."
            )
            return

        # Fetch balance once if not provided
        if balance is None:
            balance = await self.get_balance(user_id)

        # Calculate amount from action or use provided amount
        if action and not amount:
            amount = calculate_percentage_amount(balance, action)

        # Validate balance
        if not await self.validate_balance(
            user_id, amount, interaction, deferred=True, balance=balance
        ):
            return

        # Execute game with generic handler
        from utils.gambling_handler import execute_gambling_game, GameType

        # Determine game type from game_name
        game_type_map = {
            "Roll": GameType.ROLL,
            "Slots": GameType.SLOTS,
            "Blackjack": GameType.BLACKJACK,
            "Roulette": GameType.ROULETTE,
        }
        game_type = game_type_map.get(game_name, GameType.ROLL)

        # Button labels map
        button_labels = {
            "Roll": "Roll Again",
            "Slots": "Spin Again",
            "Blackjack": "Play Again",
            "Roulette": "Spin Again",
        }

        await execute_gambling_game(
            self.bot,
            interaction,
            user_id,
            amount,
            game_func=game_func,
            game_type=game_type,
            prev_balance=balance,
            add_play_again_button=True,
            play_again_label=button_labels.get(game_name, "Play Again"),
            action=action,
        )

    # ============ LOGGING/UTILITY ============

    def log_transaction(
        self, user_id: int, action: str, amount: int, details: str = ""
    ):
        """Log a transaction for debugging/auditing."""
        logger.info(
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
            logger.warning(f"Cannot DM user {user_id}; DMs might be closed.")
            return False
        except Exception as e:
            logger.error(f"Error notifying user {user_id}: {e}")
            return False
